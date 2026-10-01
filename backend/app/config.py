from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    vapid_public_key: str = ""
    vapid_private_key: str = Field(default="", repr=False)
    vapid_subject: str = ""
    telegram_bot_token: str = Field(default="", repr=False)
    telegram_bot_username: str = ""
    telegram_webhook_secret: str = Field(default="", repr=False)
    app_public_url: str = "http://localhost:5173"

    app_env: str = "development"
    app_secret: str = ""
    database_url: str = "postgresql+psycopg://ozon:ozon@localhost:5432/ozon"
    organization_timezone: str = "Europe/Moscow"
    money_risk_near_hours: int = Field(default=2, ge=1, le=24)
    money_risk_cutoff_hours: str = "12,16"
    ozon_mock_mode: bool = True
    ozon_webhook_enabled: bool = False
    # Exact trusted reverse-proxy peers; never trust arbitrary forwarded headers.
    ozon_webhook_trusted_proxies: str = ""
    upload_dir: str = "/data/uploads"
    backup_dir: str = "/data/backups"
    ozon_client_id: str = Field(default="", repr=False)
    ozon_api_key: str = Field(default="", repr=False)
    ozon_timeout_seconds: float = Field(default=10, gt=0, le=60, allow_inf_nan=False)
    ozon_max_retries: int = Field(default=2, ge=0, le=5)
    ozon_retry_backoff_seconds: float = Field(default=1, gt=0, le=30, allow_inf_nan=False)
    ozon_retry_max_delay_seconds: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
