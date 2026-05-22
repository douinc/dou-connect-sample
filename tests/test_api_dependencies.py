from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.api.dependencies import verify_bearer_token
from app.oauth.jwt_signer import JwtSigner


def make_token(signer: JwtSigner, sub: str = "user-001") -> str:
    return signer.sign_access_token(
        subject=sub, audience="saylog", scope="openid",
        client_id="saylog-client",
        issued_at=datetime.now(UTC), ttl_seconds=3600,
    )


def test_verify_valid_bearer():
    signer = JwtSigner(issuer="http://test/oauth")
    token = make_token(signer)
    claims = verify_bearer_token(
        authorization=f"Bearer {token}",
        signer=signer,
        audience="saylog",
    )
    assert claims["sub"] == "user-001"


def test_missing_header_raises_401():
    signer = JwtSigner(issuer="http://test/oauth")
    with pytest.raises(HTTPException) as exc:
        verify_bearer_token(authorization=None, signer=signer, audience="saylog")
    assert exc.value.status_code == 401


def test_invalid_token_raises_401():
    signer = JwtSigner(issuer="http://test/oauth")
    with pytest.raises(HTTPException) as exc:
        verify_bearer_token(
            authorization="Bearer not-a-jwt",
            signer=signer, audience="saylog",
        )
    assert exc.value.status_code == 401


def test_wrong_scheme_raises_401():
    signer = JwtSigner(issuer="http://test/oauth")
    with pytest.raises(HTTPException) as exc:
        verify_bearer_token(
            authorization="Basic abc",
            signer=signer, audience="saylog",
        )
    assert exc.value.status_code == 401
