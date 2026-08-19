import pytest
from pydantic import ValidationError

from app.connect.schemas import (
    PartnerApiEndpoint,
    PartnerApiEndpoints,
    PartnerApiOAuth,
    PartnerApiRequest,
    PartnerApiResponse,
    PartnerApiService,
    RecordDetail,
    RecordSummary,
    TokenIssueResponse,
    WebhookRegisterResponse,
)


def test_token_issue_response_parse():
    body = {
        "access_token": "abc",
        "token_type": "Bearer",
        "expires_in": 900,
    }
    r = TokenIssueResponse.model_validate(body)
    assert r.access_token == "abc"
    assert r.expires_in == 900


def test_partner_api_request_with_oauth_serializes_camel():
    """IdP 로그인 위임 포함 — oauth 그룹 + endpoints.patients(사용자 토큰 모드라 service 불필요)."""
    req = PartnerApiRequest(
        oauth=PartnerApiOAuth(
            authorization_url="https://p.example/authorize",
            token_url="https://p.example/token",
            user_info_url="https://p.example/api/userinfo",
            client_id="c",
            client_secret="s",
            scopes=["openid", "profile"],
        ),
        endpoints=PartnerApiEndpoints(
            patients=PartnerApiEndpoint(url="https://p.example/api/patients"),
        ),
    )
    body = req.model_dump(by_alias=True, exclude_none=True)
    assert body == {
        "oauth": {
            "authorizationUrl": "https://p.example/authorize",
            "tokenUrl": "https://p.example/token",
            "userInfoUrl": "https://p.example/api/userinfo",
            "clientId": "c",
            "clientSecret": "s",
            "scopes": ["openid", "profile"],
        },
        "endpoints": {"patients": {"url": "https://p.example/api/patients"}},
    }
    assert "service" not in body


def test_partner_api_request_service_mode_serializes_camel():
    """IdP 없이 서비스 토큰 모드만 — service.audience + endpoints.employee/patients."""
    req = PartnerApiRequest(
        service=PartnerApiService(audience="partner-emr"),
        endpoints=PartnerApiEndpoints(
            employee=PartnerApiEndpoint(url="https://p.example/api/employee"),
            patients=PartnerApiEndpoint(url="https://p.example/api/patients"),
        ),
    )
    body = req.model_dump(by_alias=True, exclude_none=True)
    assert body == {
        "service": {"audience": "partner-emr"},
        "endpoints": {
            "employee": {"url": "https://p.example/api/employee"},
            "patients": {"url": "https://p.example/api/patients"},
        },
    }


def test_partner_api_oauth_requires_all_fields():
    """oauth 그룹은 넣으면 전부 필수(반쪽 IdP 불허) — 누락은 클라이언트에서 먼저 걸린다."""
    with pytest.raises(ValidationError):
        PartnerApiOAuth.model_validate({
            "authorizationUrl": "https://p.example/authorize",
            "tokenUrl": "https://p.example/token",
            "clientId": "c",
            "clientSecret": "s",
            "scopes": ["openid"],
        })
    with pytest.raises(ValidationError):
        PartnerApiOAuth.model_validate({
            "authorizationUrl": "https://p.example/authorize",
            "tokenUrl": "https://p.example/token",
            "userInfoUrl": "https://p.example/api/userinfo",
            "clientId": "c",
            "clientSecret": "s",
            "scopes": [],
        })


def test_partner_api_response_parses_derived_auth_and_redirect_uri():
    """응답: endpoints.*.auth(파생)·oauth.redirectUri 포함, clientSecret 없음."""
    body = {
        "partnerId": "partner-1",
        "service": {"audience": "partner-emr"},
        "oauth": {
            "authorizationUrl": "https://p.example/authorize",
            "tokenUrl": "https://p.example/token",
            "userInfoUrl": "https://p.example/api/userinfo",
            "clientId": "c",
            "scopes": ["openid"],
            "redirectUri": "https://connect.dou.so/api/saylog/v1/oauth/callback",
        },
        "endpoints": {
            "patients": {"url": "https://p.example/api/patients", "auth": "user"},
            "employee": {"url": "https://p.example/api/employee", "auth": "service"},
        },
        "isActive": True,
        "createdAt": "2026-08-19T00:00:00Z",
        "updatedAt": "2026-08-19T00:00:00Z",
    }
    r = PartnerApiResponse.model_validate(body)
    assert r.partner_id == "partner-1"
    assert r.service is not None and r.service.audience == "partner-emr"
    assert r.oauth is not None
    assert r.oauth.redirect_uri == "https://connect.dou.so/api/saylog/v1/oauth/callback"
    assert r.endpoints.patients is not None and r.endpoints.patients.auth == "user"
    assert r.endpoints.employee is not None and r.endpoints.employee.auth == "service"
    assert r.is_active is True


def test_partner_api_response_without_oauth_or_service():
    body = {
        "partnerId": "partner-1",
        "endpoints": {},
        "isActive": True,
        "createdAt": "2026-08-19T00:00:00Z",
        "updatedAt": "2026-08-19T00:00:00Z",
    }
    r = PartnerApiResponse.model_validate(body)
    assert r.oauth is None and r.service is None
    assert r.endpoints.patients is None and r.endpoints.employee is None


def test_webhook_register_response():
    body = {
        "webhookId": "wh_1",
        "url": "http://x",
        "event": "records.summarized",
        "createdAt": "2026-05-15T00:00:00Z",
        "updatedAt": "2026-05-15T00:00:00Z",
        "secret": "S" * 64,
    }
    r = WebhookRegisterResponse.model_validate(body)
    assert r.webhook_id == "wh_1"
    assert r.event == "records.summarized"
    assert r.secret == "S" * 64


def test_record_summary_parse():
    body = {
        "recordId": "rec_1",
        "patientName": "홍길동",
        "recorderName": "김의사",
        "createdAt": "2026-05-15T00:00:00Z",
        "tldr": "고혈압 추적관찰",
    }
    r = RecordSummary.model_validate(body)
    assert r.record_id == "rec_1"
    assert r.patient_name == "홍길동"
    assert r.recorder_name == "김의사"
    assert r.created_at == "2026-05-15T00:00:00Z"
    assert r.tldr == "고혈압 추적관찰"
    assert r.patient_uid is None


def test_record_detail_parse_includes_patient_snapshot():
    body = {
        "recordId": "rec_1",
        "patientName": "홍길동",
        "recorderName": "김의사",
        "createdAt": "2026-05-15T00:00:00Z",
        "patientAge": "57",
        "patientIsMale": True,
        "patientDepartment": "내과",
        "patientWard": "5W",
    }
    r = RecordDetail.model_validate(body)
    assert r.patient_age == "57"
    assert r.patient_is_male is True
    assert r.patient_department == "내과"
    assert r.patient_ward == "5W"


def test_record_summary_parses_source():
    body = {
        "recordId": "rec_1",
        "patientName": "홍길동",
        "recorderName": "김의사",
        "createdAt": "2026-05-15T00:00:00Z",
        "source": "saylog-watch",
    }
    r = RecordSummary.model_validate(body)
    assert r.source == "saylog-watch"


def test_record_summary_without_source_is_none():
    # source가 없는 구 응답도 수용 (하위호환)
    body = {
        "recordId": "rec_1",
        "patientName": "홍길동",
        "recorderName": "김의사",
        "createdAt": "2026-05-15T00:00:00Z",
    }
    r = RecordSummary.model_validate(body)
    assert r.source is None


def test_record_detail_parses_delivery_fields():
    body = {
        "recordId": "rec_1",
        "patientName": "홍길동",
        "recorderName": "김의사",
        "createdAt": "2026-05-15T00:00:00Z",
        "source": "connect-api",
        "deliveryStatus": "REJECTED",
        "deliveryDetail": "환자번호 불일치",
        "deliveryReportedAt": "2026-05-15T01:00:00Z",
    }
    r = RecordDetail.model_validate(body)
    assert r.delivery_status == "REJECTED"
    assert r.delivery_detail == "환자번호 불일치"
    assert r.delivery_reported_at == "2026-05-15T01:00:00Z"


def test_record_detail_without_delivery_report_is_null():
    # delivery-status 미보고 시 세 필드 모두 null
    body = {
        "recordId": "rec_1",
        "patientName": "홍길동",
        "recorderName": "김의사",
        "createdAt": "2026-05-15T00:00:00Z",
    }
    r = RecordDetail.model_validate(body)
    assert r.delivery_status is None
    assert r.delivery_detail is None
    assert r.delivery_reported_at is None
