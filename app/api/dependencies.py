from typing import Any

from fastapi import HTTPException

from app.api.service_token import REALM
from app.oauth.jwt_signer import JwtSigner

# PHI 응답 공통 헤더 (가이드: 사용자 정보·환자 목록·직원 조회 모두 필수)
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def verify_bearer_token(
    *,
    authorization: str | None,
    signer: JwtSigner,
    audience: str,
) -> dict[str, Any]:
    """파트너 IdP(이 샘플의 OAuth 서버)가 발급한 사용자 토큰 검증. 실패는 RFC 6750 §3 헤더."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": f'Bearer realm="{REALM}"'},
        )
    token = authorization.split(None, 1)[1].strip()
    try:
        return signer.verify(token, audience=audience)
    except Exception as exc:
        raise HTTPException(
            status_code=401, detail="Invalid token",
            headers={"WWW-Authenticate": f'Bearer realm="{REALM}", error="invalid_token"'},
        ) from exc
