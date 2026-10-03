"""Retained optional subsystems are still tested with explicit legacy flags."""
import pytest

from app.config import get_settings
from app.features import OPTIONAL_FEATURES


@pytest.fixture(autouse=True)
def legacy_capabilities(monkeypatch):
    monkeypatch.setenv("ENABLED_OPTIONAL_FEATURES", ",".join(sorted(OPTIONAL_FEATURES)))
    monkeypatch.setenv("OZON_WEBHOOK_ENABLED", "false")
    monkeypatch.setenv("OZON_RECONCILIATION_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
