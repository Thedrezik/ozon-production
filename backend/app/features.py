"""Explicit optional capabilities; core never depends on these switches."""

OPTIONAL_FEATURES = frozenset({
    "manager_tasks", "procurement", "analytics", "photos", "scanner",
    "bulk_actions", "notification_preferences", "web_push", "key_expiration",
    "advanced_workflow",
})


def enabled(settings, name: str) -> bool:
    return name in settings.enabled_optional_features.split(",")


def db_enabled(db, name: str) -> bool:
    settings = db.info.get("settings")
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    return enabled(settings, name)
