from datetime import UTC, datetime, timedelta

from app.domain.auth import AuthCode, RefreshToken
from app.domain.patient import Patient, PatientType
from app.domain.user import User


def test_user_construction():
    user = User(
        id="user-001",
        username="lee@hospital.com",
        password="pw",
        name="이의사",
        employee_id="12345",
        department="내과",
        email="lee@hospital.com",
        email_verified=True,
    )
    assert user.id == "user-001"


def test_patient_with_optional_fields():
    p = Patient(
        patient_uid="EHR-001",
        name="김환자",
        attending_physician="이의사",
        attending_employee_id="12345",
        patient_type=PatientType.INPATIENT,
        age="45",
        is_male=True,
        department="내과",
        ward="3병동",
        room="301",
        bed="A",
        pod=3,
        hod=5,
    )
    assert p.patient_type is PatientType.INPATIENT


def test_authcode_expiry():
    now = datetime.now(UTC)
    code = AuthCode(
        code="abc",
        user_id="user-001",
        client_id="saylog-client",
        redirect_uri="http://cb",
        scope="openid",
        expires_at=now - timedelta(seconds=1),
    )
    assert code.is_expired(at=now) is True


def test_refresh_token_is_active():
    now = datetime.now(UTC)
    rt = RefreshToken(
        token="rt",
        user_id="user-001",
        client_id="saylog-client",
        scope="openid",
        expires_at=now + timedelta(days=30),
        revoked=False,
    )
    assert rt.is_active(at=now) is True
    rt2 = RefreshToken(
        token="rt2",
        user_id="user-001",
        client_id="saylog-client",
        scope="openid",
        expires_at=now + timedelta(days=30),
        revoked=True,
    )
    assert rt2.is_active(at=now) is False
