"""테스트용 dou-connect 서비스 토큰 발급기 — Ed25519 키쌍 + PyJWKClient 대역."""
from __future__ import annotations

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.api.service_token import ServiceTokenVerifier

ISSUER = "https://connect.test"
AUDIENCE = "partner-emr"
PROVIDER_CODE = "HOSP-1"


class FakeKeySource:
    """PyJWKClient 대역 — 토큰 header의 kid로 미리 등록한 공개키를 돌려준다."""

    def __init__(self, keys: dict[str, dict[str, Any]]) -> None:
        self._keys = keys

    def get_signing_key_from_jwt(self, token: str) -> Any:
        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self._keys:
            raise jwt.PyJWKClientError(f"Unable to find a signing key that matches: {kid!r}")
        return jwt.PyJWK.from_dict(self._keys[kid])


class ServiceTokenIssuer:
    """dou-connect 역할: 서비스 토큰을 EdDSA로 서명하고, 그 공개키로 검증기를 만든다."""

    def __init__(self, kid: str = "k1") -> None:
        self.kid = kid
        self.private_key = ed25519.Ed25519PrivateKey.generate()
        pub = self.private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
        self.jwk: dict[str, Any] = {
            "kty": "OKP", "crv": "Ed25519", "kid": kid, "alg": "EdDSA", "use": "sig",
            "x": jwt.utils.base64url_encode(pub).decode("ascii"),
        }

    def verifier(self, *, audience: str = AUDIENCE) -> ServiceTokenVerifier:
        return ServiceTokenVerifier(
            issuer=ISSUER, audience=audience, key_source=FakeKeySource({self.kid: self.jwk}),
        )

    def mint(self, *, alg: str = "EdDSA", **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER, "aud": AUDIENCE, "sub": "client-uuid", "org_id": "org-1",
            "scopes": ["staff:read", "patients:read"], "mode": "test",
            "provider_code": PROVIDER_CODE, "jti": "jti-1",
            "iat": now, "nbf": now, "exp": now + 900,
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(
            claims, self.private_key, algorithm=alg, headers={"kid": self.kid, "typ": "at+jwt"},
        )
