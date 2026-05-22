from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.dependencies import build_app_state
from app.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        saylog_client_id="saylog-client",
        saylog_client_secret="s3cret",  # type: ignore[arg-type]
        saylog_redirect_uri="http://cb.test/callback",
        jwt_issuer="http://test/oauth",
        jwt_access_token_ttl=3600,
        jwt_refresh_token_ttl=86400,
    )


@pytest.fixture
async def client(test_settings: Settings) -> AsyncIterator[AsyncClient]:
    state = build_app_state(test_settings)
    app = create_app(state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
