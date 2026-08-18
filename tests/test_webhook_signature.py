import hashlib
import hmac

from app.webhook.signature import verify_signature


# 새록 실발송과 동일: HMAC-SHA256("{timestamp}." + body)
def _sign(secret: str, timestamp: str, body: bytes) -> str:
    signed_input = f"{timestamp}.".encode() + body
    return "sha256=" + hmac.new(secret.encode(), signed_input, hashlib.sha256).hexdigest()


def test_valid_signature():
    body = b'{"event":"records.summarized"}'
    ts = "1767225600"
    sig = _sign("topsecret", ts, body)
    assert verify_signature(secret="topsecret", timestamp=ts, payload=body, header=sig) is True


def test_wrong_secret_fails():
    body = b'{"event":"records.summarized"}'
    ts = "1767225600"
    sig = _sign("wrong", ts, body)
    assert verify_signature(secret="topsecret", timestamp=ts, payload=body, header=sig) is False


def test_missing_prefix_fails():
    body = b"{}"
    ts = "1767225600"
    signed_input = f"{ts}.".encode() + body
    digest = hmac.new(b"topsecret", signed_input, hashlib.sha256).hexdigest()
    assert verify_signature(secret="topsecret", timestamp=ts, payload=body, header=digest) is False


def test_tampered_body_fails():
    ts = "1767225600"
    sig = _sign("topsecret", ts, b'{"event":"records.summarized"}')
    assert verify_signature(
        secret="topsecret", timestamp=ts, payload=b'{"event":"changed"}', header=sig,
    ) is False


def test_tampered_timestamp_fails():
    body = b'{"event":"records.summarized"}'
    sig = _sign("topsecret", "1767225600", body)
    assert verify_signature(
        secret="topsecret", timestamp="1767225601", payload=body, header=sig,
    ) is False


def test_body_only_signature_fails():
    # body 단독 해싱(구 파트너 문서 방식)은 실발송 서명과 일치하지 않아야 한다
    body = b'{"event":"records.summarized"}'
    ts = "1767225600"
    body_only = "sha256=" + hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    assert verify_signature(secret="topsecret", timestamp=ts, payload=body, header=body_only) is False


def test_non_ascii_header_fails_closed():
    # str 비교였다면 TypeError(500) — 예외 없이 False여야 한다
    body = b"{}"
    ts = "1767225600"
    assert verify_signature(
        secret="topsecret", timestamp=ts, payload=body, header="sha256=café",
    ) is False


def test_non_latin1_header_fails_closed():
    body = b"{}"
    ts = "1767225600"
    assert verify_signature(
        secret="topsecret", timestamp=ts, payload=body, header="sha256=ㄱ",
    ) is False
