import hashlib
import hmac
from collections.abc import Sequence


def verify_signature_any(
    *, secrets: Sequence[str], timestamp: str, payload: bytes, header: str
) -> bool:
    """복수 secret 후보 중 하나라도 서명이 일치하면 통과.

    secret은 웹훅 등록 건마다 별도 발급되므로(이벤트별 등록 = secret 여러 개)
    수신부는 보유한 모든 secret에 대해 검증해야 한다. 후보별 비교는
    verify_signature의 상수시간 비교를 그대로 사용한다 — 후보 개수는 비밀이
    아니므로 첫 일치에서 멈춰도 안전하다.
    """
    return any(
        verify_signature(secret=secret, timestamp=timestamp, payload=payload, header=header)
        for secret in secrets
    )


def verify_signature(*, secret: str, timestamp: str, payload: bytes, header: str) -> bool:
    """새록 웹훅 서명 검증.

    서명 입력은 body 단독이 아니라 "{timestamp}." + body raw bytes다.
    timestamp는 X-Saylog-Timestamp 헤더 값(unix epoch 초 문자열)을 그대로 사용한다.
    """
    if not header.startswith("sha256="):
        return False
    received = header.removeprefix("sha256=")
    try:
        # str 쌍의 compare_digest는 비ASCII 값에 TypeError를 던져 500을 유발한다 —
        # 바이트로 비교. HTTP 헤더 값은 latin-1 범위이므로 인코딩 실패는 위조 입력
        # 취급(fail-closed).
        received_bytes = received.encode("latin-1")
    except UnicodeEncodeError:
        return False
    signed_input = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed_input, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode("ascii"), received_bytes)
