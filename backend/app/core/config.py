from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str = f"sqlite:///{ROOT / 'vantage.db'}"
    frontend_url: str = "http://localhost:3000"
    cookie_secure: bool = False
    kite_api_key: str = ""
    kite_api_secret: str = ""
    alpha_vantage_api_key: str = ""
    fred_api_key: str = ""
    model_artifact_dir: str = str(ROOT / "artifacts/models")
    build_commit: str = ""
    openai_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: float = Field(12, ge=1, le=30)
    llm_input_usd_per_million: float | None = Field(None, ge=0)
    llm_output_usd_per_million: float | None = Field(None, ge=0)
    embedding_model: str = "text-embedding-3-small"
    document_storage_dir: str = str(ROOT / "artifacts/documents")
    document_chunk_chars: int = Field(1800, ge=400, le=3000)
    document_chunk_overlap: int = Field(180, ge=0, le=499)

    @field_validator("model_artifact_dir", "document_storage_dir")
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
