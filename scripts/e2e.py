"""파트너 통합을 end-to-end로 한 번에 검증한다 (등록 포함).

세 단계를 순차로 수행한다:

  1. 로컬 자가확인 (A 세그먼트, cloudflared 불필요)
     - 로컬 샘플 서버에 로그인 → 토큰 발급 → /api/userinfo·/api/patients 호출
     - "내 OAuth/API가 토큰을 받아 환자를 돌려주는가"를 직접 확인 (환자 목록 출력)

  2. 새록에 등록 (B 세그먼트, cloudflared 필요)
     - register_idp (+ --with-webhook 시 register_webhook)
     - 등록되는 URL은 PUBLIC_BASE_URL 기반이므로 공인 HTTPS여야 한다 (§6.2)

  3. 새록 경유 검증 (B 세그먼트, cloudflared 필요)
     - 1에서 발급한 사용자 토큰으로 validate_partner_api 호출
     - 새록이 등록된 userInfoUrl·userPatientsUrl로 **들어와** 스펙을 검증한 리포트를 돌려준다
       (환자 데이터 자체가 아니라 ok/error/skipped 리포트)

1의 토큰 발급은 로컬(localhost)에서 일어나 cloudflared와 무관하지만, 2·3은
PUBLIC_BASE_URL이 새록에서 도달 가능한 공인 HTTPS여야 한다. 따라서 보통:

    cloudflared tunnel --url http://localhost:8000      # 별도 터미널
    PUBLIC_BASE_URL=https://<랜덤>.trycloudflare.com \\
        uv run python -m scripts.e2e --with-webhook

웹훅 secret은 .env를 자동 수정하지 않고 출력만 하므로 직접 저장 후 서버를 재시작한다.

사용법:
    uv run python -m scripts.e2e                 # 로컬확인 + 등록 + 검증
    uv run python -m scripts.e2e --with-webhook  # 위 + 웹훅 등록
    uv run python -m scripts.e2e --skip-validate # 새록 경유 검증(3) 생략
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import re
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from urllib.parse import parse_qs, urlsplit

import httpx

from app.config import Settings, get_settings
from app.connect.schemas import IdentityProviderRequest
from scripts._common import connect_client, load_settings

_TRYCLOUDFLARE_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


@contextlib.contextmanager
def cloudflared_tunnel(local_url: str, *, timeout: float = 30.0) -> Iterator[str]:
    """cloudflared Quick Tunnel을 띄워 공인 HTTPS URL을 yield하고, 끝나면 종료한다.

    cloudflared가 PATH에 없으면 SystemExit. URL은 cloudflared의 로그(stderr)에서
    파싱하며 timeout 안에 못 찾으면 SystemExit.
    """
    if shutil.which("cloudflared") is None:
        raise SystemExit(
            "cloudflared가 설치되어 있지 않습니다. --with-tunnel을 쓰려면 먼저 설치하세요.\n"
            "  macOS: brew install cloudflared\n"
            "  그 외:  https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/",
        )

    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", local_url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        url = _wait_for_tunnel_url(proc, timeout=timeout)
        print(f"✓ cloudflared 터널: {url}", flush=True)
        # 엣지 전파에 시차가 있어, URL이 로그에 찍힌 직후엔 외부에서 아직 도달 안 될 수
        # 있다. 새록이 등록 직후 검증하므로, 공인 URL로 실제 200이 올 때까지 기다린다.
        _wait_for_tunnel_ready(url, timeout=timeout)
        print(f"  (로컬 {local_url} → 외부 도달 확인)")
        yield url
    finally:
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)
        if proc.poll() is None:
            proc.kill()
        print("• cloudflared 터널 종료")


def _wait_for_tunnel_url(proc: subprocess.Popen[str], *, timeout: float) -> str:
    """cloudflared stderr에서 trycloudflare URL을 찾을 때까지 대기."""
    deadline = time.monotonic() + timeout
    assert proc.stderr is not None
    while time.monotonic() < deadline:
        line = proc.stderr.readline()
        if not line:
            if proc.poll() is not None:
                raise SystemExit("cloudflared가 URL 발급 전에 종료되었습니다.")
            continue
        match = _TRYCLOUDFLARE_RE.search(line)
        if match:
            return match.group(0)
    proc.terminate()
    raise SystemExit(f"cloudflared URL을 {timeout}초 안에 받지 못했습니다.")


def _wait_for_tunnel_ready(url: str, *, timeout: float, grace: float = 6.0) -> None:
    """공인 URL이 외부에서 실제 응답할 때까지 폴링한다 (엣지 전파 대기).

    URL이 로그에 찍힌 직후엔 DNS 전파 전이라 getaddrinfo가 NXDOMAIN을 반환하고
    OS가 그 부정 결과를 캐시할 수 있다. 그래서 폴링 시작 전에 grace초 대기해
    전파 시간을 벌고, 매 시도 전 hostname을 먼저 resolve해 도달 가능성을 본다.
    """
    host = urlsplit(url).hostname or ""
    time.sleep(grace)
    deadline = time.monotonic() + timeout
    last_err = ""
    while time.monotonic() < deadline:
        try:
            socket.gethostbyname(host)  # DNS부터 확인 (부정 캐시 회피용 선검사)
            r = httpx.get(f"{url}/.well-known/jwks.json", timeout=5.0)
            if r.status_code == 200:
                return
            last_err = f"status {r.status_code}"
        except (httpx.HTTPError, OSError) as exc:
            last_err = str(exc)
        time.sleep(2.0)
    raise SystemExit(f"터널이 {timeout}초 안에 외부 도달 가능 상태가 되지 않았습니다 ({last_err}).")


async def _local_self_check(settings: Settings, base_url: str, *, username: str,
                            password: str, page_size: int) -> str:
    """로컬 서버에서 로그인→토큰→userinfo/patients. 발급한 access_token 반환."""
    redirect_uri = settings.saylog_redirect_uri
    client_id = settings.saylog_client_id
    client_secret = settings.saylog_client_secret.get_secret_value()

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
        try:
            authorize = await http.post(
                "/authorize",
                params={
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "state": "e2e",
                    "scope": "openid profile",
                },
                data={"username": username, "password": password},
            )
        except httpx.ConnectError:
            raise SystemExit(
                f"샘플 서버에 연결하지 못했습니다 ({base_url}).\n"
                "먼저 다른 터미널에서 서버를 실행하세요: uv run python -m app\n"
                "다른 포트/호스트면 --base-url 로 지정하세요.",
            ) from None
        if authorize.status_code != 302:
            raise SystemExit(f"authorize 실패 ({authorize.status_code}): {authorize.text}")
        code = parse_qs(urlsplit(authorize.headers["location"]).query).get("code", [""])[0]
        if not code:
            raise SystemExit(f"Location에 code가 없습니다: {authorize.headers['location']}")

        token_resp = await http.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        token_resp.raise_for_status()
        access_token = str(token_resp.json()["access_token"])

        auth = {"Authorization": f"Bearer {access_token}"}
        userinfo = await http.get("/api/userinfo", headers=auth)
        userinfo.raise_for_status()
        patients = await http.get(
            "/api/patients", params={"page": 1, "pageSize": page_size}, headers=auth,
        )
        patients.raise_for_status()

    print("✓ [1/3] 로컬 자가확인 — 토큰 발급 + 환자 조회 성공")
    print(f"    userinfo: {json.dumps(userinfo.json(), ensure_ascii=False)}")
    pj = patients.json()
    print(f"    patients: totalCount={pj.get('totalCount')}, "
          f"첫 환자={pj['patients'][0]['patientUid'] if pj.get('patients') else '없음'}")
    return access_token


async def main() -> None:
    settings = get_settings()
    default_base = f"http://{settings.host}:{settings.port}"

    parser = argparse.ArgumentParser(
        description="로컬 자가확인 → 새록 등록 → 새록 경유 검증을 한 번에 실행한다.",
    )
    parser.add_argument("--base-url", default=default_base,
                        help=f"로컬 샘플 서버 URL (기본: {default_base})")
    parser.add_argument("--username", default="lee@hospital.com", help="로그인 사용자")
    parser.add_argument("--password", default="password", help="로그인 비밀번호")
    parser.add_argument("--page-size", type=int, default=10, help="환자 목록 pageSize")
    parser.add_argument("--with-webhook", action="store_true",
                        help="웹훅도 등록 (파트너 선택 사항)")
    parser.add_argument("--with-tunnel", action="store_true",
                        help="cloudflared 터널을 자동으로 띄워 PUBLIC_BASE_URL로 사용")
    parser.add_argument("--skip-validate", action="store_true",
                        help="새록 경유 검증(3단계) 생략")
    args = parser.parse_args()

    local_base = args.base_url.rstrip("/")

    # 1. 로컬 자가확인 (cloudflared 불필요)
    user_token = await _local_self_check(
        settings, local_base,
        username=args.username, password=args.password, page_size=args.page_size,
    )

    # 2·3은 DOU Connect 자격증명이 필요하므로 여기서 로드 (없으면 안내 후 종료)
    connect_settings = load_settings()

    # --with-tunnel이면 cloudflared를 띄워 그 공인 URL을 등록 base로 사용하고,
    # 아니면 .env의 PUBLIC_BASE_URL을 그대로 쓴다. 터널은 등록·검증 동안만 살아 있으면 된다.
    tunnel_cm = (
        cloudflared_tunnel(local_base) if args.with_tunnel
        else contextlib.nullcontext(connect_settings.public_base_url)
    )
    with tunnel_cm as public_url:
        await _register_and_validate(
            connect_settings, base=public_url.rstrip("/"), user_token=user_token,
            with_webhook=args.with_webhook, skip_validate=args.skip_validate,
        )


async def _register_and_validate(
    connect_settings: Settings, *, base: str, user_token: str,
    with_webhook: bool, skip_validate: bool,
) -> None:
    idp_request = IdentityProviderRequest.model_validate({
        "authorization_url": f"{base}/authorize",
        "token_url": f"{base}/token",
        "user_info_url": f"{base}/api/userinfo",
        "user_patients_url": f"{base}/api/patients",
        "client_id": connect_settings.saylog_client_id,
        "client_secret": connect_settings.saylog_client_secret.get_secret_value(),
        "scopes": ["openid", "profile"],
    })

    webhook_secret: str | None = None
    async with connect_client(connect_settings) as client:
        # 2. 등록
        await client.register_identity_provider(idp_request)
        print(f"✓ [2/3] Identity Provider 등록 완료 ({base})")
        if with_webhook:
            try:
                result = await client.register_webhook(url=f"{base}/webhook/saylog")
                webhook_secret = result.secret
                print(f"    + Webhook 등록 (webhookId={result.webhook_id})")
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 409:
                    raise
                print(f"    + Webhook 이미 등록됨 ({base}/webhook/saylog) — 재등록 생략. "
                      "secret을 다시 받으려면 기존 웹훅 삭제 후 실행하세요.")

        # 3. 새록 경유 검증
        if not skip_validate:
            report = await client.validate_partner_api(user_token)
            print("✓ [3/3] 새록 경유 API 스펙 검증 리포트:")
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print("• [3/3] 새록 경유 검증 생략 (--skip-validate)")

    if webhook_secret is not None:
        print()
        print("⚠ 웹훅 secret은 한 번만 노출됩니다. .env에 저장 후 서버를 재시작하세요:")
        print(f"    WEBHOOK_SECRET={webhook_secret}")


if __name__ == "__main__":
    asyncio.run(main())
