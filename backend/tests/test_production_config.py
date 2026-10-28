import json

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import Settings


def production(tmp_path, monkeypatch):
    for key in (
        "DATABASE_URL",
        "REDIS_URL",
        "MASTER_KEYS",
        "DATABASE_URL_FILE",
        "REDIS_URL_FILE",
        "MASTER_KEY_FILE",
    ):
        monkeypatch.delenv(key, raising=False)
    database = tmp_path / "database-url"
    broker = tmp_path / "redis-url"
    keys = tmp_path / "keys"
    database.write_text(
        "postgresql+psycopg://application:SYNTHETIC-private-database-password-917@db/vantage"
    )
    broker.write_text("redis://:SYNTHETIC-private-broker-password-371@redis/0")
    keys.write_text(json.dumps({"v1": Fernet.generate_key().decode()}))
    return {
        "_env_file": None,
        "environment": "production",
        "auth_required": True,
        "registration_enabled": False,
        "cookie_secure": True,
        "expose_api_docs": False,
        "document_sandbox_required": True,
        "job_backend": "celery",
        "frontend_url": "https://localhost:8443",
        "database_url_file": str(database),
        "redis_url_file": str(broker),
        "master_key_file": str(keys),
    }


def test_production_loads_mounted_secrets_without_repr_exposure(tmp_path, monkeypatch):
    config = Settings(**production(tmp_path, monkeypatch))
    assert "SYNTHETIC-private-database-password" in config.database_url
    assert "SYNTHETIC-private" not in repr(config)
    assert config.auth_required and config.cookie_secure and not config.registration_enabled


@pytest.mark.parametrize(
    "change",
    [
        {"auth_required": False},
        {"registration_enabled": True},
        {"cookie_secure": False},
        {"expose_api_docs": True},
        {"document_sandbox_required": False},
        {"job_backend": "local"},
        {"frontend_url": "http://localhost"},
        {"frontend_url": "https://localhost/path?token=SYNTHETIC-private-value"},
        {"database_url_file": ""},
        {"redis_url_file": ""},
        {"master_key_file": ""},
        {"master_keys": "SYNTHETIC-private-value"},
    ],
)
def test_insecure_production_settings_fail_closed_without_secret_errors(
    tmp_path, monkeypatch, change
):
    values = {**production(tmp_path, monkeypatch), **change}
    with pytest.raises(ValidationError) as error:
        Settings(**values)
    assert "SYNTHETIC-private" not in str(error.value)


def test_missing_and_conflicting_secret_files_are_explicit(tmp_path, monkeypatch):
    values = production(tmp_path, monkeypatch)
    with pytest.raises(ValidationError, match="mounted secret"):
        Settings(**{**values, "database_url_file": str(tmp_path / "missing")})
    with pytest.raises(ValidationError, match="not both"):
        Settings(**{**values, "database_url": "sqlite:///SYNTHETIC-private.db"})
