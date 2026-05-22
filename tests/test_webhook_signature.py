import hashlib
import hmac

from app.webhook.signature import verify_signature


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature():
    body = b'{"event":"records.summarized"}'
    sig = _sign("topsecret", body)
    assert verify_signature(secret="topsecret", payload=body, header=sig) is True


def test_wrong_secret_fails():
    body = b'{"event":"records.summarized"}'
    sig = _sign("wrong", body)
    assert verify_signature(secret="topsecret", payload=body, header=sig) is False


def test_missing_prefix_fails():
    body = b"{}"
    digest = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    assert verify_signature(secret="topsecret", payload=body, header=digest) is False


def test_tampered_body_fails():
    sig = _sign("topsecret", b'{"event":"records.summarized"}')
    assert verify_signature(
        secret="topsecret", payload=b'{"event":"changed"}', header=sig,
    ) is False
