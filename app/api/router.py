"""새록이 호출하는 파트너 API (A 세그먼트).

- GET  /api/userinfo  — OIDC userinfo (사용자 토큰)          · oauth.userInfoUrl
- POST /api/patients  — 담당 환자 목록 (사용자 또는 서비스 토큰) · endpoints.patients
- POST /api/employee  — 직원 조회 (서비스 토큰)               · endpoints.employee

patients/employee는 POST + JSON 본문이다(FHIR `_search` 관행): 사번·이름이 URL에
실리면 액세스 로그·프록시에 평문으로 남는다. 부수효과가 없어 재시도해도 안전하다.
세 응답 모두 PHI라 `Cache-Control: no-store`.
"""

from collections.abc import Callable
from typing import Annotated, Any, TypeGuard

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.dependencies import NO_STORE_HEADERS, verify_bearer_token
from app.api.pagination import Cursor, decode_cursor, encode_cursor, paginate
from app.api.schemas import (
    EmployeeInfo,
    EmployeeQuery,
    PatientDTO,
    PatientListResponse,
    PatientsQuery,
    UserInfo,
)
from app.api.service_token import require_service_token
from app.dependencies import AppState
from app.domain.patient import Patient
from app.domain.user import User

# 서비스 토큰에 요구하는 scope (dou-connect에 등록한 파트너 리소스 서버의 scope 이름)
SCOPE_STAFF_READ = "staff:read"
SCOPE_PATIENTS_READ = "patients:read"

_NO_ECHO_ROUTE_NAMES = frozenset({"patients", "employee"})


class NotFoundNoBody(Exception):
    """본문 없는 404 — 직원 없음/다른 병원. `HTTPException(404)`는 `{"detail": ...}`를 싣는다."""


def install_exception_handlers(app: FastAPI) -> None:
    """/api/patients·/api/employee 전용 오류 응답 형식.

    - 422: FastAPI 기본 본문은 `detail[i].input`에 잘못된 입력을 그대로 돌려주는데, 이 두
      라우트에서 그 값은 사번이나 이름이다. 가이드: "본문에 입력값을 되돌려 넣지 마세요".
    - 404(NotFoundNoBody): 본문 없이, no-store 헤더만.
    """

    @app.exception_handler(RequestValidationError)
    async def _no_echo_422(request: Request, exc: RequestValidationError) -> Response:
        route = request.scope.get("route")
        if getattr(route, "name", None) in _NO_ECHO_ROUTE_NAMES:
            return JSONResponse(
                status_code=422,
                content={"detail": "invalid request body"},
                headers=NO_STORE_HEADERS,
            )
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(NotFoundNoBody)
    async def _empty_404(request: Request, exc: NotFoundNoBody) -> Response:
        return Response(status_code=404, headers=NO_STORE_HEADERS)


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


def _invalid_body(reason: str) -> HTTPException:
    # 사유는 고정 문자열만 — 입력값을 섞지 않는다
    return HTTPException(422, reason, headers=NO_STORE_HEADERS)


def build_api_router(state: AppState) -> APIRouter:
    router = APIRouter(prefix="/api")

    def _user_claims(authorization: str | None) -> dict[str, Any]:
        return verify_bearer_token(
            authorization=authorization,
            signer=state.signer,
            audience="saylog",
        )

    def _service_auth(scope: str) -> Callable[..., dict[str, Any]]:
        """서비스 토큰 인증을 라우트 `Depends`로 건다.

        인증을 핸들러 본문이 아니라 의존성으로 두는 이유: FastAPI는 의존성을 요청
        본문 검증보다 먼저 평가하므로, 토큰 없는 호출이 422(본문 오류)가 아니라
        401을 받는다 — 미인증 호출자에게 검증기를 노출하지 않는다(RFC 6750 순서).
        sync 함수라 FastAPI가 threadpool에서 돌려 JWKS 네트워크 조회가 이벤트
        루프를 막지 않는다.
        """

        def dependency(authorization: str | None = Header(default=None)) -> dict[str, Any]:
            return _service_claims(authorization, scope)

        return dependency

    def _service_claims(authorization: str | None, scope: str) -> dict[str, Any]:
        if not state.settings.service_token_audience:
            # 서버 설정 누락은 호출자의 인증 실패(401)가 아니라 서버 오류다 (웹훅 secret과 동일)
            raise HTTPException(500, "SERVICE_TOKEN_AUDIENCE not configured")
        claims = require_service_token(
            authorization=authorization,
            verifier=state.service_verifier,
            required_scope=scope,
        )
        # 병원 격리: 토큰의 provider_code가 이 서버가 서비스하는 병원이 아니면 404
        # (리소스 서버 가이드 — 매핑 없는 병원). 단일 병원 샘플은 DOU_CONNECT_PROVIDER_CODE
        # 와 대조하고, 미설정이면 검사를 생략한다. 다병원 파트너는 여기서 병원을 resolve해
        # 그 병원 명단으로만 조회하도록 바꾼다.
        expected = state.settings.dou_connect_provider_code
        if expected and claims.get("provider_code") != expected:
            raise NotFoundNoBody()
        return claims

    @router.get("/userinfo", response_model=UserInfo, response_model_by_alias=True)
    async def userinfo(
        response: Response,
        authorization: str | None = Header(default=None),
    ) -> UserInfo:
        claims = _user_claims(authorization)
        user = state.store.users.get(claims["sub"])
        if user is None:
            raise HTTPException(404, "User not found")
        response.headers.update(NO_STORE_HEADERS)
        return UserInfo(
            sub=user.id,
            preferred_username=user.username,
            name=user.name,
            email=user.email,
            email_verified=user.email_verified,
            employeeId=user.employee_id,
            department=user.department,
        )

    def _patients_auth(authorization: str | None = Header(default=None)) -> User | None:
        """모드별 인증 (본문 검증보다 먼저) — user 모드는 사용자, service 모드는 None."""
        if state.settings.patients_auth_mode == "user":
            claims = _user_claims(authorization)
            user = state.store.users.get(claims["sub"])
            if user is None:
                raise HTTPException(404, "User not found")
            return user
        _service_claims(authorization, SCOPE_PATIENTS_READ)
        return None

    @router.post("/patients", response_model=PatientListResponse, response_model_by_alias=True)
    def patients(
        body: PatientsQuery,
        auth_user: Annotated[User | None, Depends(_patients_auth)],
    ) -> Response:
        """담당 환자 목록 — `attendingEmployeeId == 사번`인 환자만.

        사번의 출처는 등록 상태로 정해진 한 모드(PATIENTS_AUTH_MODE)다:
          user    — 파트너 IdP 사용자 토큰의 sub → 그 사용자의 사번. 본문 employeeId 금지.
          service — dou-connect 서비스 토큰(scope patients:read) + 본문 employeeId.
        다음 페이지는 {cursor}만 보낸다 — 사번은 커서 안에 있다.
        """
        cursor = _resolve_cursor(body)
        if auth_user is not None:
            if body.employee_id is not None:
                raise _invalid_body("employeeId is not accepted in user token mode")
            if cursor is not None and cursor.employee_id != auth_user.employee_id:
                # 다른 사용자에게 발급된 커서 — 사번은 토큰이 정한다
                raise _invalid_body("invalid cursor")
            employee_id = auth_user.employee_id
        else:
            if cursor is not None:
                employee_id = cursor.employee_id
            elif body.employee_id is not None:
                employee_id = body.employee_id.strip()
            else:
                raise _invalid_body("employeeId or cursor is required")
            if not _is_active_employee(state.store.users.get_by_employee_id(employee_id)):
                # 미존재·퇴직 → 담당 환자 0명인 재직 직원과 같은 모양(열거 신호 없음)
                return _patients_response([], body, cursor, employee_id)

        rows = state.store.patients.list_by_employee(employee_id)
        return _patients_response([_patient_to_dto(p) for p in rows], body, cursor, employee_id)

    @router.post(
        "/employee",
        response_model=EmployeeInfo,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        responses={
            404: {
                "description": "일치하는 재직 직원 없음 — 본문 없음. "
                "미존재/이름 불일치/퇴직을 구분하지 않는다."
            }
        },
    )
    def employee(
        body: EmployeeQuery,
        response: Response,
        _claims: Annotated[dict[str, Any], Depends(_service_auth(SCOPE_STAFF_READ))],
    ) -> EmployeeInfo:
        """직원 조회 — 사번+이름 정확 일치(양끝 공백 제거만) + 재직이면 200, 아니면 빈 404.

        항상 dou-connect 서비스 토큰(scope staff:read). 404는 본문 없이, 어느 쪽이
        틀렸는지 구분 없이 — 응답으로 병원 명단을 추측할 수 없어야 한다. 로그에도
        사번·이름을 남기지 않는다.
        """
        user = state.store.users.get_by_employee_id(body.employee_id.strip())
        if not _is_active_employee(user) or user.name.strip() != body.name.strip():
            raise NotFoundNoBody()
        response.headers.update(NO_STORE_HEADERS)
        return EmployeeInfo(
            employeeId=user.employee_id,
            name=user.name.strip(),
            department=user.department,
        )

    return router


def _is_active_employee(user: User | None) -> TypeGuard[User]:
    return user is not None and user.active


def _resolve_cursor(body: PatientsQuery) -> Cursor | None:
    if body.cursor is None:
        return None
    cursor = decode_cursor(body.cursor)
    if cursor is None:
        raise _invalid_body("invalid cursor")
    return cursor


def _patients_response(
    dtos: list[PatientDTO],
    body: PatientsQuery,
    cursor: Cursor | None,
    employee_id: str,
) -> JSONResponse:
    if cursor is None and body.page is None and body.page_size is None:
        # 파라미터 없음 → 전체 목록, 페이지 필드 생략 가능, next는 null
        resp = PatientListResponse(patients=dtos)
    else:
        page_no, size = (cursor.page, cursor.page_size) if cursor else (body.page, body.page_size)
        page = paginate(dtos, page_no, size)
        nxt = (
            encode_cursor(Cursor(employee_id, page.page + 1, page.page_size))
            if page.has_next
            else None
        )
        resp = PatientListResponse(
            patients=page.items,
            page=page.page,
            pageSize=page.page_size,
            totalCount=page.total_count,
            totalPages=page.total_pages,
            next=nxt,
        )
    return JSONResponse(content=resp.to_body(), headers=NO_STORE_HEADERS)
