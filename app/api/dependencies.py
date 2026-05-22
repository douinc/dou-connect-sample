from typing import Any

from fastapi import HTTPException

from app.oauth.jwt_signer import JwtSigner


def verify_bearer_token(
    *,
    authorization: str | None,
    signer: JwtSigner,
    audience: str,
) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(None, 1)[1].strip()
    try:
        return signer.verify(token, audience=audience)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
