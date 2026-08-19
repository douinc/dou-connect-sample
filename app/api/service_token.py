"""dou-connect 서비스 토큰 검증 (새록 → 파트너 리소스 서버, 서비스 토큰 모드).

새록은 `endpoints.employee`(항상)와 `oauth` 없이 등록된 `endpoints.patients`를
dou-connect가 발급한 client_credentials 토큰(`aud=service.audience`)으로 호출한다.
파트너는 dou-connect JWKS로 그 토큰을 검증해야 하며, 필수 항목은 리소스 서버
가이드(/docs/dou-connect/resource-server-guide)를 따른다:

  alg == EdDSA → kid로 JWKS 공개키 → 서명 → iss → aud(정확 일치) → exp/nbf →
  scopes에 엔드포인트 요구 권한 포함 → (선택) provider_code로 병원 격리

python-jose는 EdDSA를 지원하지 않아 이 모듈만 PyJWT를 쓴다 (가이드의 Python 예시와
동일). 파트너 IdP 쪽(RS256 발급·검증)은 app/oauth/jwt_signer.py 그대로다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import jwt
from fastapi import HTTPException

REALM = "dou-connect-sample"
# 가이드 §검증 절차 1: 다른 알고리즘은 거부 (algorithm confusion 방지)
ALGORITHMS = ("EdDSA",)
REQUIRED_CLAIMS = ("iss", "aud", "sub", "exp", "iat", "nbf", "scopes")


class SigningKeySource(Protocol):
    """PyJWKClient 호환 — 토큰 header의 kid에 맞는 공개키를 돌려준다."""

    def get_signing_key_from_jwt(self, token: str) -> Any: ...


@dataclass(frozen=True)
class ServiceTokenError(Exception):
    """RFC 6750 오류 — status 401(invalid_token) 또는 403(insufficient_scope)."""

    status: int
    error: str
    description: str
    scope: str | None = None

    def www_authenticate(self) -> str:
        parts = [f'Bearer realm="{REALM}"', f'error="{self.error}"']
        if self.description:
            parts.append(f'error_description="{self.description}"')
        if self.scope:
            parts.append(f'scope="{self.scope}"')
        return ", ".join(parts)


class ServiceTokenVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        key_source: SigningKeySource,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._keys = key_source

    @classmethod
    def from_jwks_url(
        cls,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
    ) -> ServiceTokenVerifier:
        # JWKS set은 1시간 캐시(lifespan), 모르는 kid면 PyJWKClient가 즉시 재조회한다
        # (키 교체 직후 대응). cache_keys=True는 개별 서명 키를 lru_cache로 무기한
        # 잡아 두어 폐기된 kid가 계속 통과할 수 있으므로 쓰지 않는다.
        # jwks_url은 반드시 https여야 한다 — http면 공개키를 평문으로 받아 온다
        # (프로덕션 dou-connect는 https 고정, 이 검사는 설정 실수 방어).
        if jwks_url.startswith("http://") and "://localhost" not in jwks_url:
            raise ValueError("jwks_url must be https")
        return cls(
            issuer=issuer,
            audience=audience,
            key_source=jwt.PyJWKClient(jwks_url, lifespan=3600),
        )

    def verify(self, token: str, *, required_scope: str) -> dict[str, Any]:
        try:
            signing_key = self._keys.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": list(REQUIRED_CLAIMS)},
            )
        except jwt.PyJWTError as exc:
            # 어느 단계가 실패했는지 호출자에게 구분해 알리지 않는다 — 전부 invalid_token.
            raise ServiceTokenError(401, "invalid_token", "token verification failed") from exc

        # 가이드 검증 절차 중 이 샘플이 생략한 권장 항목 (실서비스에서는 검토하라):
        #  - jti 재사용 방지(재전송 방어) — 저장소가 필요해 샘플 범위 밖
        #  - mode 클레임(live/test)별 데이터 격리 — 단일 데이터셋 샘플이라 생략

        scopes = claims.get("scopes")
        if not isinstance(scopes, list) or required_scope not in scopes:
            raise ServiceTokenError(
                403,
                "insufficient_scope",
                "required scope missing",
                scope=required_scope,
            )
        return claims


def require_service_token(
    *,
    authorization: str | None,
    verifier: ServiceTokenVerifier,
    required_scope: str,
) -> dict[str, Any]:
    """Authorization 헤더를 검증해 claims를 돌려준다. 실패는 RFC 6750 §3 형식의
    WWW-Authenticate 헤더를 단 HTTPException."""
    if not authorization or not authorization.lower().startswith("bearer "):
        # 토큰 자체가 없을 때는 error 없이 realm만
        raise HTTPException(
            status_code=401,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": f'Bearer realm="{REALM}"'},
        )
    token = authorization.split(None, 1)[1].strip()
    try:
        return verifier.verify(token, required_scope=required_scope)
    except ServiceTokenError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail=exc.error,
            headers={"WWW-Authenticate": exc.www_authenticate()},
        ) from exc
