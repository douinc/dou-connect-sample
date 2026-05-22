"""로컬 OAuth flow 데모 — 샘플 서버를 HTTP로 끝까지 한 번 돌려본다.

A 세그먼트(새록 → 파트너) 흐름을 로컬에서 재현한다:
  1. POST /authorize 로 로그인 → 302 Location 헤더에서 인증 코드(code) 추출
  2. POST /token 으로 code ↔ access_token/refresh_token 교환
  3. 발급받은 토큰으로 GET /api/userinfo · /api/patients 호출

curl 한 줄 대신 쓰는 편의 스크립트다. 브라우저는 302를 자동으로 따라가
code를 콜백(새록)으로 넘겨버리지만, 이 스크립트는 redirect를 따라가지 않고
Location에서 code만 빼내므로 access_token까지 직접 확인할 수 있다.

BASE_URL/자격증명/redirect_uri는 .env(HOST·PORT·SAYLOG_*)에서 읽으므로
curl 예제처럼 값을 따로 맞출 필요가 없다. 서버가 떠 있어야 한다(uv run python -m app).

사용법:
    uv run python -m app                     # 별도 터미널에서 서버 실행
    uv run python scripts/local_oauth_demo.py
    uv run python scripts/local_oauth_demo.py --username kim@hospital.com
"""
from __future__ import annotations

import argparse
import asyncio
import json
from urllib.parse import parse_qs, urlsplit

import httpx

from app.config import get_settings


async def main() -> None:
    settings = get_settings()
    default_base = f"http://{settings.host}:{settings.port}"

    parser = argparse.ArgumentParser(
        description="샘플 서버를 상대로 OAuth flow를 끝까지 실행해 토큰과 API 응답을 출력한다.",
    )
    parser.add_argument(
        "--base-url",
        default=default_base,
        help=f"샘플 서버 base URL (기본: .env HOST/PORT → {default_base})",
    )
    parser.add_argument(
        "--username", default="lee@hospital.com", help="로그인 사용자 (시드 계정)",
    )
    parser.add_argument("--password", default="password", help="로그인 비밀번호")
    parser.add_argument(
        "--page-size", type=int, default=10, help="환자 목록 pageSize",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    redirect_uri = settings.saylog_redirect_uri
    client_id = settings.saylog_client_id
    client_secret = settings.saylog_client_secret.get_secret_value()

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
        # 1. 로그인 → 302 Location 헤더에서 code 추출 (redirect 비추종)
        try:
            authorize = await http.post(
                "/authorize",
                params={
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "state": "demo",
                    "scope": "openid profile",
                },
                data={"username": args.username, "password": args.password},
            )
        except httpx.ConnectError:
            raise SystemExit(
                f"샘플 서버에 연결하지 못했습니다 ({base_url}).\n"
                "먼저 다른 터미널에서 서버를 실행하세요:\n"
                "    uv run python -m app\n"
                "다른 포트/호스트로 떠 있으면 --base-url 로 지정하세요.",
            ) from None
        if authorize.status_code != 302:
            raise SystemExit(
                f"authorize 실패 ({authorize.status_code}): {authorize.text}",
            )
        location = authorize.headers["location"]
        code = parse_qs(urlsplit(location).query).get("code", [""])[0]
        if not code:
            raise SystemExit(f"Location에 code가 없습니다: {location}")
        print(f"1. code = {code}")

        # 2. 토큰 교환
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
        tokens = token_resp.json()
        print("2. token 응답:")
        print(json.dumps(tokens, indent=2, ensure_ascii=False))
        access_token = tokens["access_token"]

        auth_header = {"Authorization": f"Bearer {access_token}"}

        # 3. 사용자 정보
        userinfo = await http.get("/api/userinfo", headers=auth_header)
        userinfo.raise_for_status()
        print("3. /api/userinfo:")
        print(json.dumps(userinfo.json(), indent=2, ensure_ascii=False))

        # 4. 환자 목록
        patients = await http.get(
            "/api/patients",
            params={"page": 1, "pageSize": args.page_size},
            headers=auth_header,
        )
        patients.raise_for_status()
        print("4. /api/patients:")
        print(json.dumps(patients.json(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
