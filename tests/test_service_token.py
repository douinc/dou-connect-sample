"""dou-connect 서비스 토큰 검증기 — 리소스 서버 가이드의 필수 검증 항목(EdDSA·kid·iss·aud·exp·nbf·scopes)."""
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from fastapi import HTTPException

from app.api.service_token import ServiceTokenError, ServiceTokenVerifier, require_service_token

ISSUER = "https://connect.test"
AUDIENCE = "partner-emr"


class FakeKeySource:
    """PyJWKClient 대역 — 토큰 header의 kid로 미리 등록한 공개키를 돌려준다."""

    def __init__(self, keys: dict[str, Any]) -> None:
        self._keys = keys

    def get_signing_key_from_jwt(self, token: str) -> Any:
        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self._keys:
            raise jwt.PyJWKClientError(f"Unable to find a signing key that matches: {kid!r}")
        return jwt.PyJWK.from_dict(self._keys[kid])


def _ed25519_pair(kid: str) -> tuple[ed25519.Ed25519PrivateKey, dict[str, Any]]:
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    return priv, {
        "kty": "OKP", "crv": "Ed25519", "kid": kid, "alg": "EdDSA", "use": "sig",
        "x": jwt.utils.base64url_encode(pub).decode("ascii"),
    }


def _mint(priv: ed25519.Ed25519PrivateKey, kid: str, *, alg: str = "EdDSA", **overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER, "aud": AUDIENCE, "sub": "client-uuid", "org_id": "org-1",
        "scopes": ["staff:read", "patients:read"], "mode": "test",
        "provider_code": "HOSP-1", "jti": "jti-1",
        "iat": now, "nbf": now, "exp": now + 900,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, priv, algorithm=alg, headers={"kid": kid, "typ": "at+jwt"})


@pytest.fixture
def keypair():
    return _ed25519_pair("k1")


@pytest.fixture
def verifier(keypair):
    _, jwk = keypair
    return ServiceTokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, key_source=FakeKeySource({"k1": jwk}),
    )


def test_valid_token_returns_claims(verifier, keypair):
    priv, _ = keypair
    claims = verifier.verify(_mint(priv, "k1"), required_scope="staff:read")
    assert claims["aud"] == AUDIENCE
    assert claims["provider_code"] == "HOSP-1"


def test_missing_scope_is_insufficient_scope_403(verifier, keypair):
    priv, _ = keypair
    with pytest.raises(ServiceTokenError) as exc:
        verifier.verify(_mint(priv, "k1", scopes=["patients:read"]), required_scope="staff:read")
    assert exc.value.status == 403
    assert exc.value.error == "insufficient_scope"
    assert exc.value.scope == "staff:read"


@pytest.mark.parametrize("override", [
    {"aud": "saylog"},                   # 다른 서비스용 토큰 (confused deputy)
    {"iss": "https://evil.test"},
    {"exp": int(time.time()) - 10},      # 만료
    {"nbf": int(time.time()) + 600},     # early-use
    {"scopes": None},                    # 필수 클레임 누락
    {"exp": None},
])
def test_claim_violations_are_invalid_token_401(verifier, keypair, override):
    priv, _ = keypair
    with pytest.raises(ServiceTokenError) as exc:
        verifier.verify(_mint(priv, "k1", **override), required_scope="staff:read")
    assert exc.value.status == 401
    assert exc.value.error == "invalid_token"


def test_unknown_kid_is_invalid_token(verifier):
    priv, _ = _ed25519_pair("other")
    with pytest.raises(ServiceTokenError) as exc:
        verifier.verify(_mint(priv, "other"), required_scope="staff:read")
    assert exc.value.status == 401


def test_non_eddsa_algorithm_is_rejected(keypair):
    """algorithm confusion 방지 — RS256으로 서명된 토큰은 키가 맞아도 거부."""
    rsa_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_jwk = {
        **jwt.algorithms.RSAAlgorithm.to_jwk(rsa_priv.public_key(), as_dict=True),
        "kid": "rsa", "use": "sig", "alg": "RS256",
    }
    verifier = ServiceTokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, key_source=FakeKeySource({"rsa": rsa_jwk}),
    )
    now = int(time.time())
    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "c", "scopes": ["staff:read"],
         "iat": now, "nbf": now, "exp": now + 900},
        rsa_priv, algorithm="RS256", headers={"kid": "rsa"},
    )
    with pytest.raises(ServiceTokenError) as exc:
        verifier.verify(token, required_scope="staff:read")
    assert exc.value.status == 401


def test_garbage_token_is_invalid_token(verifier):
    with pytest.raises(ServiceTokenError) as exc:
        verifier.verify("not-a-jwt", required_scope="staff:read")
    assert exc.value.status == 401


# --- FastAPI 헬퍼: RFC 6750 WWW-Authenticate ---------------------------------

def test_require_service_token_missing_header_401_without_error(verifier):
    with pytest.raises(HTTPException) as exc:
        require_service_token(authorization=None, verifier=verifier, required_scope="staff:read")
    assert exc.value.status_code == 401
    assert exc.value.headers["WWW-Authenticate"] == 'Bearer realm="dou-connect-sample"'


def test_require_service_token_invalid_401_with_error(verifier):
    with pytest.raises(HTTPException) as exc:
        require_service_token(
            authorization="Bearer nope", verifier=verifier, required_scope="staff:read",
        )
    assert exc.value.status_code == 401
    assert 'error="invalid_token"' in exc.value.headers["WWW-Authenticate"]


def test_require_service_token_insufficient_scope_403(verifier, keypair):
    priv, _ = keypair
    token = _mint(priv, "k1", scopes=["patients:read"])
    with pytest.raises(HTTPException) as exc:
        require_service_token(
            authorization=f"Bearer {token}", verifier=verifier, required_scope="staff:read",
        )
    assert exc.value.status_code == 403
    www = exc.value.headers["WWW-Authenticate"]
    assert 'error="insufficient_scope"' in www and 'scope="staff:read"' in www


def test_require_service_token_returns_claims(verifier, keypair):
    priv, _ = keypair
    claims = require_service_token(
        authorization=f"Bearer {_mint(priv, 'k1')}", verifier=verifier, required_scope="staff:read",
    )
    assert claims["sub"] == "client-uuid"
