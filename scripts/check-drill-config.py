"""Validate resolved Compose JSON before any destructive drill action."""
import json
import re
import sys


def validate(config, prefix):
    if not re.fullmatch(r"ozon-backup-drill-[a-z0-9-]+", prefix) or config.get("name") != prefix:
        raise ValueError("drill project mismatch")
    keys = {"postgres_data", "uploads", "backups", "caddy_data", "caddy_config"}
    if set(config.get("volumes", {})) != keys:
        raise ValueError("unexpected volume definitions")
    for key, volume in config["volumes"].items():
        if volume.get("name") != f"{prefix}_{key}" or volume.get("external") or volume.get("driver_opts"):
            raise ValueError("unsafe volume definition")
    backend = config["services"]["backend"]
    settings = backend["environment"]
    if settings.get("APP_ENV") != "test" or str(settings.get("OZON_MOCK_MODE")).lower() != "true":
        raise ValueError("drill must use synthetic test configuration")
    for flag in ("OZON_RECONCILIATION_ENABLED", "OZON_WEBHOOK_ENABLED"):
        if str(settings.get(flag)).lower() != "false":
            raise ValueError("background Ozon traffic forbidden")
    for secret in ("OZON_CLIENT_ID", "OZON_API_KEY", "TELEGRAM_BOT_TOKEN", "VAPID_PRIVATE_KEY"):
        if settings.get(secret):
            raise ValueError("external credentials forbidden")
    for name, service in config["services"].items():
        for mount in service.get("volumes", []):
            if mount.get("type") != "volume" or mount.get("source") not in keys:
                raise ValueError("bind/external mounts forbidden")
        # Caddy never starts in the drill; backend/PostgreSQL publish no ports.
        if name != "caddy" and service.get("ports"):
            raise ValueError("drill data services must not expose ports")
    return [f"{prefix}_{key}" for key in sorted(keys)]


if __name__ == "__main__":
    try:
        for name in validate(json.load(sys.stdin), sys.argv[1]):
            print(name)
    except (ValueError, KeyError, TypeError, IndexError):
        sys.exit("Unsafe drill configuration; restore/cleanup forbidden (no config values disclosed).")
