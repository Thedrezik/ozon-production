from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.config import get_settings


def test_inbox_upgrade_downgrade_upgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    engine = create_engine(url)
    try:
        command.upgrade(config, "head")
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("ozon_webhook_events")}
        assert columns >= {"event_key", "payload_json", "status", "attempts", "next_attempt_at", "error_code"}
        assert {tuple(c["column_names"]) for c in inspector.get_unique_constraints("ozon_webhook_events")} == {("event_key",)}
        assert {c["name"] for c in inspector.get_columns("orders")} >= {"ozon_delivery_date_begin", "ozon_delivery_date_end"}
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0018_ozon_reconciliation"
        columns = {c["name"] for c in inspector.get_columns("ozon_sync_state")}
        assert columns >= {"last_attempt_at", "last_successful_sync", "status", "error_code", "error_episode"}
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM ozon_sync_state")) == 2
        command.downgrade(config, "0017_ozon_webhook")
        assert "ozon_sync_state" not in inspect(engine).get_table_names()
        command.upgrade(config, "head")
        command.downgrade(config, "0016_ozon_fbs_import")
        assert "ozon_webhook_events" not in inspect(engine).get_table_names()
        command.upgrade(config, "head")
        assert "ozon_webhook_events" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
        get_settings.cache_clear()
