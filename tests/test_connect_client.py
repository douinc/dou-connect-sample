import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.connect.client import ConnectClient


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_issue_token_called_lazily():
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok1", "token_type": "Bearer", "expires_in": 900,
            })
        if req.url.path == "/api/saylog/v1/identity-provider":
            assert req.headers["authorization"] == "Bearer tok1"
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_identity_provider()
        assert any(r.url.path == "/v1/oauth/token" for r in calls)


@pytest.mark.asyncio
async def test_token_cached_between_calls():
    issued = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal issued
        if req.url.path == "/v1/oauth/token":
            issued += 1
            return httpx.Response(200, json={
                "access_token": f"tok{issued}", "token_type": "Bearer",
                "expires_in": 900,
            })
        return httpx.Response(200, json={})

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_identity_provider()
        await c.get_identity_provider()
    assert issued == 1


@pytest.mark.asyncio
async def test_401_triggers_token_refresh_once():
    state = {"issued": 0, "calls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            state["issued"] += 1
            return httpx.Response(200, json={
                "access_token": f"tok{state['issued']}",
                "token_type": "Bearer", "expires_in": 900,
            })
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(401, json={"error": "invalid_token"})
        return httpx.Response(200, json={"ok": True})

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_identity_provider()
    assert state["issued"] == 2
    assert state["calls"] == 2


@pytest.mark.asyncio
async def test_register_identity_provider_sends_camel_body():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"ok": True})

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        from app.connect.schemas import IdentityProviderRequest
        await c.register_identity_provider(IdentityProviderRequest(
            authorization_url="http://a", token_url="http://t",
            user_info_url="http://u", user_patients_url="http://p",
            client_id="c", client_secret="s",
            scopes=["openid", "profile"],
        ))
    assert "authorizationUrl" in seen["body"]
    assert "userPatientsUrl" in seen["body"]
    assert seen["body"]["scopes"] == ["openid", "profile"]


@pytest.mark.asyncio
async def test_token_request_uses_basic_auth_with_audience():
    """RFC 6749 §2.3.1 Basic 인증 + dou-connect의 audience 파라미터 검증.

    - Authorization: Basic <base64(client_id:client_secret)> 헤더 사용
    - 본문에는 grant_type, audience 만 (client_id/secret 절대 본문 X — 두 방식 동시 사용 시 invalid_request)
    - scope 지정 시 본문에 포함
    """
    seen_request: dict[str, httpx.Request] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            seen_request["req"] = req
            return httpx.Response(200, json={
                "access_token": "tok",
                "token_type": "Bearer",
                "expires_in": 900,
                "scope": "patients:read records:read",
            })
        return httpx.Response(200, json={"ok": True})

    async with ConnectClient(
        base_url="http://test",
        client_id="my-id", client_secret="my-secret",
        audience="saylog",
        scope="patients:read records:read",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_identity_provider()

    req = seen_request["req"]
    auth = req.headers["authorization"]
    assert auth.startswith("Basic ")
    decoded = base64.b64decode(auth.removeprefix("Basic ")).decode("ascii")
    assert decoded == "my-id:my-secret"

    body = parse_qs(req.content.decode("ascii"))
    assert body["grant_type"] == ["client_credentials"]
    assert body["audience"] == ["saylog"]
    assert body["scope"] == ["patients:read records:read"]
    assert "client_id" not in body
    assert "client_secret" not in body


@pytest.mark.asyncio
async def test_token_request_includes_provider_code_when_set():
    """tenant-required service(Service.requires_tenant=true)는 provider_code
    본문 파라미터 미지정 시 dou-connect가 403 access_denied로 거부한다.
    """
    seen: dict[str, httpx.Request] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            seen["req"] = req
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        return httpx.Response(200, json={"ok": True})

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        provider_code="HOSP-001",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_identity_provider()

    body = parse_qs(seen["req"].content.decode("ascii"))
    assert body["provider_code"] == ["HOSP-001"]


@pytest.mark.asyncio
async def test_token_request_omits_provider_code_when_not_set():
    seen: dict[str, httpx.Request] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            seen["req"] = req
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        return httpx.Response(200, json={"ok": True})

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_identity_provider()

    body = parse_qs(seen["req"].content.decode("ascii"))
    assert "provider_code" not in body


@pytest.mark.asyncio
async def test_token_request_omits_scope_when_not_provided():
    seen_request: dict[str, httpx.Request] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            seen_request["req"] = req
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        return httpx.Response(200, json={"ok": True})

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),  # scope, audience 기본값
    ) as c:
        await c.get_identity_provider()

    body = parse_qs(seen_request["req"].content.decode("ascii"))
    assert body["audience"] == ["saylog"]  # 기본값
    assert "scope" not in body  # 미지정 시 본문에서 생략


@pytest.mark.asyncio
async def test_token_response_scope_is_parsed():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok",
                "token_type": "Bearer",
                "expires_in": 900,
                "scope": "patients:read",
            })
        return httpx.Response(200, json={"ok": True})

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        scope="patients:read",
        transport=_mock_transport(handler),
    ) as c:
        result = await c.issue_token()
        assert result.scope == "patients:read"


@pytest.mark.asyncio
async def test_register_webhook_sends_single_event_field():
    """ConnectWebhookCreateRequest는 단일 event 문자열만 받음 (배열 X)."""
    seen: dict[str, dict] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        seen["body"] = json.loads(req.content)
        return httpx.Response(201, json={
            "webhookId": "wh_1",
            "url": "https://partner.example.com/webhook/saylog",
            "event": "records.summarized",
            "createdAt": "2026-05-15T00:00:00Z",
            "updatedAt": "2026-05-15T00:00:00Z",
            "secret": "S" * 64,
        })

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        result = await c.register_webhook(
            url="https://partner.example.com/webhook/saylog",
        )

    assert seen["body"] == {
        "url": "https://partner.example.com/webhook/saylog",
        "event": "records.summarized",
    }
    assert result.webhook_id == "wh_1"
    assert result.event == "records.summarized"


@pytest.mark.asyncio
async def test_list_webhooks_unwraps_webhooks_key():
    """ConnectWebhookListResponse는 {"webhooks": [...]} 래퍼."""
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        return httpx.Response(200, json={"webhooks": [
            {
                "webhookId": "wh_1",
                "url": "https://a.example.com/hook",
                "event": "records.summarized",
                "createdAt": "2026-05-15T00:00:00Z",
                "updatedAt": "2026-05-15T00:00:00Z",
            },
        ]})

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        result = await c.list_webhooks()

    assert len(result) == 1
    assert result[0].webhook_id == "wh_1"


@pytest.mark.asyncio
async def test_gateway_calls_use_api_prefix_while_token_does_not():
    """dou-connect routing: token은 /v1/oauth/token (web.php, 루트), gateway는
    /api/{service}/{path} (api.php). 단일 base_url로 합쳐 쓸 수 없으므로
    ConnectClient가 내부 분기 조립한다는 사실에 대한 회귀 방지.
    """
    paths: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        paths.append(req.url.path)
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        if req.url.path == "/api/saylog/v1/identity-provider":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_identity_provider()

    assert "/v1/oauth/token" in paths
    assert "/api/saylog/v1/identity-provider" in paths
    assert "/saylog/v1/identity-provider" not in paths
    assert "/api/v1/oauth/token" not in paths


@pytest.mark.asyncio
async def test_list_records_unwraps_records_and_passes_camel_params():
    """ConnectRecordListResponse는 {"records": [...]} 래퍼. 쿼리는 camelCase."""
    seen: dict[str, httpx.URL] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        seen["url"] = req.url
        return httpx.Response(200, json={"records": [
            {
                "recordId": "rec_1",
                "patientName": "홍길동",
                "recorderName": "김의사",
                "createdAt": "2026-05-15T00:00:00Z",
            },
        ]})

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        result = await c.list_records(
            since="2026-05-01T00:00:00Z",
            employee_id="12345",
            patient_uid="P-001",
            limit=10,
        )

    qs = seen["url"].params
    assert qs.get("since") == "2026-05-01T00:00:00Z"
    assert qs.get("employeeId") == "12345"
    assert qs.get("patientUid") == "P-001"
    assert qs.get("limit") == "10"
    assert len(result) == 1
    assert result[0].record_id == "rec_1"
    assert result[0].patient_name == "홍길동"


@pytest.mark.asyncio
async def test_start_partner_oauth_posts_with_empty_body():
    """saylog/v1/partner-oauth/start는 본문 없이 POST. 응답은
    authorizationUrl/nonce 그대로 dict로 노출.
    """
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        if req.url.path == "/api/saylog/v1/partner-oauth/start":
            seen["method"] = req.method
            seen["body"] = req.content
            seen["auth"] = req.headers.get("authorization")
            return httpx.Response(200, json={
                "authorizationUrl": "https://partner.example.com/authorize?state=xxx",
                "nonce": "n1",
            })
        return httpx.Response(404)

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        result = await c.start_partner_oauth()

    assert seen["method"] == "POST"
    assert seen["body"] == b""
    assert seen["auth"] == "Bearer tok"
    assert result == {
        "authorizationUrl": "https://partner.example.com/authorize?state=xxx",
        "nonce": "n1",
    }
