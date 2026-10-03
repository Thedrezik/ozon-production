from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    vapid_public_key: str = ""
    vapid_private_key: str = Field(default="", repr=False)
    vapid_subject: str = ""
    telegram_bot_token: str = Field(default="", repr=False)
    telegram_bot_username: str = ""
    telegram_webhook_secret: str = Field(default="", repr=False)
    app_public_url: str = "http://localhost:5173"
    domain: str = ":80"

    app_env: Literal["development", "test", "production"] = "development"
    app_secret: str = Field(default="", repr=False)
    database_url: str = Field(default="postgresql+psycopg://ozon:ozon@localhost:5432/ozon", repr=False)
    organization_timezone: str = "Europe/Moscow"
    enabled_optional_features: str = ""
    money_risk_near_hours: int = Field(default=2, ge=1, le=24)
    money_risk_cutoff_hours: str = "12,16"
    ozon_mock_mode: bool = True
    ozon_webhook_enabled: bool = True
    ozon_reconciliation_enabled: bool = True
    ozon_reconciliation_interval_seconds: int = Field(default=900, ge=60, le=3600)
    ozon_reconciliation_lookback_days: int = Field(default=30, ge=1, le=364)
    ozon_stale_after_seconds: int = Field(default=1800, ge=60, le=86400)
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

    @model_validator(mode="after")
    def production_security(self):
        if self.app_env != "production":
            return self
        url = urlsplit(self.app_public_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ("", "/")
                or url.hostname in ("localhost", "example.com", "127.0.0.1", "::1")):
            raise ValueError("Production requires a real HTTPS APP_PUBLIC_URL origin")
        if self.ozon_mock_mode:
            raise ValueError("Mock Mode is forbidden in production")
        if self.domain != url.netloc:
            raise ValueError("Production DOMAIN must match the HTTPS APP_PUBLIC_URL host and port")
        database = make_url(self.database_url)
        if (database.get_backend_name() != "postgresql" or not database.password
                or len(database.password) < 16
                or database.password.lower() in ("replace-with-a-strong-password", "password")):
            raise ValueError("Production requires PostgreSQL with a non-default password of at least 16 characters")
        if len(self.app_secret) < 32 or self.app_secret.startswith("replace-"):
            raise ValueError("Production requires a random APP_SECRET of at least 32 characters")
        try:
            Fernet(self.ozon_credentials_master_key.encode())
        except (ValueError, TypeError):
            raise ValueError("Production requires a valid OZON_CREDENTIALS_MASTER_KEY") from None
        if (any((self.telegram_bot_token, self.telegram_bot_username, self.telegram_webhook_secret))
                and (not all((self.telegram_bot_token, self.telegram_bot_username, self.telegram_webhook_secret))
                     or len(self.telegram_webhook_secret) < 32)):
            raise ValueError("Production Telegram requires complete configuration and a random webhook secret")
        if (any((self.vapid_public_key, self.vapid_private_key, self.vapid_subject))
                and not all((self.vapid_public_key, self.vapid_private_key, self.vapid_subject))):
            raise ValueError("Production Web Push requires complete VAPID configuration")
        if self.ozon_webhook_trusted_proxies:
            import ipaddress

            for peer in self.ozon_webhook_trusted_proxies.split(","):
                network = ipaddress.ip_network(peer.strip())
                if network.prefixlen != network.max_prefixlen:
                    raise ValueError("Production webhook trust requires exact proxy IPs (/32 or /128)")
        return self

    @field_validator("ozon_key_alert_days")
    @classmethod
    def valid_alert_days(cls, value: str) -> str:
        days = [int(part.strip()) for part in value.split(",")]
        if not days or any(day < 1 or day > 365 for day in days):
            raise ValueError("Ozon alert days must be between 1 and 365")
        return ",".join(str(day) for day in sorted(set(days), reverse=True))

    @field_validator("enabled_optional_features")
    @classmethod
    def valid_features(cls, value: str) -> str:
        from app.features import OPTIONAL_FEATURES

        names = {part.strip() for part in value.split(",") if part.strip()}
        if names - OPTIONAL_FEATURES:
            raise ValueError("Unknown optional feature")
        return ",".join(sorted(names))


@lru_cache
def get_settings() -> Settings:
    return Settings()
