import base64
import binascii
from urllib.parse import unquote, urlencode

from fastapi import APIRouter, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.dependencies import AppState
from app.oauth.errors import OAuthError


def _resolve_client_credentials(
    *,
    authorization: str | None,
    form_client_id: str | None,
    form_client_secret: str | None,
) -> tuple[str, str]:
    """RFC 6749 §2.3.1: Basic 헤더 또는 본문 중 정확히 하나로 인증.

    Basic 헤더의 client_id/secret은 application/x-www-form-urlencoded 규칙으로
    퍼센트 인코딩된 값이라 unquote로 디코드한다. 양쪽 방식을 동시에 사용하면
    invalid_request로 거부.
    """
    basic_creds: tuple[str, str] | None = None
    if authorization is not None and authorization.lower().startswith("basic "):
        encoded = authorization.split(" ", 1)[1].strip()
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
            raise OAuthError(
                "invalid_client", "Malformed Basic credentials", status=401,
            ) from exc
        if ":" not in decoded:
            raise OAuthError(
                "invalid_client", "Malformed Basic credentials", status=401,
            )
        cid, csecret = decoded.split(":", 1)
        basic_creds = (unquote(cid), unquote(csecret))

    form_present = form_client_id is not None or form_client_secret is not None

    if basic_creds is not None and form_present:
        raise OAuthError(
            "invalid_request",
            "client credentials must not be sent via both Basic header and request body",
        )
    if basic_creds is not None:
        return basic_creds
    if form_client_id is not None and form_client_secret is not None:
        return form_client_id, form_client_secret
    raise OAuthError("invalid_client", "client credentials required", status=401)


def build_oauth_router(state: AppState) -> APIRouter:
    router = APIRouter()
    service = state.oauth_service
    templates = state.templates

    @router.get("/authorize", response_class=HTMLResponse)
    async def authorize_get(
        request: Request,
        response_type: str = "code",
        client_id: str = "",
        redirect_uri: str = "",
        scope: str = "",
        state: str = "",
    ) -> HTMLResponse:
        if response_type != "code":
            raise HTTPException(400, "unsupported response_type")
        action = "/authorize?" + urlencode({
            "response_type": response_type,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
        })
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"action_url": action, "error": None},
        )

    @router.post("/authorize", response_model=None)
    async def authorize_post(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        response_type: str = "code",
        client_id: str = "",
        redirect_uri: str = "",
        scope: str = "",
        state: str = "",
    ) -> HTMLResponse | RedirectResponse | JSONResponse:
        user = service.authenticate(username, password)
        if user is None:
            action = "/authorize?" + urlencode({
                "response_type": response_type,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
            })
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={"action_url": action, "error": "잘못된 사용자 이름 또는 비밀번호"},
                status_code=401,
            )

        try:
            code = service.authorize(
                user_id=user.id,
                client_id=client_id,
                redirect_uri=redirect_uri,
                scope=scope,
            )
        except OAuthError as e:
            return JSONResponse(
                {"error": e.code, "error_description": e.description},
                status_code=e.status,
            )

        target = f"{redirect_uri}?{urlencode({'code': code, 'state': state})}"
        return RedirectResponse(target, status_code=302)

    @router.post("/token")
    async def token(
        grant_type: str = Form(...),
        code: str | None = Form(None),
        redirect_uri: str | None = Form(None),
        client_id: str | None = Form(None),
        client_secret: str | None = Form(None),
        refresh_token: str | None = Form(None),
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        try:
            resolved_id, resolved_secret = _resolve_client_credentials(
                authorization=authorization,
                form_client_id=client_id,
                form_client_secret=client_secret,
            )
            if grant_type == "authorization_code":
                if not code or not redirect_uri:
                    raise OAuthError("invalid_request", "code and redirect_uri required")
                result = service.exchange_code(
                    code=code,
                    client_id=resolved_id,
                    client_secret=resolved_secret,
                    redirect_uri=redirect_uri,
                )
            elif grant_type == "refresh_token":
                if not refresh_token:
                    raise OAuthError("invalid_request", "refresh_token required")
                result = service.refresh(
                    refresh_token=refresh_token,
                    client_id=resolved_id,
                    client_secret=resolved_secret,
                )
            else:
                raise OAuthError("unsupported_grant_type", grant_type)
        except OAuthError as e:
            return JSONResponse(
                {"error": e.code, "error_description": e.description},
                status_code=e.status,
            )

        # RFC 6749 §5.1: 부여된 scope가 요청과 다르면 응답에 scope 포함 필수.
        # 동일해도 포함 가능. 클라이언트가 부여된 권한을 정확히 알 수 있도록
        # 비어있지 않은 경우 항상 반환.
        body: dict[str, object] = {
            "access_token": result.access_token,
            "token_type": result.token_type,
            "expires_in": result.expires_in,
            "refresh_token": result.refresh_token,
        }
        if result.scope:
            body["scope"] = result.scope
        return JSONResponse(body)

    @router.get("/.well-known/jwks.json")
    async def jwks() -> JSONResponse:
        return JSONResponse(state.signer.jwks())

    return router
