import math
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.api.dependencies import verify_bearer_token
from app.api.schemas import PatientDTO, PatientListResponse, UserInfo
from app.dependencies import AppState
from app.domain.patient import Patient


def _patient_to_dto(p: Patient) -> PatientDTO:
    return PatientDTO(
        patientUid=p.patient_uid,
        name=p.name,
        attendingPhysician=p.attending_physician,
        attendingEmployeeId=p.attending_employee_id,
        patientType=p.patient_type.value,
        age=p.age,
        isMale=p.is_male,
        department=p.department,
        ward=p.ward,
        room=p.room,
        bed=p.bed,
        pod=p.pod,
        hod=p.hod,
    )


def build_api_router(state: AppState) -> APIRouter:
    router = APIRouter(prefix="/api")

    def _verify(authorization: str | None) -> dict[str, Any]:
        return verify_bearer_token(
            authorization=authorization, signer=state.signer, audience="saylog",
        )

    @router.get("/userinfo", response_model=UserInfo, response_model_by_alias=True)
    async def userinfo(authorization: str | None = Header(default=None)) -> UserInfo:
        claims = _verify(authorization)
        user = state.store.users.get(claims["sub"])
        if user is None:
            raise HTTPException(404, "User not found")
        return UserInfo(
            sub=user.id,
            preferred_username=user.username,
            name=user.name,
            email=user.email,
            email_verified=user.email_verified,
            employeeId=user.employee_id,
            department=user.department,
        )

    @router.get(
        "/patients",
        response_model=PatientListResponse,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    async def patients(
        authorization: str | None = Header(default=None),
        page: int | None = Query(default=None, ge=1),
        pageSize: int | None = Query(default=None, ge=1, le=500),
    ) -> PatientListResponse:
        claims = _verify(authorization)
        user = state.store.users.get(claims["sub"])
        if user is None:
            raise HTTPException(404, "User not found")

        all_patients = state.store.patients.list_by_employee(user.employee_id)
        dtos = [_patient_to_dto(p) for p in all_patients]

        if page is None and pageSize is None:
            return PatientListResponse(patients=dtos)

        if page is None or pageSize is None:
            raise HTTPException(400, "page and pageSize must be provided together")

        total_count = len(dtos)
        total_pages = math.ceil(total_count / pageSize) if total_count > 0 else 0
        start = (page - 1) * pageSize
        end = start + pageSize
        return PatientListResponse(
            patients=dtos[start:end],
            page=page,
            pageSize=pageSize,
            totalCount=total_count,
            totalPages=total_pages,
        )

    return router
