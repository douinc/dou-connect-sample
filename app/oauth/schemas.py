from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str
    scope: str = ""


class OAuthErrorResponse(BaseModel):
    error: str
    error_description: str = Field(default="")
