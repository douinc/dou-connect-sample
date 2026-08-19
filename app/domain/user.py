from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    id: str
    username: str
    password: str
    name: str
    employee_id: str
    department: str
    email: str
    email_verified: bool
    # 재직 여부 — 직원 조회(employee)는 재직자만 200, 환자 목록 서비스 토큰 모드는
    # 퇴직자를 미존재와 같은 빈 목록으로 다룬다. 샘플의 OAuth 로그인은 이 값을 보지 않는다.
    active: bool = True
