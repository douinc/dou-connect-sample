from app.connect.schemas import (
    IdentityProviderRequest,
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


def test_identity_provider_request_serializes_camel():
    req = IdentityProviderRequest(
        authorization_url="http://a",
        token_url="http://t",
        user_info_url="http://u",
        user_patients_url="http://p",
        client_id="c",
        client_secret="s",
        scopes=["openid", "profile"],
    )
    body = req.model_dump(by_alias=True)
    assert body["authorizationUrl"] == "http://a"
    assert body["userPatientsUrl"] == "http://p"
    assert body["clientId"] == "c"
    assert body["scopes"] == ["openid", "profile"]


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
