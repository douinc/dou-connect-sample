import base64
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_authorize_get_renders_login_form(client: AsyncClient):
    r = await client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "saylog-client",
            "redirect_uri": "http://cb.test/callback",
            "state": "xyz",
            "scope": "openid",
        },
    )
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "name=\"username\"" in r.text


@pytest.mark.asyncio
async def test_authorize_post_redirects_with_code(client: AsyncClient):
    r = await client.post(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "saylog-client",
            "redirect_uri": "http://cb.test/callback",
            "state": "xyz",
            "scope": "openid",
        },
        data={"username": "lee@hospital.com", "password": "password"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    parsed = urlparse(r.headers["location"])
    assert parsed.scheme == "http" and parsed.netloc == "cb.test"
    qs = parse_qs(parsed.query)
    assert "code" in qs
    assert qs["state"] == ["xyz"]


@pytest.mark.asyncio
async def test_authorize_post_wrong_password_shows_form(client: AsyncClient):
    r = await client.post(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "saylog-client",
            "redirect_uri": "http://cb.test/callback",
            "state": "xyz",
            "scope": "openid",
        },
        data={"username": "lee@hospital.com", "password": "wrong"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "잘못된" in r.text or "invalid" in r.text.lower()


@pytest.mark.asyncio
async def test_token_endpoint_full_flow(client: AsyncClient):
    auth = await client.post(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "saylog-client",
            "redirect_uri": "http://cb.test/callback",
            "state": "xyz",
            "scope": "openid",
        },
        data={"username": "lee@hospital.com", "password": "password"},
        follow_redirects=False,
    )
    code = parse_qs(urlparse(auth.headers["location"]).query)["code"][0]

    r = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://cb.test/callback",
            "client_id": "saylog-client",
            "client_secret": "s3cret",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600
    assert body["access_token"]
    assert body["refresh_token"]


@pytest.mark.asyncio
async def test_token_endpoint_returns_oauth_error_shape(client: AsyncClient):
    r = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": "nope",
            "redirect_uri": "http://cb.test/callback",
            "client_id": "saylog-client",
            "client_secret": "s3cret",
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "invalid_grant"
    assert "error_description" in body


async def _get_auth_code(client: AsyncClient) -> str:
    r = await client.post(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "saylog-client",
            "redirect_uri": "http://cb.test/callback",
            "state": "xyz",
            "scope": "openid",
        },
        data={"username": "lee@hospital.com", "password": "password"},
        follow_redirects=False,
    )
    return parse_qs(urlparse(r.headers["location"]).query)["code"][0]


@pytest.mark.asyncio
async def test_token_accepts_basic_auth_header(client: AsyncClient):
    """RFC 6749 §2.3.1: client_id/secret을 Basic 헤더로 전달 가능해야 함."""
    code = await _get_auth_code(client)
    basic = base64.b64encode(b"saylog-client:s3cret").decode("ascii")

    r = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://cb.test/callback",
        },
        headers={"Authorization": f"Basic {basic}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["scope"] == "openid"


@pytest.mark.asyncio
async def test_token_response_includes_scope(client: AsyncClient):
    """RFC 6749 §5.1: 부여된 scope를 응답에 포함."""
    code = await _get_auth_code(client)
    r = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://cb.test/callback",
            "client_id": "saylog-client",
            "client_secret": "s3cret",
        },
    )
    assert r.status_code == 200
    assert r.json()["scope"] == "openid"


@pytest.mark.asyncio
async def test_token_rejects_basic_and_body_creds_together(client: AsyncClient):
    """RFC 6749 §2.3.1: 두 인증 방식 동시 사용은 invalid_request로 거부."""
    code = await _get_auth_code(client)
    basic = base64.b64encode(b"saylog-client:s3cret").decode("ascii")

    r = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://cb.test/callback",
            "client_id": "saylog-client",
            "client_secret": "s3cret",
        },
        headers={"Authorization": f"Basic {basic}"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_request"


@pytest.mark.asyncio
async def test_token_rejects_missing_credentials(client: AsyncClient):
    code = await _get_auth_code(client)
    r = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://cb.test/callback",
        },
    )
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_client"


@pytest.mark.asyncio
async def test_jwks_endpoint(client: AsyncClient):
    r = await client.get("/.well-known/jwks.json")
    assert r.status_code == 200
    body = r.json()
    assert "keys" in body and body["keys"][0]["alg"] == "RS256"
