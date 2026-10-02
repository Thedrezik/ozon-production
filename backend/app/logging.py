import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

_secrets: tuple[str, ...] = ()
_sensitive = re.compile(
    r"(?i)((?:password(?:_hash)?|secret|token|api[_-]?key|authorization|cookie)[\"']?\s*[=:]\s*[\"']?)[^\s,;\"']+"
)


def redact_text(value: str) -> str:
    for secret in _secrets:
        value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"https://api\.telegram\.org/bot[^/\s]+", "https://api.telegram.org/bot[REDACTED]", value)
    value = re.sub(r"(?i)(authorization\s*[=:]\s*)(?:Bearer|Basic)\s+[^\s,;]+", r"\1[REDACTED]", value)
    return _sensitive.sub(r"\1[REDACTED]", value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": redact_text(record.getMessage()),
                **{key: getattr(record, key) for key in (
                    "ozon_endpoint", "ozon_attempt", "ozon_status", "ozon_error",
                    "ozon_duration_ms",
                ) if hasattr(record, key)},
            },
            ensure_ascii=False,
        )


def configure_logging(settings=None) -> None:
    global _secrets
    if settings:
        password = urlsplit(settings.database_url).password
        _secrets = tuple(value for value in (
            settings.app_secret, settings.ozon_api_key, settings.ozon_credentials_master_key,
            settings.telegram_bot_token, settings.telegram_webhook_secret,
            settings.vapid_private_key, password,
        ) if value)
    # Transport libraries log complete URLs (Telegram token / push capability).
    for name in ("httpx", "httpcore", "urllib3", "pywebpush", "py_vapid", "uvicorn.access"):
        logging.getLogger(name).disabled = True
        logging.getLogger(name).setLevel(logging.CRITICAL)
    # Uvicorn has its own default handlers and re-logs uncaught ASGI exceptions.
    # Route those through the safe formatter too; it intentionally omits exc_info.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
