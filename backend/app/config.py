from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret: str = ""
    database_url: str = "postgresql+psycopg://ozon:ozon@localhost:5432/ozon"
    organization_timezone: str = "Europe/Moscow"
    money_risk_near_hours: int = Field(default=2, ge=1, le=24)
    money_risk_cutoff_hours: str = "12,16"
    ozon_mock_mode: bool = True
    upload_dir: str = "/data/uploads"
    backup_dir: str = "/data/backups"
    ozon_client_id: str = Field(default="", repr=False)
    ozon_api_key: str = Field(default="", repr=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
