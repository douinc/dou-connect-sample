from typing import Literal

OAuthErrorCode = Literal[
    "invalid_request",
    "invalid_grant",
    "invalid_client",
    "unsupported_grant_type",
]


class OAuthError(Exception):
    def __init__(self, code: OAuthErrorCode, description: str, status: int = 400):
        super().__init__(description)
        self.code: OAuthErrorCode = code
        self.description = description
        self.status = status
