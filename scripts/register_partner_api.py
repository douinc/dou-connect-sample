"""파트너 API(새록이 호출할 자사 주소·자격)를 새록에 등록 — PUT saylog/v1/partner-api.

두 가지 등록 형태를 지원한다 (가이드 "파트너 API 등록"의 두 예시와 동일):

  IdP 포함(기본)        oauth 그룹(authorizationUrl·tokenUrl·userInfoUrl·clientId·
                        clientSecret·scopes — 전부 필수) + endpoints.patients(+employee).
                        patients는 사용자 토큰 모드(auth=user)로 호출된다.
  --mode service        oauth 없이 service.audience + endpoints.employee/patients.
                        새록이 dou-connect 서비스 토큰으로 호출한다(auth=service).
                        SERVICE_TOKEN_AUDIENCE 설정 필요.

PUT은 전체 교체(부분 갱신 없음) — oauth를 유지하려면 매 등록에 clientSecret 원문을
다시 포함해야 하고, 생략하면 IdP 등록이 삭제된다.

사용법:
    uv run python scripts/register_partner_api.py                 # IdP 포함 등록
    uv run python scripts/register_partner_api.py --mode service  # 서비스 토큰 모드만
"""
from __future__ import annotations

import argparse
import asyncio

from app.config import Settings
from app.connect.schemas import (
    PartnerApiEndpoint,
    PartnerApiEndpoints,
    PartnerApiOAuth,
    PartnerApiRequest,
    PartnerApiService,
)
from scripts._common import connect_client, load_settings


def build_request(*, base: str, mode: str, settings: Settings) -> PartnerApiRequest:
    endpoints = PartnerApiEndpoints(
        patients=PartnerApiEndpoint(url=f"{base}/api/patients"),
        employee=PartnerApiEndpoint(url=f"{base}/api/employee"),
    )
    if mode == "service":
        audience = settings.service_token_audience
        if not audience:
            raise SystemExit(
                "--mode service에는 SERVICE_TOKEN_AUDIENCE가 .env에 설정되어야 합니다 "
                "(dou-connect에 리소스 서버를 등록할 때 정한 audience).",
            )
        return PartnerApiRequest(service=PartnerApiService(audience=audience), endpoints=endpoints)
    # IdP 포함: patients는 사용자 토큰 모드가 되므로 service.audience는 employee에만 필요.
    # 샘플은 employee도 함께 등록하므로 audience가 설정돼 있으면 같이 보낸다.
    service = (
        PartnerApiService(audience=settings.service_token_audience)
        if settings.service_token_audience else None
    )
    if service is None:
        # employee는 서비스 토큰 전용이라 audience 없이는 등록할 수 없다
        endpoints = PartnerApiEndpoints(patients=endpoints.patients)
    return PartnerApiRequest(
        service=service,
        oauth=PartnerApiOAuth(
            authorizationUrl=f"{base}/authorize",
            tokenUrl=f"{base}/token",
            userInfoUrl=f"{base}/api/userinfo",
            clientId=settings.saylog_client_id,
            clientSecret=settings.saylog_client_secret.get_secret_value(),
            scopes=["openid", "profile"],
        ),
        endpoints=endpoints,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="파트너 API를 새록에 등록한다 (PUT 전체 교체).")
    parser.add_argument(
        "--mode", choices=["oauth", "service"], default="oauth",
        help="oauth(기본): IdP 로그인 위임 포함 / service: IdP 없이 서비스 토큰 모드만",
    )
    args = parser.parse_args()

    settings = load_settings()
    base = settings.public_base_url.rstrip("/")
    request = build_request(base=base, mode=args.mode, settings=settings)

    async with connect_client(settings) as client:
        result = await client.register_partner_api(request)

    print("✓ 파트너 API 등록 완료")
    if result.oauth is not None:
        print(f"  oauth.authorizationUrl: {result.oauth.authorization_url}")
        print(f"  oauth.redirectUri(새록 콜백): {result.oauth.redirect_uri}")
    if result.service is not None:
        print(f"  service.audience: {result.service.audience}")
    for key in ("patients", "employee"):
        ep = getattr(result.endpoints, key)
        if ep is not None:
            print(f"  endpoints.{key}: {ep.url} (auth={ep.auth})")


if __name__ == "__main__":
    asyncio.run(main())
