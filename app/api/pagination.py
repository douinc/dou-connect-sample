"""담당 환자 목록 페이지네이션 + 불투명 `next` 커서.

가이드 규칙: page/pageSize가 둘 다 없으면 전체 목록, 있으면 1부터 시작하는 페이지.
pageSize 최대 100 권장(초과는 100으로 clamp). 다음 페이지는 응답의 `next`를
`{"cursor": ...}`로 되돌려 보내고, 사번은 커서 안에서만 전달된다.
"""
from __future__ import annotations

import base64
import binascii
import json
import math
from dataclasses import dataclass

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 100


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    page: int
    page_size: int
    total_count: int
    total_pages: int

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


def paginate[T](items: list[T], page: int | None, page_size: int | None) -> Page[T]:
    """1-based. 한쪽만 와도 기본값(page=1, pageSize=50)을 채운다."""
    p = max(page or 1, 1)
    size = min(max(page_size or PAGE_SIZE_DEFAULT, 1), PAGE_SIZE_MAX)
    total = len(items)
    pages = math.ceil(total / size) if total else 0
    start = (p - 1) * size
    return Page(items[start:start + size], p, size, total, pages)


@dataclass(frozen=True)
class Cursor:
    employee_id: str
    page: int
    page_size: int


# 자격증명이 아니다: 호출자는 이미 토큰과 사번을 갖고 있다. 목적은 2페이지부터 사번이
# URL·가시 파라미터로 다시 나가지 않게 하고, 클라이언트가 페이징을 재조립하지 않게 하는 것.
# 형식은 파트너 자유(불투명) — 샘플은 base64url(JSON).

def encode_cursor(cursor: Cursor) -> str:
    raw = json.dumps(
        {"e": cursor.employee_id, "p": cursor.page, "s": cursor.page_size},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> Cursor | None:
    """해석 불가면 None (호출자가 422)."""
    try:
        pad = "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(value + pad).decode())
        e, p, s = data["e"], data["p"], data["s"]
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeDecodeError):
        return None
    if not isinstance(e, str) or not e or not isinstance(p, int) or not isinstance(s, int):
        return None
    if p < 1 or s < 1:
        return None
    return Cursor(employee_id=e, page=p, page_size=s)
