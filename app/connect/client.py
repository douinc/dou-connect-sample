import base64
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any

import httpx

from app.connect.schemas import (
    IdentityProviderRequest,
    RecordDetail,
    RecordSummary,
    TokenIssueResponse,
    WebhookRegisterResponse,
    WebhookSummary,
)


class ConnectClient:
    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        client_secret: str,
        audience: str = "saylog",
        scope: str | None = None,
        provider_code: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        # base_url은 dou-connect 호스트 루트(예: http://localhost,
        # https://connect.dou.so). dou-connect는 OAuth 토큰 엔드포인트
        # (`/v1/oauth/token`, web.php)와 게이트웨이 프록시
        # (`/api/{service}/{path}`, api.php)를 서로 다른 루트에 둔다.
        # httpx의 RFC 3986 결합 규칙상 base.path를 보존하려면 trailing
        # slash가 필요하므로 강제로 추가한다.
        self._base_url = base_url.rstrip("/") + "/"
        self._client_id = client_id
        self._client_secret = client_secret
        self._audience = audience
        self._scope = scope
        # tenant-required service(saylog 등)는 token 발급 시 provider_code
        # (Hospital.provider_code, 요양기관번호)로 어느 병원인지 지정 필수.
        # 미지정 시 dou-connect가 403 access_denied로 거부.
        self._provider_code = provider_code
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._http = httpx.AsyncClient(
            base_url=self._base_url, transport=transport, timeout=timeout,
        )

    async def __aenter__(self) -> "ConnectClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._http.aclose()

    async def _get_token(self, force: bool = False) -> str:
        now = datetime.now(UTC)
        if (
            not force and self._token is not None
            and self._token_expires_at is not None
            and now < self._token_expires_at - timedelta(seconds=60)
        ):
            return self._token

        # RFC 6749 §2.3.1 Basic 인증. 본문에 client_id/secret을 함께
        # 보내면 dou-connect가 `invalid_request`로 거부하므로 둘 중 하나만
        # 사용한다. 본 클라이언트는 Basic 헤더 방식을 사용한다.
        creds = f"{self._client_id}:{self._client_secret}".encode()
        basic = base64.b64encode(creds).decode("ascii")
        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "audience": self._audience,
        }
        if self._scope:
            data["scope"] = self._scope
        if self._provider_code:
            data["provider_code"] = self._provider_code

        r = await self._http.post(
            "v1/oauth/token",
            data=data,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        r.raise_for_status()
        parsed = TokenIssueResponse.model_validate(r.json())
        self._token = parsed.access_token
        self._token_expires_at = now + timedelta(seconds=parsed.expires_in)
        return self._token

    async def _request(
        self, method: str, path: str, **kwargs: Any,
    ) -> httpx.Response:
        # 게이트웨이 프록시 호출 전용. path는 `{service}/{path}`
        # (예: `saylog/v1/identity-provider`)로 받고 dou-connect의 `/api`
        # 라우트 그룹에 맞춰 prefix를 prepend한다. 토큰 엔드포인트
        # (`/v1/oauth/token`)는 별도 루트라 `_get_token`이 따로 처리.
        gateway_path = f"api/{path}"
        token = await self._get_token()
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {token}"
        r = await self._http.request(method, gateway_path, headers=headers, **kwargs)
        if r.status_code == 401:
            token = await self._get_token(force=True)
            headers["Authorization"] = f"Bearer {token}"
            r = await self._http.request(
                method, gateway_path, headers=headers, **kwargs,
            )
        return r

    async def issue_token(self) -> TokenIssueResponse:
        token = await self._get_token(force=True)
        expires_in = 0
        if self._token_expires_at is not None:
            expires_in = int(
                (self._token_expires_at - datetime.now(UTC)).total_seconds()
            )
        return TokenIssueResponse(
            access_token=token,
            token_type="Bearer",
            expires_in=expires_in,
            scope=self._scope,
        )

    async def register_identity_provider(
        self, idp: IdentityProviderRequest,
    ) -> dict[str, Any]:
        r = await self._request(
            "PUT", "saylog/v1/identity-provider",
            json=idp.model_dump(by_alias=True),
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    async def get_identity_provider(self) -> dict[str, Any]:
        r = await self._request("GET", "saylog/v1/identity-provider")
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    async def start_partner_oauth(self) -> dict[str, Any]:
        # dou-connect 게이트웨이를 거쳐 saylog 서비스의 partner-oauth 시작을 호출.
        # 인자 없음 — saylog 측에서 토큰 claim의 partner_id로 어느 파트너 흐름인지 판단.
        # 응답: {"authorizationUrl": "...", "nonce": "..."}. authorizationUrl을
        # 브라우저로 열면 파트너 OAuth 서버로 redirect되고, 완료 후 dou-connect
        # 게이트웨이의 콜백 경로로 돌아온다.
        r = await self._request("POST", "saylog/v1/partner-oauth/start")
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    async def validate_partner_api(
        self, partner_user_access_token: str,
    ) -> dict[str, Any]:
        # 새록은 이 토큰으로 파트너의 /api/userinfo·/api/patients를 호출해 스펙을
        # 검증한다. 따라서 이 토큰은 **파트너 OAuth에 사용자가 로그인해서 받은**
        # 토큰이어야 하며, dou-connect의 client-credentials 토큰과 다르다.
        # wire contract상 헤더명은 `Partner-Access-Token`이지만 의미상 사용자
        # 토큰을 담는다.
        r = await self._request(
            "POST", "saylog/v1/validate-partner-api",
            headers={"Partner-Access-Token": partner_user_access_token},
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    async def register_webhook(self, *, url: str) -> WebhookRegisterResponse:
        # ConnectWebhookCreateRequest.event는 const "records.summarized"이며
        # 단일 값. 서버 측 default가 있어 본문에서 생략해도 되지만, 명시적으로
        # 보내 향후 확장 시에도 의도가 분명히 드러나도록 한다.
        r = await self._request(
            "POST", "saylog/v1/webhooks",
            json={"url": url, "event": "records.summarized"},
        )
        r.raise_for_status()
        return WebhookRegisterResponse.model_validate(r.json())

    async def list_webhooks(self) -> list[WebhookSummary]:
        r = await self._request("GET", "saylog/v1/webhooks")
        r.raise_for_status()
        payload = r.json()
        return [WebhookSummary.model_validate(x) for x in payload["webhooks"]]

    async def delete_webhook(self, webhook_id: str) -> None:
        r = await self._request("DELETE", f"saylog/v1/webhooks/{webhook_id}")
        r.raise_for_status()

    async def list_records(
        self,
        *,
        since: str | None = None,
        employee_id: str | None = None,
        patient_uid: str | None = None,
        limit: int | None = None,
    ) -> list[RecordSummary]:
        # ConnectRecordListResponse는 {"records": [...]} 래퍼 + 쿼리는
        # since / employeeId / patientUid / limit(1~100, 기본 50)만 허용.
        params: dict[str, str | int] = {}
        if since is not None:
            params["since"] = since
        if employee_id is not None:
            params["employeeId"] = employee_id
        if patient_uid is not None:
            params["patientUid"] = patient_uid
        if limit is not None:
            params["limit"] = limit
        r = await self._request("GET", "saylog/v1/records", params=params)
        r.raise_for_status()
        payload = r.json()
        return [RecordSummary.model_validate(x) for x in payload["records"]]

    async def get_record(self, record_id: str) -> RecordDetail:
        r = await self._request("GET", f"saylog/v1/records/{record_id}")
        r.raise_for_status()
        return RecordDetail.model_validate(r.json())
