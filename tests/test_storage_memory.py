from datetime import UTC, datetime, timedelta

from app.domain.auth import AuthCode, RefreshToken
from app.domain.patient import Patient, PatientType
from app.domain.user import User
from app.storage.memory import InMemoryStore


def make_user(uid: str = "user-001") -> User:
    return User(
        id=uid, username=f"{uid}@h", password="p", name="N",
        employee_id="123", department="d", email="e", email_verified=True,
    )


def test_user_save_and_get():
    store = InMemoryStore()
    user = make_user()
    store.users.save(user)
    assert store.users.get(user.id) == user
    assert store.users.get_by_username(user.username) == user
    assert store.users.get("nope") is None


def test_authcode_consume_once():
    store = InMemoryStore()
    code = AuthCode(
        code="c", user_id="u", client_id="s", redirect_uri="r",
        scope="openid", expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    store.auth_codes.save(code)
    assert store.auth_codes.consume("c") == code
    assert store.auth_codes.consume("c") is None  # 1회용


def test_refresh_token_revoke():
    store = InMemoryStore()
    rt = RefreshToken(
        token="rt", user_id="u", client_id="s", scope="openid",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    store.refresh_tokens.save(rt)
    assert store.refresh_tokens.get("rt") == rt
    store.refresh_tokens.revoke("rt")
    fetched = store.refresh_tokens.get("rt")
    assert fetched is not None and fetched.revoked is True


def test_patient_list_by_employee():
    store = InMemoryStore()
    p1 = Patient(patient_uid="A", name="a", attending_physician="이",
                 attending_employee_id="12345", patient_type=PatientType.INPATIENT)
    p2 = Patient(patient_uid="B", name="b", attending_physician="이",
                 attending_employee_id="12345", patient_type=PatientType.OUTPATIENT)
    p3 = Patient(patient_uid="C", name="c", attending_physician="김",
                 attending_employee_id="99999", patient_type=PatientType.EMERGENCY)
    store.patients.save_all([p1, p2, p3])
    assert store.patients.list_by_employee("12345") == [p1, p2]
    assert store.patients.list_by_employee("99999") == [p3]
