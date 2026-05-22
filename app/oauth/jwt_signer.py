from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt


class JwtSigner:
    def __init__(
        self,
        issuer: str,
        private_key_pem: bytes | None = None,
        public_key_pem: bytes | None = None,
        kid: str = "sample-key-1",
    ) -> None:
        self._issuer = issuer
        self._kid = kid

        if private_key_pem is None:
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            private_key_pem = key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            public_key_pem = key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        elif public_key_pem is None:
            loaded = serialization.load_pem_private_key(private_key_pem, password=None)
            public_key_pem = loaded.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )

        self._private_pem = private_key_pem
        self._public_pem = public_key_pem

    @classmethod
    def from_paths(
        cls,
        issuer: str,
        private_key_path: Path | None,
        public_key_path: Path | None,
        kid: str = "sample-key-1",
    ) -> "JwtSigner":
        private_pem = private_key_path.read_bytes() if private_key_path else None
        public_pem = public_key_path.read_bytes() if public_key_path else None
        return cls(
            issuer=issuer,
            private_key_pem=private_pem,
            public_key_pem=public_pem,
            kid=kid,
        )

    def sign_access_token(
        self,
        *,
        subject: str,
        audience: str,
        scope: str,
        client_id: str,
        issued_at: datetime,
        ttl_seconds: int,
    ) -> str:
        claims: dict[str, Any] = {
            "iss": self._issuer,
            "sub": subject,
            "aud": audience,
            "iat": int(issued_at.timestamp()),
            "exp": int(issued_at.timestamp()) + ttl_seconds,
            "scope": scope,
            "client_id": client_id,
        }
        return jwt.encode(
            claims,
            self._private_pem.decode(),
            algorithm="RS256",
            headers={"kid": self._kid},
        )

    def verify(self, token: str, *, audience: str) -> dict[str, Any]:
        return jwt.decode(
            token,
            self._public_pem.decode(),
            algorithms=["RS256"],
            audience=audience,
            issuer=self._issuer,
        )

    def jwks(self) -> dict[str, Any]:
        key = jwk.construct(self._public_pem.decode(), algorithm="RS256")
        data = key.to_dict()
        # Some python-jose versions return bytes for n/e; ensure strings
        normalized: dict[str, Any] = {
            k: v.decode("ascii") if isinstance(v, bytes) else v
            for k, v in data.items()
        }
        normalized.update({"kid": self._kid, "use": "sig", "alg": "RS256"})
        return {"keys": [normalized]}
