import hashlib
import hmac


def verify_signature(*, secret: str, payload: bytes, header: str) -> bool:
    if not header.startswith("sha256="):
        return False
    received = header.removeprefix("sha256=")
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)
