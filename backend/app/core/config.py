from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "production"] = "development"
    expose_api_docs: bool = True
    database_url: str = Field(f"sqlite:///{ROOT / 'vantage.db'}", repr=False)
    database_url_file: str = ""
    redis_url_file: str = ""
    kite_api_key_file: str = ""
    kite_api_secret_file: str = ""
    alpha_vantage_api_key_file: str = ""
    fred_api_key_file: str = ""
    openai_api_key_file: str = ""
    frontend_url: str = "http://localhost:3000"
    cookie_secure: bool = False
    master_keys: str = Field("", repr=False)
    master_key_file: str = ""
    master_key_active: str = "v1"
    kite_token_lifetime_hours: int = Field(8, ge=1, le=24)
    private_storage_dir: str = str(ROOT / "artifacts/private")
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    source_quota_mb: int = Field(250, ge=10, le=10000)
    storage_quota_mb: int = Field(250, ge=10, le=10000)
    document_sandbox_required: bool = False
    job_backend: str = "local"
    redis_url: str = Field("redis://127.0.0.1:56379/0", repr=False)
    provider_daily_reserved_tokens: int = Field(10_000_000, ge=1_000_000, le=100_000_000)
    job_lease_seconds: int = Field(45, ge=10, le=300)
    job_per_user_limit: int = Field(4, ge=1, le=20)
    job_queue_limit: int = Field(100, ge=4, le=1000)
    auth_required: bool = False
    registration_enabled: bool = True
    auth_session_hours: int = Field(12, ge=1, le=168)
    auth_idle_minutes: int = Field(60, ge=5, le=1440)
    kite_api_key: str = Field("", repr=False)
    kite_api_secret: str = Field("", repr=False)
    alpha_vantage_api_key: str = Field("", repr=False)
    fred_api_key: str = Field("", repr=False)
    model_artifact_dir: str = str(ROOT / "artifacts/models")
    build_commit: str = ""
    openai_api_key: str = Field("", repr=False)
    llm_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: float = Field(12, ge=1, le=30)
    llm_input_usd_per_million: float | None = Field(None, ge=0)
    llm_output_usd_per_million: float | None = Field(None, ge=0)
    embedding_model: str = "text-embedding-3-small"
    document_storage_dir: str = str(ROOT / "artifacts/documents")
    document_chunk_chars: int = Field(1800, ge=400, le=3000)
    document_chunk_overlap: int = Field(180, ge=0, le=499)

    @model_validator(mode="before")
    @classmethod
    def mounted_secrets(cls, values):
        values = dict(values)
        for name in (
            "database_url",
            "redis_url",
            "kite_api_key",
            "kite_api_secret",
            "alpha_vantage_api_key",
            "fred_api_key",
            "openai_api_key",
        ):
            filename = values.get(name + "_file")
            if not filename:
                continue
            if values.get(name):
                raise ValueError("Choose a mounted secret file or an environment value, not both.")
            try:
                path = Path(filename)
                if not path.is_file() or path.stat().st_size > 8192:
                    raise ValueError()
                values[name] = path.read_text().strip()
                if not values[name]:
                    raise ValueError()
            except (OSError, ValueError):
                raise ValueError(
                    "A required mounted secret file is missing, unreadable or invalid."
                ) from None
        return values

    @model_validator(mode="after")
    def production_boundary(self):
        if self.environment != "production":
            return self
        origin = urlsplit(self.frontend_url)
        database = make_url(self.database_url)
        if (
            not self.auth_required
            or self.registration_enabled
            or not self.cookie_secure
            or self.expose_api_docs
            or not self.document_sandbox_required
            or self.job_backend != "celery"
        ):
            raise ValueError(
                "Production requires authentication, secure cookies, closed registration/docs, required Linux parser isolation and durable workers."
            )
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.query
            or origin.fragment
            or origin.path not in {"", "/"}
        ):
            raise ValueError(
                "Production requires an explicit HTTPS origin without credentials, path, query or fragment."
            )
        if (
            database.get_backend_name() != "postgresql"
            or not database.password
            or len(database.password) < 24
            or not self.database_url_file
            or not self.redis_url_file
        ):
            raise ValueError(
                "Production requires PostgreSQL and separately mounted database/broker credentials."
            )
        broker = urlsplit(self.redis_url)
        if (
            broker.scheme not in {"redis", "rediss"}
            or not broker.password
            or len(broker.password) < 24
        ):
            raise ValueError("Production requires an authenticated private Redis broker.")
        if self.master_keys or not self.master_key_file:
            raise ValueError(
                "Production requires a separately mounted external versioned encryption keyring."
            )
        try:
            import json

            from cryptography.fernet import Fernet

            path = Path(self.master_key_file)
            if path.stat().st_size > 8192:
                raise ValueError()
            keys = json.loads(path.read_text())
            if (
                not isinstance(keys, dict)
                or self.master_key_active not in keys
                or not 1 <= len(keys) <= 8
            ):
                raise ValueError()
            for value in keys.values():
                Fernet(value.encode())
        except (OSError, ValueError, TypeError, AttributeError):
            raise ValueError("Production encryption keyring is unavailable or invalid.") from None
        return self

    @field_validator("model_artifact_dir", "document_storage_dir", "private_storage_dir")
    @classmethod
    def resolve_artifact_dir(cls, value: str) -> str:
        path = Path(value).expanduser()
        return str(path if path.is_absolute() else ROOT / path)

    @field_validator("database_url")
    @classmethod
    def resolve_local_database(cls, value: str) -> str:
        # Backend, Alembic and browser-test processes can have different cwd values.
        if value.startswith("sqlite"):
            url = make_url(value)
            path = url.database
            if (
                path
                and path != ":memory:"
                and not path.startswith("file:")
                and not Path(path).is_absolute()
            ):
                return url.set(database=str(ROOT / path)).render_as_string(hide_password=False)
        return value


@lru_cache
def settings() -> Settings:
    return Settings()
