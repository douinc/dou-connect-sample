import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.connect.client import ConnectClient


def _mock_transport(handler):
    return httpx.MockTransport(handler)


# GET/PUT /v1/partner-api 의 최소 유효 응답 (ConnectPartnerApiResponse)
_PARTNER_API_BODY = {
    "partnerId": "partner-1",
    "endpoints": {},
    "isActive": True,
    "createdAt": "2026-08-19T00:00:00Z",
    "updatedAt": "2026-08-19T00:00:00Z",
}


@pytest.mark.asyncio
async def test_issue_token_called_lazily():
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok1", "token_type": "Bearer", "expires_in": 900,
            })
        if req.url.path == "/api/saylog/v1/partner-api":
            assert req.headers["authorization"] == "Bearer tok1"
            return httpx.Response(200, json=_PARTNER_API_BODY)
        return httpx.Response(404)

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_partner_api()
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
        return httpx.Response(200, json=_PARTNER_API_BODY)

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_partner_api()
        await c.get_partner_api()
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
        return httpx.Response(200, json=_PARTNER_API_BODY)

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_partner_api()
    assert state["issued"] == 2
    assert state["calls"] == 2


@pytest.mark.asyncio
async def test_register_partner_api_puts_camel_body_and_parses_response():
    """PUT /api/saylog/v1/partner-api — 본문은 service/oauth/endpoints 객체(camelCase),
    응답은 endpoints.*.auth 파생값을 포함한 PartnerApiResponse로 파싱."""
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        seen["method"] = req.method
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={
            **_PARTNER_API_BODY,
            "oauth": {
                "authorizationUrl": "https://p.example/authorize",
                "tokenUrl": "https://p.example/token",
                "userInfoUrl": "https://p.example/api/userinfo",
                "clientId": "c",
                "scopes": ["openid", "profile"],
                "redirectUri": "https://connect.dou.so/api/saylog/v1/oauth/callback",
            },
            "endpoints": {
                "patients": {"url": "https://p.example/api/patients", "auth": "user"},
            },
        })

    from app.connect.schemas import (
        PartnerApiEndpoint,
        PartnerApiEndpoints,
        PartnerApiOAuth,
        PartnerApiRequest,
    )
    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        result = await c.register_partner_api(PartnerApiRequest(
            oauth=PartnerApiOAuth(
                authorization_url="https://p.example/authorize",
                token_url="https://p.example/token",
                user_info_url="https://p.example/api/userinfo",
                client_id="c", client_secret="s",
                scopes=["openid", "profile"],
            ),
            endpoints=PartnerApiEndpoints(
                patients=PartnerApiEndpoint(url="https://p.example/api/patients"),
            ),
        ))

    assert seen["method"] == "PUT"
    assert seen["path"] == "/api/saylog/v1/partner-api"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["oauth"]["authorizationUrl"] == "https://p.example/authorize"
    assert body["oauth"]["clientSecret"] == "s"
    assert body["endpoints"] == {"patients": {"url": "https://p.example/api/patients"}}
    assert "service" not in body  # 사용자 토큰 모드만이면 service 불필요
    assert "userPatientsUrl" not in json.dumps(body)
    assert result.endpoints.patients is not None
    assert result.endpoints.patients.auth == "user"
    assert result.oauth is not None and result.oauth.redirect_uri.endswith("/oauth/callback")


@pytest.mark.asyncio
async def test_register_partner_api_service_mode_body():
    """서비스 토큰 모드 — oauth 없이 service.audience + endpoints.employee/patients."""
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={
            **_PARTNER_API_BODY,
            "service": {"audience": "partner-emr"},
            "endpoints": {
                "employee": {"url": "https://p.example/api/employee", "auth": "service"},
                "patients": {"url": "https://p.example/api/patients", "auth": "service"},
            },
        })

    from app.connect.schemas import (
        PartnerApiEndpoint,
        PartnerApiEndpoints,
        PartnerApiRequest,
        PartnerApiService,
    )
    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        result = await c.register_partner_api(PartnerApiRequest(
            service=PartnerApiService(audience="partner-emr"),
            endpoints=PartnerApiEndpoints(
                employee=PartnerApiEndpoint(url="https://p.example/api/employee"),
                patients=PartnerApiEndpoint(url="https://p.example/api/patients"),
            ),
        ))

    assert seen["body"] == {
        "service": {"audience": "partner-emr"},
        "endpoints": {
            "employee": {"url": "https://p.example/api/employee"},
            "patients": {"url": "https://p.example/api/patients"},
        },
    }
    assert result.endpoints.employee is not None
    assert result.endpoints.employee.auth == "service"
    assert result.endpoints.patients is not None
    assert result.endpoints.patients.auth == "service"


@pytest.mark.asyncio
async def test_validate_partner_api_user_mode_sends_header_only():
    """사용자 토큰 모드 검증 — Partner-Access-Token 헤더, 본문 없음."""
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        seen["path"] = req.url.path
        seen["header"] = req.headers.get("partner-access-token")
        seen["content"] = req.content
        return httpx.Response(200, json={"userInfo": {}, "patients": {}})

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.validate_partner_api("user-token")

    assert seen["path"] == "/api/saylog/v1/validate-partner-api"
    assert seen["header"] == "user-token"
    assert seen["content"] == b""


@pytest.mark.asyncio
async def test_validate_partner_api_service_mode_sends_sample_body():
    """서비스 토큰 모드 검증 — 헤더 없이 본문 sample.employeeId/name."""
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        seen["header"] = req.headers.get("partner-access-token")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"employee": {}, "patients": {}})

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.validate_partner_api(sample_employee_id="12345", sample_name="이의사")

    assert seen["header"] is None
    assert seen["body"] == {"sample": {"employeeId": "12345", "name": "이의사"}}


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
        return httpx.Response(200, json=_PARTNER_API_BODY)

    async with ConnectClient(
        base_url="http://test",
        client_id="my-id", client_secret="my-secret",
        audience="saylog",
        scope="patients:read records:read",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_partner_api()

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
        return httpx.Response(200, json=_PARTNER_API_BODY)

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        provider_code="HOSP-001",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_partner_api()

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
        return httpx.Response(200, json=_PARTNER_API_BODY)

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_partner_api()

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
        return httpx.Response(200, json=_PARTNER_API_BODY)

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),  # scope, audience 기본값
    ) as c:
        await c.get_partner_api()

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
        return httpx.Response(200, json=_PARTNER_API_BODY)

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        scope="patients:read",
        transport=_mock_transport(handler),
    ) as c:
        result = await c.issue_token()
        assert result.scope == "patients:read"


@pytest.mark.asyncio
async def test_register_webhook_sends_event_string():
    """ConnectWebhookCreateRequest.event는 4값 enum의 단일 문자열 (배열 X)."""
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
async def test_register_webhook_accepts_event_parameter():
    """이벤트 단위 등록 — event 인자가 요청 본문에 그대로 실린다."""
    seen: dict[str, dict] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={
                "access_token": "tok", "token_type": "Bearer", "expires_in": 900,
            })
        seen["body"] = json.loads(req.content)
        return httpx.Response(201, json={
            "webhookId": "wh_2",
            "url": "https://partner.example.com/webhook/saylog",
            "event": "records.updated",
            "createdAt": "2026-05-15T00:00:00Z",
            "updatedAt": "2026-05-15T00:00:00Z",
            "secret": "T" * 64,
        })

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        result = await c.register_webhook(
            url="https://partner.example.com/webhook/saylog",
            event="records.updated",
        )

    assert seen["body"]["event"] == "records.updated"
    assert result.event == "records.updated"


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
        if req.url.path == "/api/saylog/v1/partner-api":
            return httpx.Response(200, json=_PARTNER_API_BODY)
        return httpx.Response(404)

    async with ConnectClient(
        base_url="http://test",
        client_id="cid", client_secret="csecret",
        transport=_mock_transport(handler),
    ) as c:
        await c.get_partner_api()

    assert "/v1/oauth/token" in paths
    assert "/api/saylog/v1/partner-api" in paths
    assert "/saylog/v1/partner-api" not in paths
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
