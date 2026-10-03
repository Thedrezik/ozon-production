"""Core defaults, real ingestion effects, provenance, permissions and replay."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.cli import create_admin
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import (
    Assignment,
    Blocker,
    BlockerType,
    ManagerTask,
    Order,
    TelegramAccount,
    utc_now,
)
from app.orders import seed_mock_orders
from app.ozon import MockOzonClient, OzonNetworkError
from app.ozon_reconciliation import reconcile
from app.ozon_tariff import normalize
from app.ozon_webhook import apply_posting
from app.rbac import seed_rbac
from app.telegram import deliver_pending
from tests.test_orders import login


def setup(tmp_path):
    config = Settings(database_url=f"sqlite:///{tmp_path / 'core.db'}", enabled_optional_features="",
                      ozon_webhook_enabled=False, ozon_reconciliation_enabled=False,
                      telegram_bot_token="fake-token", telegram_bot_username="fake_bot", telegram_webhook_secret="fake-secret")
    app = create_app(config)
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as db:
        seed_rbac(db)
        db.commit()
        create_admin("admin", "Admin", "admin-password-123", db)
        seed_mock_orders(db)
        db.add(BlockerType(code="OTHER", display_name="Другое"))
        db.add(TelegramAccount(user_id=1, chat_id="12345"))
        db.commit()
    return app


def posting():
    raw = deepcopy(MockOzonClient().get_fbs("0210000001-0001-1"))
    # Domain apply uses the documented v3 get string-price shape.
    raw["in_process_at"] = utc_now().isoformat()
    raw["shipment_date"] = (utc_now() + timedelta(hours=6)).isoformat()
    raw["tariffication"] = {
        "current_tariff_type": "discount", "current_tariff_charge": "120", "current_tariff_charge_currency_code": "RUB",
        "next_tariff_type": "commission", "next_tariff_charge": "50", "next_tariff_charge_currency_code": "RUB",
        "next_tariff_starts_at": (utc_now() + timedelta(hours=1)).isoformat()}
    raw["tariffication_steps"] = []
    return raw


def apply(app, raw):
    with Session(app.state.engine) as db:
        changed = apply_posting(db, raw, app.state.settings, from_get=True)
        db.commit()
        return changed


def test_core_workflow_and_telegram_side_effect(tmp_path):
    app = setup(tmp_path)
    raw = posting()
    assert apply(app, raw)
    statements = []
    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lower())
    event.listen(app.state.engine, "before_cursor_execute", record)
    with TestClient(app) as admin:
        h = login(admin)
        assert admin.post("/api/users", headers=h, json={"username": "worker", "display_name": "Worker", "password": "worker-password-123", "roles": ["PRODUCTION_WORKER"]}).status_code == 201
        order = admin.get(f"/api/orders?q={raw['posting_number']}").json()["items"][0]
        oid = order["id"]
        assert Decimal(order["tariff"]["delta_to_next_tariff"]) == Decimal(170)
        with TestClient(app) as worker:
            wh = login(worker, "worker", "worker-password-123")
            assert worker.get("/api/dashboard").status_code == 200
            assert worker.get("/api/audit").status_code == 403
            assert worker.get("/api/ozon/credentials").status_code in (403, 404)
            assert worker.post(f"/api/orders/{oid}/claim", headers=wh).json()["internal_status"] == "IN_PRODUCTION"
            assert worker.post(f"/api/orders/{oid}/claim", headers=wh).status_code == 409
            assert worker.post(f"/api/orders/{oid}/comments", headers=wh, json={"body": "Изготавливаю"}).status_code == 201
            problem = worker.post("/api/blockers", headers=wh, json={"order_id": oid, "description": "Нужна кромка"}).json()
            assert admin.get("/api/orders?problems=true").json()["items"][0]["problems"][0]["description"] == "Нужна кромка"
            assert admin.get("/api/blockers/summary").json()["active"] == 1
            sent = []
            deliver_pending(app.state.engine, app.state.settings, lambda *args: sent.append(args))
            deliver_pending(app.state.engine, app.state.settings, lambda *args: sent.append(args))
            assert len(sent) == 1 and "Нужна кромка" in sent[0][2]
            response = worker.patch(f"/api/blockers/{problem['id']}", headers=wh, json={"status": "RESOLVED", "resolution_comment": "Кромка получена"})
            assert response.status_code == 200
            assert response.json()["resolved_by_user_id"] == worker.get("/api/auth/me").json()["id"]
            for target in ("PRODUCED", "READY_TO_SHIP"):
                assert worker.post(f"/api/orders/{oid}/status", headers=wh, json={"status": target}).status_code == 200
            assert worker.post(f"/api/orders/{oid}/status", headers=wh, json={"status": "HANDED_TO_SHIPPING"}).status_code == 409
            raw["status"] = "delivering"
            assert apply(app, raw)
            assert not apply(app, raw)
            assert worker.get(f"/api/orders?order_id={oid}").json()["items"][0]["internal_status"] == "HANDED_TO_SHIPPING"
            timeline = worker.get(f"/api/orders/{oid}/timeline").json()["items"]
            assert any(item["body"] == "Заказ получен" for item in timeline)
            assert any("Кромка получена" in item["body"] and item["author"] == "Worker" for item in timeline)
        event.remove(app.state.engine, "before_cursor_execute", record)
        assert not any(any(table in statement for table in ("manager_tasks", "notification_preferences", "photos")) for statement in statements)
        with Session(app.state.engine) as db:
            assert db.scalar(select(func.count()).select_from(ManagerTask)) == 0
            assert db.get(Blocker, problem["id"]).resolution_comment == "Кромка получена"


@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("external_status", ["cancelled", "cancelled_from_split_pending"])
def test_cancellation_history_queue_critical_and_deduplication(tmp_path, started, external_status):
    app = setup(tmp_path)
    raw = posting()
    apply(app, raw)
    with TestClient(app) as client:
        h = login(client)
        oid = client.get(f"/api/orders?q={raw['posting_number']}").json()["items"][0]["id"]
        if started:
            assert client.post(f"/api/orders/{oid}/claim", headers=h).status_code == 200
        raw["status"] = external_status
        assert apply(app, raw)
        assert not apply(app, raw)
        row = next(row for row in client.get("/api/orders/feed?limit=100").json()["items"] if row["id"] == oid)
        assert row["cancelled"] and row["critical_cancellation"] == started
        assert bool(client.get(f"/api/orders?q={raw['posting_number']}").json()["items"]) == started
        assert bool(client.get("/api/dashboard").json()["cancelled_after_start"]) == started
        assert client.post(f"/api/orders/{oid}/status", headers=h, json={"status": "PRODUCED"}).status_code == 409
        sent = []
        for _ in range(2):
            deliver_pending(app.state.engine, app.state.settings, lambda *args: sent.append(args))
        assert len(sent) == int(started)
        if started:
            assert "TUMBA-WHITE" in sent[0][2] and "IN_PRODUCTION" in sent[0][2] and "Admin" in sent[0][2]
            assert client.post(f"/api/orders/{oid}/status", headers=h, json={"status": "CANCELLED"}).status_code == 200
            deliver_pending(app.state.engine, app.state.settings, lambda *args: sent.append(args))
            assert len(sent) == 1, "admin disposition must not repeat cancellation alert"
            assert client.get("/api/dashboard").json()["cancelled_after_start"] == []
            closed = client.get(f"/api/orders?order_id={oid}").json()["items"][0]
            assert closed["cancelled"] and not closed["critical_cancellation"]
            risk = client.get("/api/money-at-risk").json()
            for bucket in [*risk["buckets"], risk["already_degraded"]]:
                detail = client.get("/api/money-at-risk/orders", params={"bucket": bucket["key"], "limit": 100})
                assert detail.status_code == 200
                assert all(row["id"] != oid for row in detail.json()["items"])


def test_default_features_disabled_and_feed_is_chronological(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLED_OPTIONAL_FEATURES", "")
    app = setup(tmp_path)
    with TestClient(app) as client:
        h = login(client)
        for route in ("manager-tasks", "procurement", "analytics", "push/config", "files/photos", "notifications/preferences"):
            assert client.get(f"/api/{route}").status_code == 404
        assert client.post("/api/orders/bulk", headers=h, json={"order_ids": [1], "action": "status", "status": "PRODUCED"}).status_code == 404
        rows = client.get("/api/orders/feed?limit=100").json()["items"]
        assert [row["received_at"] for row in rows] == sorted(row["received_at"] for row in rows)
        assert any(row["cancelled"] for row in rows)
        assert client.get("/api/features").json()["optional"] == []
    config = Settings(_env_file=None)
    assert config.ozon_reconciliation_interval_seconds == 900


@pytest.mark.parametrize("stage", ["NEW", "IN_PRODUCTION", "PRODUCED", "PACKING", "READY_TO_SHIP"])
def test_problem_from_every_working_stage_restores_stage(tmp_path, stage):
    app = setup(tmp_path)
    with Session(app.state.engine) as db:
        db.get(Order, 1).internal_status = stage
        db.commit()
    with TestClient(app) as client:
        h = login(client)
        problems = [client.post("/api/blockers", headers=h, json={"order_id": 1, "description": text}).json() for text in ("Первая", "Вторая")]
        for problem in problems:
            assert client.patch(f"/api/blockers/{problem['id']}", headers=h, json={"status": "RESOLVED"}).status_code == 200
        assert client.get("/api/orders?order_id=1").json()["items"][0]["internal_status"] == stage


def test_real_tariff_ends_sign_unknown_and_minimum_not_added():
    now = utc_now()
    end = now + timedelta(hours=1)
    raw = {"tariffication_steps": [
        {"tariff_type": "discount", "tariff_charge": {"amount": "120", "currency": "RUB"}, "tariff_deadline_at": end.isoformat()},
        {"tariff_type": "commission", "tariff_charge": {"amount": "50", "currency": "RUB"}, "min_charge": {"amount": "999", "currency": "RUB"}, "tariff_deadline_at": (end + timedelta(hours=1)).isoformat()}]}
    steps = normalize(raw, now)
    assert steps[0]["cost"] == "-120" and steps[1]["cost"] == "50"
    assert steps[1]["starts_at"] == end.isoformat()
    assert steps[-1]["cost"] is None
    raw["tariffication_steps"][0]["tariff_type"] = "new_unknown_type"
    assert normalize(raw, now)[0]["cost"] is None


def test_reconciliation_error_core_telegram_deduplication_and_recovery(tmp_path):
    from unittest.mock import Mock

    app = setup(tmp_path)
    broken = Mock()
    broken.list_fbs.side_effect = OzonNetworkError()
    events = Mock()
    for _ in range(2):
        assert "error_code" in reconcile(app.state.engine, broken, app.state.settings, events)
    sent = []
    deliver_pending(app.state.engine, app.state.settings, lambda *args: sent.append(args))
    assert len(sent) == 1 and "Ошибка синхронизации Ozon" in sent[0][2]
    assert "error_code" not in reconcile(app.state.engine, MockOzonClient(), app.state.settings, events)
    assert "error_code" in reconcile(app.state.engine, broken, app.state.settings, events)
    deliver_pending(app.state.engine, app.state.settings, lambda *args: sent.append(args))
    assert len(sent) == 2
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(ManagerTask)) == 0


def test_identical_snapshot_backfills_tariff_without_losing_production(tmp_path):
    app = setup(tmp_path)
    raw = posting()
    apply(app, raw)
    with Session(app.state.engine) as db:
        order = db.scalar(select(Order).where(Order.posting_number == raw["posting_number"]))
        order.tariff_steps = None
        order.internal_status = "IN_PRODUCTION"
        db.commit()
    assert apply(app, raw)
    assert not apply(app, raw)
    with Session(app.state.engine) as db:
        order = db.scalar(select(Order).where(Order.posting_number == raw["posting_number"]))
        assert order.tariff_steps[0]["cost"] == "-120"
        assert order.internal_status == "IN_PRODUCTION"


def test_legacy_assigned_initial_order_starts_atomically(tmp_path):
    app = setup(tmp_path)
    with Session(app.state.engine) as db:
        db.get(Order, 1).internal_status = "QUEUED"
        db.add(Assignment(order_id=1, user_id=1, assigned_by=1))
        db.commit()
    with TestClient(app) as client:
        headers = login(client)
        response = client.post("/api/orders/1/claim", headers=headers)
        assert response.status_code == 200 and response.json()["internal_status"] == "IN_PRODUCTION"
        assert client.post("/api/orders/1/claim", headers=headers).status_code == 409
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Assignment).where(Assignment.order_id == 1)) == 1


def test_home_shows_active_critical_problem_and_removes_resolved(tmp_path):
    app = setup(tmp_path)
    with TestClient(app) as client:
        headers = login(client)
        problem = client.post("/api/blockers", headers=headers, json={"order_id": 1, "description": "Критическая поломка", "severity": "CRITICAL"}).json()
        row = client.get("/api/dashboard").json()["critical_problems"][0]
        assert row["id"] == problem["id"] and row["description"] == "Критическая поломка"
        assert client.patch(f"/api/blockers/{problem['id']}", headers=headers, json={"status": "RESOLVED"}).status_code == 200
        assert client.get("/api/dashboard").json()["critical_problems"] == []


def test_sse_checkpoint_changes_without_subscribers_and_after_restart():
    from app.order_events import OrderEvents

    bus = OrderEvents()
    initial = bus.checkpoint()
    bus.publish(42)
    assert bus.checkpoint() != initial
    assert bus.checkpoint().endswith(":1")
    assert OrderEvents().checkpoint().split(":")[0] != initial.split(":")[0]


@pytest.mark.parametrize("scalar", [False, True])
def test_tariff_current_next_documented_v4_money_and_v3_strings(scalar):
    raw = posting()
    if not scalar:
        for prefix in ("current_", "next_"):
            raw["tariffication"][prefix + "tariff_charge"] = {"amount": raw["tariffication"][prefix + "tariff_charge"], "currency": "RUB"}
    result = normalize(raw, utc_now())
    assert Decimal(result[1]["cost"]) - Decimal(result[0]["cost"]) == Decimal(170)


def test_v3_empty_current_charge_uses_confirmed_zero_step_and_explicit_next_start():
    now = utc_now()
    end = now + timedelta(hours=1)
    explicit = end + timedelta(seconds=1)
    raw = {"tariffication": {"current_tariff_type": "no_discount", "current_tariff_charge": "",
                            "current_tariff_charge_currency_code": "RUB", "next_tariff_type": "commission",
                            "next_tariff_charge": "50", "next_tariff_charge_currency_code": "RUB",
                            "next_tariff_starts_at": explicit.isoformat()},
           "tariffication_steps": [
               {"tariff_type": "no_discount", "tariff_charge": {"amount": "0", "currency": "RUB"}, "tariff_deadline_at": end.isoformat()},
               {"tariff_type": "commission", "tariff_charge": {"amount": "50", "currency": "RUB"}, "tariff_deadline_at": (end + timedelta(hours=1)).isoformat()}]}
    steps = normalize(raw, now)
    assert steps[0]["cost"] == "0" and steps[1]["cost"] == "50"
    assert steps[1]["starts_at"] == explicit.isoformat()
    assert steps[2]["cost"] is None
    raw.pop("tariffication_steps")
    assert normalize(raw, now)[0]["cost"] is None, "empty snapshot must not invent zero"
