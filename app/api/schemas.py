from typing import Any, Literal

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
    # 다음 페이지 불투명 커서 — 마지막 페이지이거나 전체를 한 번에 반환했으면 null.
    # 클라이언트는 이 값을 다음 요청의 `cursor`로 그대로 보낸다 (FHIR next link 패턴).
    next: str | None = None

    def to_body(self) -> dict[str, Any]:
        """응답 JSON — 환자의 선택 필드·미사용 페이지 필드는 생략하되 `next` 키는 항상 둔다."""
        body = self.model_dump(by_alias=True, exclude_none=True)
        body["next"] = self.next
        return body


# --- 요청 본문 (POST + JSON, FHIR _search 관행) ------------------------------
# 사번·이름 같은 식별자를 URL(쿼리스트링)에 싣지 않는다 — 액세스 로그·프록시에 남기 때문.


class PatientsQuery(_CamelModel):
    """POST /api/patients 본문.

    - 사용자 토큰 모드: {page?, pageSize?} — 사번은 토큰의 sub가 정한다(employeeId 금지)
    - 서비스 토큰 모드: {employeeId, page?, pageSize?}
    - 다음 페이지(모드 공통): {cursor} — 직전 응답의 next 그대로
    """

    employee_id: str | None = Field(default=None, alias="employeeId", min_length=1, max_length=64)
    page: int | None = Field(default=None, ge=1)
    page_size: int | None = Field(default=None, alias="pageSize", ge=1)
    cursor: str | None = Field(default=None, min_length=1, max_length=512)


class EmployeeQuery(_CamelModel):
    """POST /api/employee 본문 — 둘 다 필수, 정확 일치(양끝 공백 제거 외 정규화 없음)."""

    employee_id: str = Field(alias="employeeId", min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)


class EmployeeInfo(_CamelModel):
    employee_id: str = Field(alias="employeeId")
    name: str
    department: str
    department_code: str | None = Field(default=None, alias="departmentCode")
    # 200 응답에서는 항상 true — 재직자가 아니면 200 자체를 내지 않는다
    active: Literal[True] = True
