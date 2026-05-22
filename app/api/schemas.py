from pydantic import BaseModel, ConfigDict, Field


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class UserInfo(_CamelModel):
    sub: str
    preferred_username: str
    name: str
    email: str | None = None
    email_verified: bool | None = None
    employee_id: str = Field(alias="employeeId")
    department: str


class PatientDTO(_CamelModel):
    patient_uid: str = Field(alias="patientUid")
    name: str
    attending_physician: str = Field(alias="attendingPhysician")
    attending_employee_id: str = Field(alias="attendingEmployeeId")
    patient_type: str = Field(alias="patientType")
    age: str | None = None
    is_male: bool | None = Field(default=None, alias="isMale")
    department: str | None = None
    ward: str | None = None
    room: str | None = None
    bed: str | None = None
    pod: int | None = None
    hod: int | None = None


class PatientListResponse(_CamelModel):
    patients: list[PatientDTO]
    page: int | None = None
    page_size: int | None = Field(default=None, alias="pageSize")
    total_count: int | None = Field(default=None, alias="totalCount")
    total_pages: int | None = Field(default=None, alias="totalPages")
