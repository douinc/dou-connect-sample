import hashlib
import hmac
import json
import logging
import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.dependencies import build_app_state
from app.main import create_app
from app.webhook.router import FRESHNESS_TOLERANCE_SECONDS


def _sign(secret: str, timestamp: str, body: bytes) -> str:
    signed_input = f"{timestamp}.".encode() + body
    return "sha256=" + hmac.new(secret.encode(), signed_input, hashlib.sha256).hexdigest()


def _now_ts() -> str:
    return str(int(time.time()))


def _make_client(webhook_secret: str) -> AsyncClient:
    settings = Settings(  # type: ignore[call-arg]
        saylog_client_id="saylog-client",
        saylog_client_secret="s3cret",  # type: ignore[arg-type]
        saylog_redirect_uri="http://cb.test/callback",
        webhook_secret=webhook_secret,  # type: ignore[arg-type]
    )
    state = build_app_state(settings)
    app = create_app(state)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def webhook_client():
    async with _make_client("webhook-secret-1234") as c:
        yield c


@pytest.mark.asyncio
async def test_valid_signature_returns_200(webhook_client: AsyncClient):
    ts = _now_ts()
    body = json.dumps({
        "event": "records.summarized",
        "timestamp": ts,
        "data": {"recordId": "rec_001"},
    }).encode()
    r = await webhook_client.post(
        "/webhook/saylog",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Saylog-Signature": _sign("webhook-secret-1234", ts, body),
            "X-Saylog-Timestamp": ts,
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_missing_signature_returns_401(webhook_client: AsyncClient):
    r = await webhook_client.post(
        "/webhook/saylog",
        content=b'{"event":"x"}',
        headers={
            "Content-Type": "application/json",
            "X-Saylog-Timestamp": _now_ts(),
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_missing_timestamp_header_returns_401(webhook_client: AsyncClient):
    ts = _now_ts()
    body = b'{"event":"records.summarized","data":{"recordId":"r1"}}'
    r = await webhook_client.post(
        "/webhook/saylog",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Saylog-Signature": _sign("webhook-secret-1234", ts, body),
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_bad_signature_returns_401(webhook_client: AsyncClient):
    ts = _now_ts()
    body = b'{"event":"records.summarized","data":{"recordId":"r1"}}'
    r = await webhook_client.post(
        "/webhook/saylog",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Saylog-Signature": _sign("WRONG", ts, body),
            "X-Saylog-Timestamp": ts,
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_tampered_timestamp_returns_401(webhook_client: AsyncClient):
    ts = _now_ts()
    body = b'{"event":"records.summarized","data":{"recordId":"r1"}}'
    r = await webhook_client.post(
        "/webhook/saylog",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Saylog-Signature": _sign("webhook-secret-1234", ts, body),
            "X-Saylog-Timestamp": str(int(ts) + 1),
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_non_ascii_signature_header_returns_401(webhook_client: AsyncClient):
    # 비ASCII 서명 헤더가 500(TypeError)이 아니라 401로 거절되는지 회귀 확인
    body = b'{"event":"records.summarized","data":{"recordId":"r1"}}'
    r = await webhook_client.post(
        "/webhook/saylog",
        content=body,
        headers=[
            (b"content-type", b"application/json"),
            (b"saylog-signature", "sha256=café".encode("latin-1")),
            (b"x-saylog-timestamp", _now_ts().encode()),
        ],
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_stale_timestamp_returns_401(webhook_client: AsyncClient):
    ts = str(int(time.time()) - FRESHNESS_TOLERANCE_SECONDS - 1)
    body = b'{"event":"records.summarized","data":{"recordId":"r1"}}'
    r = await webhook_client.post(
        "/webhook/saylog",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Saylog-Signature": _sign("webhook-secret-1234", ts, body),
            "X-Saylog-Timestamp": ts,
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_non_numeric_timestamp_returns_401(webhook_client: AsyncClient):
    ts = "2026-01-01T00:00:00Z"  # ISO 8601은 실계약 위반 — 숫자 형식 강제
    body = b'{"event":"records.summarized","data":{"recordId":"r1"}}'
    r = await webhook_client.post(
        "/webhook/saylog",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Saylog-Signature": _sign("webhook-secret-1234", ts, body),
            "X-Saylog-Timestamp": ts,
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_name",
    ["records.summarized", "records.transcribed", "records.updated", "records.deleted"],
)
async def test_known_events_return_200_and_dispatch(
    webhook_client: AsyncClient, caplog: pytest.LogCaptureFixture, event_name: str
):
    ts = _now_ts()
    body = json.dumps({
        "event": event_name,
        "timestamp": ts,
        "data": {"recordId": "rec_001", "source": "saylog-mobile"},
    }).encode()
    with caplog.at_level(logging.INFO):
        r = await webhook_client.post(
            "/webhook/saylog",
            content=body,
            headers={
                "Content-Type": "application/json",
                "Saylog-Signature": _sign("webhook-secret-1234", ts, body),
                "X-Saylog-Timestamp": ts,
            },
        )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert f"{event_name}: rec_001 (source=saylog-mobile)" in caplog.text


@pytest.mark.asyncio
async def test_unknown_event_returns_200_and_is_ignored(
    webhook_client: AsyncClient, caplog: pytest.LogCaptureFixture
):
    # forward-compat: 미지 이벤트는 재시도를 유발하지 않도록 2xx로 무시
    ts = _now_ts()
    body = json.dumps({
        "event": "records.future_event",
        "timestamp": ts,
        "data": {"recordId": "rec_001", "source": "unknown"},
    }).encode()
    with caplog.at_level(logging.INFO):
        r = await webhook_client.post(
            "/webhook/saylog",
            content=body,
            headers={
                "Content-Type": "application/json",
                "Saylog-Signature": _sign("webhook-secret-1234", ts, body),
                "X-Saylog-Timestamp": ts,
            },
        )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert "ignored unknown event: records.future_event" in caplog.text


@pytest.mark.asyncio
async def test_payload_without_source_is_accepted(
    webhook_client: AsyncClient, caplog: pytest.LogCaptureFixture
):
    # 구 페이로드(source 없음)도 수용 — source는 unknown으로 처리
    ts = _now_ts()
    body = json.dumps({
        "event": "records.summarized",
        "timestamp": ts,
        "data": {"recordId": "rec_001"},
    }).encode()
    with caplog.at_level(logging.INFO):
        r = await webhook_client.post(
            "/webhook/saylog",
            content=body,
            headers={
                "Content-Type": "application/json",
                "Saylog-Signature": _sign("webhook-secret-1234", ts, body),
                "X-Saylog-Timestamp": ts,
            },
        )
    assert r.status_code == 200
    assert "records.summarized: rec_001 (source=unknown)" in caplog.text


@pytest.mark.asyncio
async def test_unknown_data_fields_are_ignored(webhook_client: AsyncClient):
    # forward-compat: data의 미지 필드는 무시하고 정상 처리
    ts = _now_ts()
    body = json.dumps({
        "event": "records.updated",
        "timestamp": ts,
        "data": {"recordId": "rec_001", "source": "connect-api", "futureField": {"x": 1}},
    }).encode()
    r = await webhook_client.post(
        "/webhook/saylog",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Saylog-Signature": _sign("webhook-secret-1234", ts, body),
            "X-Saylog-Timestamp": ts,
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_null_data_returns_200(webhook_client: AsyncClient):
    # data가 null이거나 recordId가 없어도 5xx를 내지 않고 무시
    ts = _now_ts()
    body = json.dumps({"event": "records.deleted", "timestamp": ts, "data": None}).encode()
    r = await webhook_client.post(
        "/webhook/saylog",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Saylog-Signature": _sign("webhook-secret-1234", ts, body),
            "X-Saylog-Timestamp": ts,
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_unconfigured_secret_returns_500():
    # 서버 설정 누락은 호출자 인증 실패(401)와 구분해 500으로 응답
    ts = _now_ts()
    body = b'{"event":"records.summarized","data":{"recordId":"r1"}}'
    async with _make_client("") as client:
        r = await client.post(
            "/webhook/saylog",
            content=body,
            headers={
                "Content-Type": "application/json",
                "Saylog-Signature": _sign("any", ts, body),
                "X-Saylog-Timestamp": ts,
            },
        )
    assert r.status_code == 500
