"""파트너 OAuth/API URL을 새록(identity-provider)에 등록.

사용법:
    uv run python scripts/register_idp.py
"""
from __future__ import annotations

import asyncio

from app.connect.schemas import IdentityProviderRequest
from scripts._common import connect_client, load_settings


async def main() -> None:
    settings = load_settings()
    base = settings.public_base_url.rstrip("/")

    request = IdentityProviderRequest.model_validate({
        "authorization_url": f"{base}/authorize",
        "token_url": f"{base}/token",
        "user_info_url": f"{base}/api/userinfo",
        "user_patients_url": f"{base}/api/patients",
        "client_id": settings.saylog_client_id,
        "client_secret": settings.saylog_client_secret.get_secret_value(),
        "scopes": ["openid", "profile"],
    })

    async with connect_client(settings) as client:
        result = await client.register_identity_provider(request)

    print("✓ Identity Provider 등록 완료")
    print(f"  authorizationUrl: {request.authorization_url}")
    print(f"  tokenUrl:         {request.token_url}")
    print(f"  userInfoUrl:      {request.user_info_url}")
    print(f"  userPatientsUrl:  {request.user_patients_url}")
    print(f"  서버 응답: {result}")


if __name__ == "__main__":
    asyncio.run(main())
