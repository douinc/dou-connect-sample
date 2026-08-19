from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.dependencies import AppState, build_app_state
from app.main import create_app
from tests._service_tokens import AUDIENCE, PROVIDER_CODE, ServiceTokenIssuer


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "saylog_client_id": "saylog-client",
        "saylog_client_secret": "s3cret",
        "saylog_redirect_uri": "http://cb.test/callback",
        "jwt_issuer": "http://test/oauth",
        "jwt_access_token_ttl": 3600,
        "jwt_refresh_token_ttl": 86400,
        # 서비스 토큰 모드(직원 조회·service 모드 환자 목록) — 새록에 등록한 service.audience
        "service_token_audience": AUDIENCE,
        "dou_connect_provider_code": PROVIDER_CODE,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def test_settings() -> Settings:
    return make_settings()


@pytest.fixture
def service_issuer() -> ServiceTokenIssuer:
    """dou-connect 역할 — 서비스 토큰 발급 + 그 공개키로 만든 검증기."""
    return ServiceTokenIssuer()


def make_state(settings: Settings, service_issuer: ServiceTokenIssuer) -> AppState:
    state = build_app_state(settings)
    # 실제 JWKS 대신 테스트 키로 검증
    state.service_verifier = service_issuer.verifier(audience=settings.service_token_audience)
    return state


@pytest.fixture
def app_state(test_settings: Settings, service_issuer: ServiceTokenIssuer) -> AppState:
    return make_state(test_settings, service_issuer)


@pytest.fixture
async def client(app_state: AppState) -> AsyncIterator[AsyncClient]:
    app = create_app(app_state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
