from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    public_base_url: str = "http://localhost:8000"

    saylog_client_id: str
    saylog_client_secret: SecretStr
    saylog_redirect_uri: str

    jwt_private_key_path: Path | None = None
    jwt_public_key_path: Path | None = None

    @field_validator("jwt_private_key_path", "jwt_public_key_path", mode="before")
    @classmethod
    def _empty_path_to_none(cls, v: Any) -> Any:
        return None if v == "" else v

    jwt_issuer: str = "http://localhost:8000/oauth"
    jwt_access_token_ttl: int = 3600
    jwt_refresh_token_ttl: int = 2592000

    dou_connect_base_url: str = "https://connect.dou.so"
    dou_connect_client_id: str = ""
    dou_connect_client_secret: SecretStr = SecretStr("")
    dou_connect_audience: str = "saylog"
    dou_connect_scope: str = ""
    dou_connect_provider_code: str = ""

    # === 새록 → 파트너 서비스 토큰 모드 (A 세그먼트) ===
    # 담당 환자 목록(endpoints.patients)을 어느 토큰으로 받을지. 새록은 등록 상태로 정해진
    # 한 모드로만 호출한다 — oauth 그룹을 등록했으면 user(파트너 IdP 사용자 토큰), 안 했으면
    # service(dou-connect 서비스 토큰). 직원 조회(endpoints.employee)는 항상 service.
    patients_auth_mode: Literal["user", "service"] = "user"
    # 파트너 리소스 서버가 dou-connect에 등록한 서비스의 aud — PUT /v1/partner-api 의
    # service.audience 와 같은 값. 비어 있으면 서비스 토큰 모드 엔드포인트가 500.
    service_token_audience: str = ""

    @property
    def dou_connect_issuer(self) -> str:
        # 서비스 토큰의 iss 는 dou-connect base URL 그대로 (리소스 서버 가이드)
        return self.dou_connect_base_url.rstrip("/")

    @property
    def dou_connect_jwks_url(self) -> str:
        return f"{self.dou_connect_issuer}/v1/oauth/.well-known/jwks.json"

    @field_validator("dou_connect_scope", mode="before")
    @classmethod
    def _normalize_scope(cls, v: Any) -> Any:
        # OAuth scope는 RFC 6749 §3.3에 따라 wire format이 space-delimited.
        # env var 컨벤션은 콤마이므로 입력 시 콤마/공백 혼용을 단일 공백으로
        # 정규화해 wire 그대로 통과시킨다.
        if not isinstance(v, str):
            return v
        return " ".join(part for part in v.replace(",", " ").split() if part)

    # 웹훅 secret은 등록 건마다 별도 발급된다 — 이벤트별로 등록하면 secret도
    # 그 수만큼 생기므로 콤마 구분 복수 값(WEBHOOK_SECRETS)을 받는다.
    # 단수 WEBHOOK_SECRET도 하위호환으로 함께 수용한다.
    webhook_secret: SecretStr = SecretStr("")
    webhook_secrets: SecretStr = SecretStr("")

    def webhook_secret_candidates(self) -> list[str]:
        """검증에 사용할 secret 후보 목록 (순서 유지, 중복·공백 제거)."""
        values = [s.strip() for s in self.webhook_secrets.get_secret_value().split(",")]
        values.append(self.webhook_secret.get_secret_value().strip())
        seen: set[str] = set()
        out: list[str] = []
        for v in values:
            if v and v not in seen:
                seen.add(v)
                out.append(v)
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
