"""파트너 API 스펙 자동 검증.

이 스크립트는 **파트너 OAuth 사용자 토큰**을 새록에 전달해서, 새록이 그 토큰으로
파트너 `/api/userinfo` · `/api/patients`를 호출했을 때 응답이 새록 스펙에
맞는지 검사하도록 시킨다.

여기서 "토큰"은 두 가지 중 후자다:
  A. dou-connect 토큰 — 파트너 클라이언트(회사)를 식별. ConnectClient가 자동 발급.
  B. 파트너 사용자 토큰 — 파트너 OAuth에 **사용자**가 로그인해서 받은 토큰. ←
     이 스크립트가 받는 토큰은 B다. userInfo 검증은 사용자 컨텍스트가 필요하므로
     자동 발급이 불가능하고, 운영자가 직접 발급해서 전달해야 한다.

발급 방법: docs/manual-testing.md L2.2~L2.3 (브라우저 로그인 → code → /token 교환)

사용법:
    uv run python scripts/validate_api.py --partner-user-token <access_token>
"""
from __future__ import annotations

import argparse
import asyncio
import json

from scripts._common import connect_client, load_settings


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "새록의 파트너 API 스펙 검증을 실행한다. "
            "--partner-user-token에는 파트너 OAuth 서버에 사용자가 로그인해서 "
            "발급받은 access token을 넣는다 (dou-connect 클라이언트 토큰이 아님)."
        ),
    )
    parser.add_argument(
        "--partner-user-token",
        required=True,
        help=(
            "파트너 OAuth 서버에서 **사용자**가 로그인해 발급받은 access token. "
            "샘플의 경우 L2.2 브라우저 로그인 → L2.3 /token 교환으로 획득."
        ),
    )
    args = parser.parse_args()

    settings = load_settings()
    async with connect_client(settings) as client:
        result = await client.validate_partner_api(args.partner_user_token)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
