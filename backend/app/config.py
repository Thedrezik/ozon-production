from functools import lru_cache

from pydantic import Field, field_validator
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
    ozon_reconciliation_enabled: bool = False
    ozon_reconciliation_interval_seconds: int = Field(default=240, ge=60, le=3600)
    ozon_reconciliation_lookback_days: int = Field(default=30, ge=1, le=364)
    ozon_stale_after_seconds: int = Field(default=600, ge=60, le=86400)
    # Exact trusted reverse-proxy peers; never trust arbitrary forwarded headers.
    ozon_webhook_trusted_proxies: str = ""
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    upload_dir: str = "/data/uploads"
    backup_dir: str = "/data/backups"
    ozon_credentials_master_key: str = Field(default="", repr=False)
    ozon_key_alert_days: str = "14,7,3,1"
    ozon_client_id: str = Field(default="", repr=False)
    ozon_api_key: str = Field(default="", repr=False)
    ozon_timeout_seconds: float = Field(default=10, gt=0, le=60, allow_inf_nan=False)
    ozon_max_retries: int = Field(default=2, ge=0, le=5)
    ozon_retry_backoff_seconds: float = Field(default=1, gt=0, le=30, allow_inf_nan=False)
    ozon_retry_max_delay_seconds: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)

    @field_validator("ozon_key_alert_days")
    @classmethod
    def valid_alert_days(cls, value: str) -> str:
        days = [int(part.strip()) for part in value.split(",")]
        if not days or any(day < 1 or day > 365 for day in days):
            raise ValueError("Ozon alert days must be between 1 and 365")
        return ",".join(str(day) for day in sorted(set(days), reverse=True))


@lru_cache
def get_settings() -> Settings:
    return Settings()
