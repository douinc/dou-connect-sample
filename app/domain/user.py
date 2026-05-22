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
