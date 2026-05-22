import math
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient


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


@pytest.mark.asyncio
async def test_userinfo_requires_bearer(client: AsyncClient):
    r = await client.get("/api/userinfo")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_userinfo_returns_required_fields(client: AsyncClient):
    token = await _get_access_token(client)
    r = await client.get(
        "/api/userinfo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    for f in ("sub", "preferred_username", "name", "employeeId", "department"):
        assert f in body
    assert body["sub"] == "user-001"
    assert body["employeeId"] == "12345"


@pytest.mark.asyncio
async def test_patients_without_pagination_returns_all(client: AsyncClient):
    token = await _get_access_token(client)
    r = await client.get(
        "/api/patients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "patients" in body
    assert len(body["patients"]) > 0
    assert "page" not in body
    for p in body["patients"]:
        assert p["attendingEmployeeId"] == "12345"


@pytest.mark.asyncio
async def test_patients_pagination_consistency(client: AsyncClient):
    token = await _get_access_token(client)
    r = await client.get(
        "/api/patients?page=1&pageSize=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = r.json()
    assert body["page"] == 1
    assert body["pageSize"] == 10
    assert body["totalPages"] == math.ceil(body["totalCount"] / body["pageSize"])
    assert len(body["patients"]) <= 10


@pytest.mark.asyncio
async def test_patients_pagination_total_matches_full(client: AsyncClient):
    token = await _get_access_token(client)
    full = await client.get("/api/patients", headers={"Authorization": f"Bearer {token}"})
    paginated = await client.get(
        "/api/patients?page=1&pageSize=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(full.json()["patients"]) == paginated.json()["totalCount"]
