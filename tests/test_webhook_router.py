import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.dependencies import build_app_state
from app.main import create_app


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
async def webhook_client():
    settings = Settings(  # type: ignore[call-arg]
        saylog_client_id="saylog-client",
        saylog_client_secret="s3cret",  # type: ignore[arg-type]
        saylog_redirect_uri="http://cb.test/callback",
        webhook_secret="webhook-secret-1234",  # type: ignore[arg-type]
    )
    state = build_app_state(settings)
    app = create_app(state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_valid_signature_returns_200(webhook_client: AsyncClient):
    body = json.dumps({
        "event": "records.summarized",
        "timestamp": "2026-01-01T00:00:00Z",
        "data": {"recordId": "rec_001"},
    }).encode()
    r = await webhook_client.post(
        "/webhook/saylog",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Saylog-Signature": _sign("webhook-secret-1234", body),
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_missing_signature_returns_401(webhook_client: AsyncClient):
    r = await webhook_client.post(
        "/webhook/saylog",
        content=b'{"event":"x"}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_bad_signature_returns_401(webhook_client: AsyncClient):
    body = b'{"event":"records.summarized","data":{"recordId":"r1"}}'
    r = await webhook_client.post(
        "/webhook/saylog",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Saylog-Signature": _sign("WRONG", body),
        },
    )
    assert r.status_code == 401
