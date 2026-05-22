import pytest

from app.domain.user import User
from app.oauth.errors import OAuthError
from app.oauth.jwt_signer import JwtSigner
from app.oauth.service import OAuthService
from app.storage.memory import InMemoryStore


@pytest.fixture
def store() -> InMemoryStore:
    s = InMemoryStore()
    s.users.save(User(
        id="user-001", username="lee@h", password="pw", name="이",
        employee_id="12345", department="내과",
        email="lee@h", email_verified=True,
    ))
    return s


@pytest.fixture
def signer() -> JwtSigner:
    return JwtSigner(issuer="http://test/oauth")


@pytest.fixture
def service(store: InMemoryStore, signer: JwtSigner) -> OAuthService:
    return OAuthService(
        store=store, signer=signer,
        client_id="saylog-client", client_secret="s3cret",
        redirect_uri="http://cb",
        audience="saylog",
        access_ttl=3600, refresh_ttl=86400,
        auth_code_ttl=600,
    )


def test_authorize_creates_code(service: OAuthService, store: InMemoryStore):
    code = service.authorize(
        user_id="user-001", client_id="saylog-client",
        redirect_uri="http://cb", scope="openid",
    )
    assert code != ""
    consumed = store.auth_codes.consume(code)
    assert consumed is not None and consumed.user_id == "user-001"


def test_authorize_rejects_unknown_client(service: OAuthService):
    with pytest.raises(OAuthError) as exc:
        service.authorize(
            user_id="user-001", client_id="other",
            redirect_uri="http://cb", scope="openid",
        )
    assert exc.value.code == "invalid_client"


def test_authorize_rejects_redirect_mismatch(service: OAuthService):
    with pytest.raises(OAuthError) as exc:
        service.authorize(
            user_id="user-001", client_id="saylog-client",
            redirect_uri="http://wrong", scope="openid",
        )
    assert exc.value.code == "invalid_request"


def test_token_exchange_returns_access_and_refresh(service: OAuthService):
    code = service.authorize(
        user_id="user-001", client_id="saylog-client",
        redirect_uri="http://cb", scope="openid",
    )
    result = service.exchange_code(
        code=code, client_id="saylog-client",
        client_secret="s3cret", redirect_uri="http://cb",
    )
    assert result.access_token != ""
    assert result.refresh_token != ""
    assert result.token_type == "Bearer"
    assert result.expires_in == 3600


def test_auth_code_is_single_use(service: OAuthService):
    code = service.authorize(
        user_id="user-001", client_id="saylog-client",
        redirect_uri="http://cb", scope="openid",
    )
    service.exchange_code(
        code=code, client_id="saylog-client",
        client_secret="s3cret", redirect_uri="http://cb",
    )
    with pytest.raises(OAuthError) as exc:
        service.exchange_code(
            code=code, client_id="saylog-client",
            client_secret="s3cret", redirect_uri="http://cb",
        )
    assert exc.value.code == "invalid_grant"


def test_token_exchange_rejects_bad_secret(service: OAuthService):
    code = service.authorize(
        user_id="user-001", client_id="saylog-client",
        redirect_uri="http://cb", scope="openid",
    )
    with pytest.raises(OAuthError) as exc:
        service.exchange_code(
            code=code, client_id="saylog-client",
            client_secret="wrong", redirect_uri="http://cb",
        )
    assert exc.value.code == "invalid_client"


def test_refresh_token_rotation(service: OAuthService, store: InMemoryStore):
    code = service.authorize(
        user_id="user-001", client_id="saylog-client",
        redirect_uri="http://cb", scope="openid",
    )
    first = service.exchange_code(
        code=code, client_id="saylog-client",
        client_secret="s3cret", redirect_uri="http://cb",
    )
    second = service.refresh(
        refresh_token=first.refresh_token,
        client_id="saylog-client", client_secret="s3cret",
    )
    assert second.refresh_token != first.refresh_token
    old = store.refresh_tokens.get(first.refresh_token)
    assert old is not None and old.revoked is True


def test_refresh_with_revoked_token_fails(service: OAuthService):
    code = service.authorize(
        user_id="user-001", client_id="saylog-client",
        redirect_uri="http://cb", scope="openid",
    )
    first = service.exchange_code(
        code=code, client_id="saylog-client",
        client_secret="s3cret", redirect_uri="http://cb",
    )
    service.refresh(refresh_token=first.refresh_token,
                    client_id="saylog-client", client_secret="s3cret")
    with pytest.raises(OAuthError) as exc:
        service.refresh(refresh_token=first.refresh_token,
                        client_id="saylog-client", client_secret="s3cret")
    assert exc.value.code == "invalid_grant"


def test_authenticate_user(service: OAuthService):
    user = service.authenticate("lee@h", "pw")
    assert user is not None and user.id == "user-001"
    assert service.authenticate("lee@h", "wrong") is None
    assert service.authenticate("nope", "pw") is None
