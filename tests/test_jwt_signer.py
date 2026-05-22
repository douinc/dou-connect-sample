from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.oauth.jwt_signer import JwtSigner


@pytest.fixture
def signer() -> JwtSigner:
    return JwtSigner(issuer="http://test/oauth")


def test_sign_and_verify_round_trip(signer: JwtSigner):
    now = datetime.now(UTC)
    token = signer.sign_access_token(
        subject="user-001",
        audience="saylog",
        scope="openid profile",
        client_id="saylog-client",
        issued_at=now,
        ttl_seconds=3600,
    )
    claims = signer.verify(token, audience="saylog")
    assert claims["sub"] == "user-001"
    assert claims["scope"] == "openid profile"
    assert claims["client_id"] == "saylog-client"
    assert claims["iss"] == "http://test/oauth"


def test_expired_token_rejected(signer: JwtSigner):
    past = datetime.now(UTC) - timedelta(hours=2)
    token = signer.sign_access_token(
        subject="u", audience="saylog", scope="", client_id="c",
        issued_at=past, ttl_seconds=60,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        signer.verify(token, audience="saylog")


def test_jwks_exposes_public_key(signer: JwtSigner):
    jwks = signer.jwks()
    assert "keys" in jwks
    assert len(jwks["keys"]) == 1
    key = jwks["keys"][0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    assert "n" in key and "e" in key
    assert "d" not in key  # private 컴포넌트 미노출


def test_kid_consistent_between_token_and_jwks(signer: JwtSigner):
    token = signer.sign_access_token(
        subject="u", audience="saylog", scope="", client_id="c",
        issued_at=datetime.now(UTC), ttl_seconds=60,
    )
    header = jwt.get_unverified_header(token)
    jwks = signer.jwks()
    assert header["kid"] == jwks["keys"][0]["kid"]
