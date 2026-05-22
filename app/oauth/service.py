import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.auth import AuthCode, RefreshToken
from app.domain.user import User
from app.oauth.errors import OAuthError
from app.oauth.jwt_signer import JwtSigner
from app.storage.memory import InMemoryStore


@dataclass(frozen=True)
class TokenIssueResult:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"
    scope: str = ""


class OAuthService:
    def __init__(
        self,
        *,
        store: InMemoryStore,
        signer: JwtSigner,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        audience: str,
        access_ttl: int,
        refresh_ttl: int,
        auth_code_ttl: int = 600,
    ) -> None:
        self._store = store
        self._signer = signer
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._audience = audience
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl
        self._auth_code_ttl = auth_code_ttl

    def authenticate(self, username: str, password: str) -> User | None:
        user = self._store.users.get_by_username(username)
        if user is None:
            return None
        if not hmac.compare_digest(user.password, password):
            return None
        return user

    def authorize(
        self, *, user_id: str, client_id: str, redirect_uri: str, scope: str,
    ) -> str:
        if not hmac.compare_digest(client_id, self._client_id):
            raise OAuthError("invalid_client", "Unknown client_id", status=401)
        if redirect_uri != self._redirect_uri:
            raise OAuthError("invalid_request", "redirect_uri mismatch")
        if self._store.users.get(user_id) is None:
            raise OAuthError("invalid_request", "Unknown user")

        code = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        self._store.auth_codes.save(
            AuthCode(
                code=code,
                user_id=user_id,
                client_id=client_id,
                redirect_uri=redirect_uri,
                scope=scope,
                expires_at=now + timedelta(seconds=self._auth_code_ttl),
            )
        )
        return code

    def exchange_code(
        self, *, code: str, client_id: str, client_secret: str, redirect_uri: str,
    ) -> TokenIssueResult:
        self._verify_client(client_id, client_secret)
        consumed = self._store.auth_codes.consume(code)
        if consumed is None:
            raise OAuthError("invalid_grant", "Authorization code invalid or used")
        now = datetime.now(UTC)
        if consumed.is_expired(now):
            raise OAuthError("invalid_grant", "Authorization code expired")
        if consumed.redirect_uri != redirect_uri:
            raise OAuthError("invalid_grant", "redirect_uri mismatch")
        return self._issue_tokens(
            user_id=consumed.user_id, scope=consumed.scope, now=now,
        )

    def refresh(
        self, *, refresh_token: str, client_id: str, client_secret: str,
    ) -> TokenIssueResult:
        self._verify_client(client_id, client_secret)
        rt = self._store.refresh_tokens.get(refresh_token)
        now = datetime.now(UTC)
        if rt is None or not rt.is_active(now):
            raise OAuthError("invalid_grant", "Refresh token invalid or revoked")
        self._store.refresh_tokens.revoke(refresh_token)
        return self._issue_tokens(user_id=rt.user_id, scope=rt.scope, now=now)

    def _verify_client(self, client_id: str, client_secret: str) -> None:
        if not hmac.compare_digest(client_id, self._client_id):
            raise OAuthError("invalid_client", "Unknown client_id", status=401)
        if not hmac.compare_digest(client_secret, self._client_secret):
            raise OAuthError("invalid_client", "Bad client_secret", status=401)

    def _issue_tokens(
        self, *, user_id: str, scope: str, now: datetime,
    ) -> TokenIssueResult:
        access = self._signer.sign_access_token(
            subject=user_id,
            audience=self._audience,
            scope=scope,
            client_id=self._client_id,
            issued_at=now,
            ttl_seconds=self._access_ttl,
        )
        refresh = secrets.token_urlsafe(48)
        self._store.refresh_tokens.save(
            RefreshToken(
                token=refresh,
                user_id=user_id,
                client_id=self._client_id,
                scope=scope,
                expires_at=now + timedelta(seconds=self._refresh_ttl),
            )
        )
        return TokenIssueResult(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._access_ttl,
            scope=scope,
        )
