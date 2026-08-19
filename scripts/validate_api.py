"""파트너 API 스펙 자동 검증 — POST saylog/v1/validate-partner-api.

등록된 항목만 검증된다. 모드에 따라 넘길 것이 다르다:

  사용자 토큰 모드 (oauth 등록)      --partner-user-token — 파트너 OAuth에 **사용자**가
                                     로그인해 받은 access token. 새록이 그 토큰으로
                                     userInfoUrl·endpoints.patients를 호출한다.
                                     dou-connect 클라이언트 토큰이 아니다.
  서비스 토큰 모드 / employee        --sample-employee-id(·--sample-name) — 새록이
                                     dou-connect 서비스 토큰을 직접 발급받아 호출하고,
                                     본문 sample로 검증용 사번·이름을 받는다.
                                     생략하면 해당 항목은 skipped.

사용자 토큰 발급 방법: scripts/local_oauth_demo.py 출력의 access_token (README §2.3).

사용법:
    uv run python scripts/validate_api.py --partner-user-token <access_token>
    uv run python scripts/validate_api.py --sample-employee-id 12345 --sample-name 이의사
"""
from __future__ import annotations

import argparse
import asyncio
import json

from scripts._common import connect_client, load_settings


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "새록의 파트너 API 스펙 검증을 실행한다. 사용자 토큰 모드 항목은 "
            "--partner-user-token, 서비스 토큰 모드 항목(직원 조회 포함)은 "
            "--sample-employee-id/--sample-name으로 검증한다."
        ),
    )
    parser.add_argument(
        "--partner-user-token",
        help=(
            "파트너 OAuth 서버에서 **사용자**가 로그인해 발급받은 access token "
            "(oauth를 등록한 파트너의 userInfoUrl·patients 검증용)."
        ),
    )
    parser.add_argument(
        "--sample-employee-id",
        help="서비스 토큰 모드 검증용 사번 (가능하면 테스트용 직원 데이터).",
    )
    parser.add_argument("--sample-name", help="직원 조회 검증용 이름.")
    args = parser.parse_args()

    if not args.partner_user_token and not args.sample_employee_id:
        parser.error("--partner-user-token 또는 --sample-employee-id 중 하나는 필요합니다.")

    settings = load_settings()
    async with connect_client(settings) as client:
        result = await client.validate_partner_api(
            args.partner_user_token,
            sample_employee_id=args.sample_employee_id,
            sample_name=args.sample_name,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
