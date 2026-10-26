from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
