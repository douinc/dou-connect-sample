from app.api.schemas import PatientDTO, PatientListResponse, UserInfo


def test_userinfo_serialization_uses_camel_keys():
    u = UserInfo(
        sub="user-001", preferred_username="lee@h", name="이",
        email="lee@h", email_verified=True,
        employee_id="123", department="내과",
    )
    body = u.model_dump(by_alias=True)
    assert body["preferred_username"] == "lee@h"
    assert body["employeeId"] == "123"
    assert body["email_verified"] is True


def test_patient_dto_camel():
    p = PatientDTO(
        patient_uid="EHR-1", name="환자", attending_physician="이",
        attending_employee_id="123", patient_type="inpatient",
    )
    body = p.model_dump(by_alias=True, exclude_none=True)
    assert body == {
        "patientUid": "EHR-1", "name": "환자",
        "attendingPhysician": "이", "attendingEmployeeId": "123",
        "patientType": "inpatient",
    }


def test_patient_list_with_pagination():
    resp = PatientListResponse(
        patients=[], page=1, page_size=50, total_count=150, total_pages=3,
    )
    body = resp.model_dump(by_alias=True, exclude_none=True)
    assert body["pageSize"] == 50
    assert body["totalCount"] == 150
    assert body["totalPages"] == 3
