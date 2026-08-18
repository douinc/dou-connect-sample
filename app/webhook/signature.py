import hashlib
import hmac


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
