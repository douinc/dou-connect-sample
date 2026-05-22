from dataclasses import dataclass, field

from app.domain.auth import AuthCode, RefreshToken
from app.domain.patient import Patient
from app.domain.user import User


@dataclass
class _UserStoreMem:
    _by_id: dict[str, User] = field(default_factory=dict)
    _by_username: dict[str, User] = field(default_factory=dict)

    def save(self, user: User) -> None:
        self._by_id[user.id] = user
        self._by_username[user.username] = user

    def get(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    def get_by_username(self, username: str) -> User | None:
        return self._by_username.get(username)


@dataclass
class _AuthCodeStoreMem:
    _codes: dict[str, AuthCode] = field(default_factory=dict)

    def save(self, code: AuthCode) -> None:
        self._codes[code.code] = code

    def consume(self, code: str) -> AuthCode | None:
        return self._codes.pop(code, None)


@dataclass
class _RefreshTokenStoreMem:
    _tokens: dict[str, RefreshToken] = field(default_factory=dict)

    def save(self, token: RefreshToken) -> None:
        self._tokens[token.token] = token

    def get(self, token: str) -> RefreshToken | None:
        return self._tokens.get(token)

    def revoke(self, token: str) -> None:
        rt = self._tokens.get(token)
        if rt is not None:
            rt.revoked = True


@dataclass
class _PatientStoreMem:
    _patients: list[Patient] = field(default_factory=list)

    def save_all(self, patients: list[Patient]) -> None:
        self._patients.extend(patients)

    def list_by_employee(self, employee_id: str) -> list[Patient]:
        return [p for p in self._patients if p.attending_employee_id == employee_id]


@dataclass
class InMemoryStore:
    users: _UserStoreMem = field(default_factory=_UserStoreMem)
    auth_codes: _AuthCodeStoreMem = field(default_factory=_AuthCodeStoreMem)
    refresh_tokens: _RefreshTokenStoreMem = field(default_factory=_RefreshTokenStoreMem)
    patients: _PatientStoreMem = field(default_factory=_PatientStoreMem)
