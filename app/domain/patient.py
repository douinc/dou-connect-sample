from dataclasses import dataclass
from enum import StrEnum


class PatientType(StrEnum):
    INPATIENT = "inpatient"
    OUTPATIENT = "outpatient"
    EMERGENCY = "emergency"


@dataclass(frozen=True)
class Patient:
    patient_uid: str
    name: str
    attending_physician: str
    attending_employee_id: str
    patient_type: PatientType
    age: str | None = None
    is_male: bool | None = None
    department: str | None = None
    ward: str | None = None
    room: str | None = None
    bed: str | None = None
    pod: int | None = None
    hod: int | None = None
