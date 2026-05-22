from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AuthCode:
    code: str
    user_id: str
    client_id: str
    redirect_uri: str
    scope: str
    expires_at: datetime

    def is_expired(self, at: datetime) -> bool:
        return at >= self.expires_at


@dataclass
class RefreshToken:
    token: str
    user_id: str
    client_id: str
    scope: str
    expires_at: datetime
    revoked: bool = False

    def is_active(self, at: datetime) -> bool:
        return not self.revoked and at < self.expires_at
