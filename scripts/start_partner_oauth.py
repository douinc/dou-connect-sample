"""dou-connect를 거쳐 saylog 서비스의 partner OAuth flow를 시작.

이 스크립트는 파트너 서버 입장에서 사용자 OAuth 라운드트립을 자체 검증할 때 쓴다.
실행하면:
  1. dou-connect에 client-credentials로 토큰 발급
  2. dou-connect 게이트웨이를 통해 saylog의 partner-oauth/start 호출
  3. 응답으로 받은 authorizationUrl을 출력 (브라우저로 열어 로그인 흐름 검증)

토큰 claim의 partner_id가 자동으로 사용되므로 본문 인자 없음.

사용법:
    uv run python scripts/start_partner_oauth.py
"""
from __future__ import annotations

import asyncio

from scripts._common import connect_client, load_settings


async def main() -> None:
    settings = load_settings()

    async with connect_client(settings) as client:
        result = await client.start_partner_oauth()

    print("✓ Partner OAuth flow 시작")
    print(f"  authorizationUrl: {result.get('authorizationUrl')}")
    print(f"  nonce:            {result.get('nonce')}")
    print()
    print("위 authorizationUrl을 브라우저로 열어 파트너 OAuth 로그인을 진행하세요.")
    print("완료 후 dou-connect 게이트웨이의 콜백 경로로 redirect됩니다.")


if __name__ == "__main__":
    asyncio.run(main())
