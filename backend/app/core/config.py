from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

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


@lru_cache
def settings() -> Settings:
    return Settings()
