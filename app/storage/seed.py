from app.domain.patient import Patient, PatientType
from app.domain.user import User
from app.storage.memory import InMemoryStore

_DOCTORS = [
    User(
        id="user-001", username="lee@hospital.com", password="password",
        name="이의사", employee_id="12345", department="내과",
        email="lee@hospital.com", email_verified=True,
    ),
    User(
        id="user-002", username="kim@hospital.com", password="password",
        name="김의사", employee_id="12346", department="외과",
        email="kim@hospital.com", email_verified=True,
    ),
]

_PATIENT_TYPES = [
    PatientType.INPATIENT,
    PatientType.OUTPATIENT,
    PatientType.EMERGENCY,
]


def _build_patients() -> list[Patient]:
    patients: list[Patient] = []
    for i in range(1, 151):
        doctor = _DOCTORS[i % 2]
        ptype = _PATIENT_TYPES[i % 3]
        patients.append(
            Patient(
                patient_uid=f"EHR-{i:04d}",
                name=f"환자{i:03d}",
                attending_physician=doctor.name,
                attending_employee_id=doctor.employee_id,
                patient_type=ptype,
                age=str(20 + (i % 60)),
                is_male=(i % 2 == 0),
                department=doctor.department,
                ward=f"{(i % 5) + 1}병동",
                room=f"{(i % 20) + 301}",
                bed="ABCDE"[i % 5],
                pod=(i % 10) if ptype is PatientType.INPATIENT else None,
                hod=((i % 30) + 1) if ptype is PatientType.INPATIENT else None,
            )
        )
    return patients


def seed_store(store: InMemoryStore) -> None:
    for user in _DOCTORS:
        store.users.save(user)
    store.patients.save_all(_build_patients())
