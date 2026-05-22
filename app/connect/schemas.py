from pydantic import BaseModel, ConfigDict, Field


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class TokenIssueResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    scope: str | None = None


class IdentityProviderRequest(_CamelModel):
    authorization_url: str = Field(alias="authorizationUrl")
    token_url: str = Field(alias="tokenUrl")
    user_info_url: str = Field(alias="userInfoUrl")
    user_patients_url: str = Field(alias="userPatientsUrl")
    client_id: str = Field(alias="clientId")
    client_secret: str = Field(alias="clientSecret")
    scopes: list[str] = Field(min_length=1)


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


class RecordDetail(RecordSummary):
    patient_age: str | None = Field(default=None, alias="patientAge")
    patient_is_male: bool | None = Field(default=None, alias="patientIsMale")
    patient_department: str | None = Field(
        default=None, alias="patientDepartment",
    )
    patient_ward: str | None = Field(default=None, alias="patientWard")
