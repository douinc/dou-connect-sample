"""파트너 구현 의무 엔드포인트 — GET /api/userinfo, POST /api/patients(두 모드), POST /api/employee."""

import math
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.user import User
from app.main import create_app
from tests._service_tokens import ServiceTokenIssuer
from tests.conftest import make_settings, make_state

NO_STORE = {"cache-control": "no-store", "pragma": "no-cache"}


async def _get_access_token(client: AsyncClient, username: str = "lee@hospital.com") -> str:
    auth = await client.post(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "saylog-client",
            "redirect_uri": "http://cb.test/callback",
            "state": "x",
            "scope": "openid",
        },
        data={"username": username, "password": "password"},
        follow_redirects=False,
    )
    code = parse_qs(urlparse(auth.headers["location"]).query)["code"][0]
    tok = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://cb.test/callback",
            "client_id": "saylog-client",
            "client_secret": "s3cret",
        },
    )
    return tok.json()["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_no_store(headers) -> None:
    for k, v in NO_STORE.items():
        assert headers.get(k) == v


# ---------------------------------------------------------------------------
# userinfo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_userinfo_requires_bearer(client: AsyncClient):
    r = await client.get("/api/userinfo")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_userinfo_returns_required_fields_and_no_store(client: AsyncClient):
    token = await _get_access_token(client)
    r = await client.get("/api/userinfo", headers=_bearer(token))
    assert r.status_code == 200
    body = r.json()
    for f in ("sub", "preferred_username", "name", "employeeId", "department"):
        assert f in body
    assert body["sub"] == "user-001"
    assert body["employeeId"] == "12345"
    _assert_no_store(r.headers)


# ---------------------------------------------------------------------------
# patients — 사용자 토큰 모드 (기본: PATIENTS_AUTH_MODE=user)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patients_is_post_only(client: AsyncClient):
    token = await _get_access_token(client)
    r = await client.get("/api/patients", headers=_bearer(token))
    assert r.status_code == 405


@pytest.mark.asyncio
async def test_patients_requires_bearer(client: AsyncClient):
    r = await client.post("/api/patients", json={})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_patients_empty_body_returns_all_with_null_next(client: AsyncClient):
    token = await _get_access_token(client)
    r = await client.post("/api/patients", json={}, headers=_bearer(token))
    assert r.status_code == 200
    body = r.json()
    assert len(body["patients"]) > 0
    assert "page" not in body
    assert "next" in body and body["next"] is None
    for p in body["patients"]:
        assert p["attendingEmployeeId"] == "12345"
    _assert_no_store(r.headers)


@pytest.mark.asyncio
async def test_patients_pagination_consistency(client: AsyncClient):
    token = await _get_access_token(client)
    r = await client.post("/api/patients", json={"page": 1, "pageSize": 10}, headers=_bearer(token))
    body = r.json()
    assert body["page"] == 1
    assert body["pageSize"] == 10
    assert body["totalPages"] == math.ceil(body["totalCount"] / body["pageSize"])
    assert len(body["patients"]) <= 10
    assert isinstance(body["next"], str)


@pytest.mark.asyncio
async def test_patients_pagination_total_matches_full(client: AsyncClient):
    token = await _get_access_token(client)
    full = await client.post("/api/patients", json={}, headers=_bearer(token))
    paginated = await client.post(
        "/api/patients",
        json={"page": 1, "pageSize": 20},
        headers=_bearer(token),
    )
    assert len(full.json()["patients"]) == paginated.json()["totalCount"]


@pytest.mark.asyncio
async def test_patients_cursor_walk_covers_all_without_duplicates(client: AsyncClient):
    """다음 페이지는 {cursor}만 보낸다 — 전 페이지를 돌면 전체 목록과 같고 중복이 없다."""
    token = await _get_access_token(client)
    full = await client.post("/api/patients", json={}, headers=_bearer(token))
    expected = [p["patientUid"] for p in full.json()["patients"]]

    r = await client.post("/api/patients", json={"page": 1, "pageSize": 7}, headers=_bearer(token))
    seen: list[str] = [p["patientUid"] for p in r.json()["patients"]]
    pages = 1
    while r.json()["next"] is not None:
        r = await client.post(
            "/api/patients",
            json={"cursor": r.json()["next"]},
            headers=_bearer(token),
        )
        assert r.status_code == 200
        seen.extend(p["patientUid"] for p in r.json()["patients"])
        pages += 1
    assert pages == math.ceil(len(expected) / 7)
    assert seen == expected
    assert r.json()["page"] == pages
    assert r.json()["next"] is None


@pytest.mark.asyncio
async def test_patients_last_page_has_null_next_and_beyond_is_empty(client: AsyncClient):
    token = await _get_access_token(client)
    first = await client.post(
        "/api/patients",
        json={"page": 1, "pageSize": 50},
        headers=_bearer(token),
    )
    last_page = first.json()["totalPages"]
    r = await client.post(
        "/api/patients",
        json={"page": last_page, "pageSize": 50},
        headers=_bearer(token),
    )
    assert r.json()["next"] is None
    r = await client.post(
        "/api/patients",
        json={"page": last_page + 1, "pageSize": 50},
        headers=_bearer(token),
    )
    assert r.status_code == 200
    assert r.json()["patients"] == []
    assert r.json()["next"] is None


@pytest.mark.asyncio
async def test_patients_page_size_is_clamped_to_100(client: AsyncClient):
    token = await _get_access_token(client)
    r = await client.post(
        "/api/patients",
        json={"page": 1, "pageSize": 500},
        headers=_bearer(token),
    )
    assert r.status_code == 200
    assert r.json()["pageSize"] == 100


@pytest.mark.asyncio
async def test_patients_single_param_uses_defaults(client: AsyncClient):
    """page/pageSize 한쪽만 와도 거부하지 않고 기본값(page=1, pageSize=50)을 채운다."""
    token = await _get_access_token(client)
    r = await client.post("/api/patients", json={"pageSize": 5}, headers=_bearer(token))
    assert r.status_code == 200
    assert r.json()["page"] == 1 and r.json()["pageSize"] == 5
    r = await client.post("/api/patients", json={"page": 2}, headers=_bearer(token))
    assert r.status_code == 200
    assert r.json()["page"] == 2 and r.json()["pageSize"] == 50


@pytest.mark.asyncio
async def test_patients_malformed_cursor_422_without_echo(client: AsyncClient):
    token = await _get_access_token(client)
    r = await client.post(
        "/api/patients",
        json={"cursor": "not-a-cursor-xyz"},
        headers=_bearer(token),
    )
    assert r.status_code == 422
    assert "not-a-cursor-xyz" not in r.text
    _assert_no_store(r.headers)


@pytest.mark.asyncio
async def test_patients_invalid_body_422_without_echo(client: AsyncClient):
    token = await _get_access_token(client)
    r = await client.post(
        "/api/patients",
        json={"page": "zero-ish", "pageSize": -1},
        headers=_bearer(token),
    )
    assert r.status_code == 422
    assert "zero-ish" not in r.text


@pytest.mark.asyncio
async def test_patients_cursor_is_bound_to_token_user(client: AsyncClient):
    """사용자 토큰 모드: 다른 사용자가 받은 커서를 재사용하면 422 — 사번은 토큰이 정한다."""
    lee = await _get_access_token(client, "lee@hospital.com")
    kim = await _get_access_token(client, "kim@hospital.com")
    r = await client.post("/api/patients", json={"page": 1, "pageSize": 5}, headers=_bearer(lee))
    cursor = r.json()["next"]
    r = await client.post("/api/patients", json={"cursor": cursor}, headers=_bearer(kim))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patients_user_mode_rejects_employee_id_in_body(client: AsyncClient):
    token = await _get_access_token(client)
    r = await client.post("/api/patients", json={"employeeId": "12346"}, headers=_bearer(token))
    assert r.status_code == 422
    assert "12346" not in r.text


@pytest.mark.asyncio
async def test_patients_user_mode_rejects_service_token(
    client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    r = await client.post(
        "/api/patients",
        json={"employeeId": "12345"},
        headers=_bearer(service_issuer.mint()),
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# patients — 서비스 토큰 모드 (PATIENTS_AUTH_MODE=service)
# ---------------------------------------------------------------------------


@pytest.fixture
async def service_client(service_issuer: ServiceTokenIssuer) -> AsyncIterator[AsyncClient]:
    state = make_state(make_settings(patients_auth_mode="service"), service_issuer)
    # 퇴직 의사 — 직원 조회 404·환자 목록 빈 목록 케이스용
    state.store.users.save(
        User(
            id="user-099",
            username="park@hospital.com",
            password="password",
            name="박의사",
            employee_id="99999",
            department="내과",
            email="park@hospital.com",
            email_verified=True,
            active=False,
        )
    )
    app = create_app(state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_service_patients_by_employee_id(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    r = await service_client.post(
        "/api/patients",
        json={"employeeId": "12346", "page": 1, "pageSize": 10},
        headers=_bearer(service_issuer.mint()),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["totalCount"] > 0
    assert all(p["attendingEmployeeId"] == "12346" for p in body["patients"])
    assert isinstance(body["next"], str)
    _assert_no_store(r.headers)


@pytest.mark.asyncio
async def test_service_patients_cursor_carries_employee_id(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    headers = _bearer(service_issuer.mint())
    r = await service_client.post(
        "/api/patients",
        json={"employeeId": "12346", "page": 1, "pageSize": 10},
        headers=headers,
    )
    first_uids = [p["patientUid"] for p in r.json()["patients"]]
    r2 = await service_client.post(
        "/api/patients",
        json={"cursor": r.json()["next"]},
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["page"] == 2
    assert all(p["attendingEmployeeId"] == "12346" for p in r2.json()["patients"])
    assert not set(first_uids) & {p["patientUid"] for p in r2.json()["patients"]}


@pytest.mark.asyncio
async def test_service_patients_requires_employee_id_or_cursor(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    r = await service_client.post(
        "/api/patients",
        json={"page": 1, "pageSize": 10},
        headers=_bearer(service_issuer.mint()),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("employee_id", ["00000", "99999"])  # 미존재 / 퇴직
async def test_service_patients_unknown_or_inactive_is_empty_200(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
    employee_id: str,
):
    """담당 환자 0명인 재직 직원과 같은 모양 — 이 엔드포인트로 직원 존재를 알 수 없어야 한다."""
    r = await service_client.post(
        "/api/patients",
        json={"employeeId": employee_id, "page": 1, "pageSize": 10},
        headers=_bearer(service_issuer.mint()),
    )
    assert r.status_code == 200
    assert r.json() == {
        "patients": [],
        "page": 1,
        "pageSize": 10,
        "totalCount": 0,
        "totalPages": 0,
        "next": None,
    }


@pytest.mark.asyncio
async def test_service_patients_requires_patients_read_scope(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    r = await service_client.post(
        "/api/patients",
        json={"employeeId": "12346"},
        headers=_bearer(service_issuer.mint(scopes=["staff:read"])),
    )
    assert r.status_code == 403
    assert 'scope="patients:read"' in r.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_service_patients_rejects_user_token(service_client: AsyncClient):
    token = await _get_access_token(service_client)
    r = await service_client.post("/api/patients", json={}, headers=_bearer(token))
    assert r.status_code == 401
    assert 'error="invalid_token"' in r.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_service_patients_other_hospital_is_404(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    r = await service_client.post(
        "/api/patients",
        json={"employeeId": "12346"},
        headers=_bearer(service_issuer.mint(provider_code="OTHER-HOSP")),
    )
    assert r.status_code == 404
    assert r.content == b""


# ---------------------------------------------------------------------------
# employee — 항상 서비스 토큰
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_employee_exact_match_returns_200(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    r = await service_client.post(
        "/api/employee",
        json={"employeeId": "12345", "name": "이의사"},
        headers=_bearer(service_issuer.mint()),
    )
    assert r.status_code == 200
    assert r.json() == {
        "employeeId": "12345",
        "name": "이의사",
        "department": "내과",
        "active": True,
    }
    _assert_no_store(r.headers)


@pytest.mark.asyncio
async def test_employee_trims_surrounding_whitespace_only(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    headers = _bearer(service_issuer.mint())
    r = await service_client.post(
        "/api/employee",
        json={"employeeId": " 12345 ", "name": "  이의사 "},
        headers=headers,
    )
    assert r.status_code == 200
    r = await service_client.post(
        "/api/employee",
        json={"employeeId": "12345", "name": "이 의사"},
        headers=headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"employeeId": "00000", "name": "이의사"},  # 미존재 사번
        {"employeeId": "12345", "name": "김의사"},  # 이름 불일치
        {"employeeId": "99999", "name": "박의사"},  # 퇴직
        {"employeeId": "__saylog_validation__", "name": "x"},  # 새록 검증기의 404 케이스
    ],
)
async def test_employee_miss_is_indistinguishable_404(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
    body: dict[str, str],
):
    r = await service_client.post(
        "/api/employee", json=body, headers=_bearer(service_issuer.mint())
    )
    assert r.status_code == 404
    assert r.content == b""
    _assert_no_store(r.headers)


@pytest.mark.asyncio
async def test_employee_validation_error_422_without_echo(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    r = await service_client.post(
        "/api/employee",
        json={"employeeId": "12345-echo-me"},
        headers=_bearer(service_issuer.mint()),
    )
    assert r.status_code == 422
    assert "12345-echo-me" not in r.text
    _assert_no_store(r.headers)


@pytest.mark.asyncio
async def test_employee_requires_service_token(service_client: AsyncClient):
    r = await service_client.post("/api/employee", json={"employeeId": "12345", "name": "이의사"})
    assert r.status_code == 401
    user_token = await _get_access_token(service_client)
    r = await service_client.post(
        "/api/employee",
        json={"employeeId": "12345", "name": "이의사"},
        headers=_bearer(user_token),
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_employee_requires_staff_read_scope(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    r = await service_client.post(
        "/api/employee",
        json={"employeeId": "12345", "name": "이의사"},
        headers=_bearer(service_issuer.mint(scopes=["patients:read"])),
    )
    assert r.status_code == 403
    assert 'scope="staff:read"' in r.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_employee_other_hospital_is_404(
    service_client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    r = await service_client.post(
        "/api/employee",
        json={"employeeId": "12345", "name": "이의사"},
        headers=_bearer(service_issuer.mint(provider_code="OTHER-HOSP")),
    )
    assert r.status_code == 404
    assert r.content == b""


@pytest.mark.asyncio
async def test_employee_works_in_user_mode_app_too(
    client: AsyncClient,
    service_issuer: ServiceTokenIssuer,
):
    """employee는 oauth 등록 여부와 무관하게 항상 서비스 토큰 — 기본(user 모드) 앱에서도 동작."""
    r = await client.post(
        "/api/employee",
        json={"employeeId": "12345", "name": "이의사"},
        headers=_bearer(service_issuer.mint()),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_service_endpoints_without_audience_config_are_500(
    service_issuer: ServiceTokenIssuer,
):
    """service.audience 미설정은 호출자 오류(401)가 아니라 서버 설정 오류."""
    state = make_state(make_settings(service_token_audience=""), service_issuer)
    app = create_app(state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/employee",
            json={"employeeId": "12345", "name": "이의사"},
            headers=_bearer(service_issuer.mint()),
        )
    assert r.status_code == 500


# ---------------------------------------------------------------------------
# 인증이 본문 검증보다 먼저 — 미인증 호출자에게 검증기를 노출하지 않는다
# ---------------------------------------------------------------------------


async def test_employee_auth_runs_before_body_validation(service_client: AsyncClient):
    # 토큰 없음 + 깨진 본문 → 422(본문 오류)가 아니라 401
    r = await service_client.post("/api/employee", json={"employeeId": 123})
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Bearer")


async def test_patients_auth_runs_before_body_validation(service_client: AsyncClient):
    r = await service_client.post("/api/patients", json={"cursor": 123})
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Bearer")
