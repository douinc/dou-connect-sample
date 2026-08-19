from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class TokenIssueResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    scope: str | None = None


# --- 파트너 API 등록 (PUT/GET saylog/v1/partner-api) ---------------------------
# 새록이 호출할 파트너 측 주소·자격을 한 객체로 등록한다 (파트너당 1개, PUT은 전체 교체).
#   service.audience  서비스 토큰 모드 항목이 있으면 필수 — 파트너 리소스 서버의 aud
#   oauth             IdP 로그인 위임(선택 그룹, 넣으면 전부 필수)
#   endpoints         patients(담당 환자 목록) / employee(직원 조회) — 항목 단위 선택


class PartnerApiService(_CamelModel):
    audience: str


class PartnerApiOAuth(_CamelModel):
    authorization_url: str = Field(alias="authorizationUrl")
    token_url: str = Field(alias="tokenUrl")
    user_info_url: str = Field(alias="userInfoUrl")
    client_id: str = Field(alias="clientId")
    client_secret: str = Field(alias="clientSecret")
    scopes: list[str] = Field(min_length=1)


class PartnerApiEndpoint(_CamelModel):
    url: str


class PartnerApiEndpoints(_CamelModel):
    patients: PartnerApiEndpoint | None = None
    employee: PartnerApiEndpoint | None = None


class PartnerApiRequest(_CamelModel):
    service: PartnerApiService | None = None
    oauth: PartnerApiOAuth | None = None
    endpoints: PartnerApiEndpoints | None = None


class PartnerApiOAuthInfo(_CamelModel):
    """등록 응답의 oauth — clientSecret 대신 새록 콜백 redirectUri가 온다."""
    authorization_url: str = Field(alias="authorizationUrl")
    token_url: str = Field(alias="tokenUrl")
    user_info_url: str = Field(alias="userInfoUrl")
    client_id: str = Field(alias="clientId")
    scopes: list[str]
    redirect_uri: str = Field(alias="redirectUri")


class PartnerApiEndpointInfo(_CamelModel):
    url: str
    # 새록이 정하는 파생값: patients는 oauth가 있으면 user, 없으면 service. employee는 항상 service.
    auth: Literal["user", "service"]


class PartnerApiEndpointsInfo(_CamelModel):
    patients: PartnerApiEndpointInfo | None = None
    employee: PartnerApiEndpointInfo | None = None


class PartnerApiResponse(_CamelModel):
    partner_id: str = Field(alias="partnerId")
    service: PartnerApiService | None = None
    oauth: PartnerApiOAuthInfo | None = None
    endpoints: PartnerApiEndpointsInfo
    is_active: bool = Field(alias="isActive")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class WebhookRegisterResponse(_CamelModel):
    webhook_id: str = Field(alias="webhookId")
    url: str
    event: str
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    secret: str


class WebhookSummary(_CamelModel):
    webhook_id: str = Field(alias="webhookId")
    url: str
    event: str
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class RecordSummary(_CamelModel):
    record_id: str = Field(alias="recordId")
    patient_name: str = Field(alias="patientName")
    recorder_name: str = Field(alias="recorderName")
    created_at: str = Field(alias="createdAt")
    patient_uid: str | None = Field(default=None, alias="patientUid")
    summary: str | None = None
    tldr: str | None = None
    template_id: str | None = Field(default=None, alias="templateId")
    recorder_employee_id: str | None = Field(
        default=None, alias="recorderEmployeeId",
    )
    summary_created_at: str | None = Field(
        default=None, alias="summaryCreatedAt",
    )
    # 기록 유입 경로: connect-api | saylog-mobile | saylog-watch | unknown
    source: str | None = None


class RecordDetail(RecordSummary):
    patient_age: str | None = Field(default=None, alias="patientAge")
    patient_is_male: bool | None = Field(default=None, alias="patientIsMale")
    patient_department: str | None = Field(
        default=None, alias="patientDepartment",
    )
    patient_ward: str | None = Field(default=None, alias="patientWard")
    # EMR 반영 상태 보고(delivery-status API)로 기록된 값 — 미보고 시 모두 null
    delivery_status: str | None = Field(default=None, alias="deliveryStatus")
    delivery_detail: str | None = Field(default=None, alias="deliveryDetail")
    delivery_reported_at: str | None = Field(
        default=None, alias="deliveryReportedAt",
    )
