from app.config import Settings


def test_settings_loads_from_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "PUBLIC_BASE_URL=http://example.com\n"
        "SAYLOG_CLIENT_ID=test-client\n"
        "SAYLOG_CLIENT_SECRET=test-secret\n"
        "SAYLOG_REDIRECT_URI=http://callback.example/cb\n"
    )
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.public_base_url == "http://example.com"
    assert settings.saylog_client_id == "test-client"
    assert settings.saylog_client_secret.get_secret_value() == "test-secret"


def test_settings_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAYLOG_CLIENT_ID", "x")
    monkeypatch.setenv("SAYLOG_CLIENT_SECRET", "y")
    monkeypatch.setenv("SAYLOG_REDIRECT_URI", "http://z")
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.jwt_access_token_ttl == 3600
    assert settings.jwt_refresh_token_ttl == 2592000


def test_secret_str_not_in_repr(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAYLOG_CLIENT_ID", "x")
    monkeypatch.setenv("SAYLOG_CLIENT_SECRET", "super-secret-value")
    monkeypatch.setenv("SAYLOG_REDIRECT_URI", "http://z")
    settings = Settings()
    assert "super-secret-value" not in repr(settings)


def _minimal_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAYLOG_CLIENT_ID", "x")
    monkeypatch.setenv("SAYLOG_CLIENT_SECRET", "y")
    monkeypatch.setenv("SAYLOG_REDIRECT_URI", "http://z")


def test_dou_connect_scope_comma_normalized_to_space(monkeypatch, tmp_path):
    """RFC 6749 §3.3: OAuth scope는 space-delimited. env var는 콤마 컨벤션을
    따르므로 입력 시 콤마를 공백으로 정규화한다."""
    _minimal_env(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "DOU_CONNECT_SCOPE", "idp:write,idp:read,webhooks:read",
    )
    settings = Settings()
    assert settings.dou_connect_scope == "idp:write idp:read webhooks:read"


def test_dou_connect_scope_with_whitespace_around_commas(monkeypatch, tmp_path):
    _minimal_env(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "DOU_CONNECT_SCOPE", "idp:write, idp:read ,webhooks:read",
    )
    settings = Settings()
    assert settings.dou_connect_scope == "idp:write idp:read webhooks:read"


def test_dou_connect_scope_empty_stays_empty(monkeypatch, tmp_path):
    _minimal_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DOU_CONNECT_SCOPE", "")
    settings = Settings()
    assert settings.dou_connect_scope == ""


def test_dou_connect_scope_already_space_delimited_preserved(
    monkeypatch, tmp_path,
):
    """RFC 표준 형식(스페이스)으로 직접 적은 값도 그대로 받아준다."""
    _minimal_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DOU_CONNECT_SCOPE", "idp:write idp:read")
    settings = Settings()
    assert settings.dou_connect_scope == "idp:write idp:read"


def test_dou_connect_scope_single_value(monkeypatch, tmp_path):
    _minimal_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DOU_CONNECT_SCOPE", "records:read")
    settings = Settings()
    assert settings.dou_connect_scope == "records:read"


def test_webhook_secret_candidates_parses_comma_list(monkeypatch, tmp_path):
    _minimal_env(monkeypatch, tmp_path)
    monkeypatch.setenv("WEBHOOK_SECRETS", "sec-a, sec-b ,sec-c")
    settings = Settings()
    assert settings.webhook_secret_candidates() == ["sec-a", "sec-b", "sec-c"]


def test_webhook_secret_candidates_merges_legacy_single(monkeypatch, tmp_path):
    """단수 WEBHOOK_SECRET은 복수 목록 뒤에 합쳐진다 (하위호환)."""
    _minimal_env(monkeypatch, tmp_path)
    monkeypatch.setenv("WEBHOOK_SECRETS", "sec-a,sec-b")
    monkeypatch.setenv("WEBHOOK_SECRET", "legacy-sec")
    settings = Settings()
    assert settings.webhook_secret_candidates() == ["sec-a", "sec-b", "legacy-sec"]


def test_webhook_secret_candidates_dedupes(monkeypatch, tmp_path):
    _minimal_env(monkeypatch, tmp_path)
    monkeypatch.setenv("WEBHOOK_SECRETS", "sec-a,sec-a,sec-b")
    monkeypatch.setenv("WEBHOOK_SECRET", "sec-b")
    settings = Settings()
    assert settings.webhook_secret_candidates() == ["sec-a", "sec-b"]


def test_webhook_secret_candidates_empty_when_unset(monkeypatch, tmp_path):
    _minimal_env(monkeypatch, tmp_path)
    monkeypatch.delenv("WEBHOOK_SECRETS", raising=False)
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    settings = Settings()
    assert settings.webhook_secret_candidates() == []
