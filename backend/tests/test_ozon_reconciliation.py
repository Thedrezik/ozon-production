import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    Blocker,
    BlockerType,
    Comment,
    InternalStatus,
    ManagerTask,
    Notification,
    Order,
    OzonPostingData,
    OzonSyncState,
    StatusHistory,
    User,
)
from app.orders import STATUS_LABELS, STATUSES, seed_mock_orders
from app.ozon import FBS_GET_PATH, FBS_LIST_PATH, MockOzonClient
from app.ozon_import import upsert_posting
from app.ozon_reconciliation import reconcile, reconciliation_loop, sync_status
from tests.test_orders import login, setup_app
from tests.test_ozon import client_for
from tests.test_ozon_import import response

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
def page():
    return json.loads((Path(__file__).parents[1] / "app/fixtures/fbs_v4.json").read_text(encoding="utf-8"),
                      parse_float=Decimal)


@pytest.fixture
def app(tmp_path):
    app = setup_app(tmp_path)
    app.state.settings.ozon_mock_mode = False
    with Session(app.state.engine) as db:
        for index, status in enumerate(STATUSES):
            db.add(InternalStatus(name=status, display_name=STATUS_LABELS[index], sort_order=index))
        db.commit()
    return app


def run(app, replies):
    client, requests, _ = client_for(replies)
    events = Mock()
    with client:
        result = reconcile(app.state.engine, client, app.state.settings, events)
    events.publish.assert_called_once_with(0)
    return result, requests


def get_response(raw):
    raw = copy.deepcopy(raw)
    for item in raw["products"]:
        price = item["price"]
        item["price"], item["currency_code"] = price["amount"], price["currency"]
    from app.ozon_import import diagnostic_json
    return httpx.Response(200, text=diagnostic_json({"result": raw}))


def test_missed_new_posting_and_repeat_with_shared_notifications(app, page):
    assert run(app, [response(page)])[0] == {"received": 1, "changed": 1, "pages": 1, "checked_missing": 0}
    assert run(app, [response(page)])[0]["changed"] == 0
    with Session(app.state.engine) as db:
        assert db.query(Order).count() == db.query(StatusHistory).count() == 1
        assert db.query(Notification).filter_by(type="NEW_ORDER").count() == 1
        assert db.query(ManagerTask).count() == 0
        state = db.get(OzonSyncState, 1)
        assert state.status == "SUCCESS" and state.error_code is None
        assert state.last_successful_sync >= state.last_attempt_at


def test_cursor_pages_and_new_posting_on_second_page(app, page):
    first = copy.deepcopy(page)
    first.update(has_next=True, cursor="next-page")
    page["postings"][0]["posting_number"] = "missed-second"
    result, requests = run(app, [response(first), response(page)])
    assert result == {"received": 2, "changed": 2, "pages": 2, "checked_missing": 0}
    assert [r.url.path for r in requests] == [FBS_LIST_PATH, FBS_LIST_PATH]
    assert json.loads(requests[1].content)["cursor"] == "next-page"
    with Session(app.state.engine) as db:
        assert db.query(Order).count() == 2


def test_updates_dates_substatus_tariff_and_preserves_production(app, page):
    run(app, [response(page)])
    with Session(app.state.engine) as db:
        order = db.scalar(select(Order))
        uid = db.scalar(select(User.id))
        order.internal_status, order.priority_override, order.priority_pinned = "BLOCKED", "P0", True
        order.production_started_at = NOW
        db.add(Assignment(order_id=order.id, user_id=uid, assigned_by=uid))
        db.add(Comment(order_id=order.id, author_user_id=uid, body="Кромка"))
        db.add(BlockerType(code="MATERIAL", display_name="Материал"))
        db.flush()
        blocker = Blocker(order_id=order.id, type_code="MATERIAL", description="Кромка", severity="HIGH", status="OPEN")
        db.add(blocker)
        db.flush()
        db.add(ManagerTask(order_id=order.id, source_type="BLOCKER", source_id=blocker.id,
                           title="Кромка", description="Кромка", severity="HIGH", status="OPEN", assigned_to=uid))
        db.commit()
        order_id = order.id
    raw = page["postings"][0]
    raw.update(status="awaiting_deliver", substatus="updated", shipment_date="2026-10-03T15:00:00Z",
               shipment_date_without_delay="2026-10-03T12:00:00Z", delivering_date="2026-10-05T12:00:00Z",
               analytics_data={"delivery_date_begin": "2026-10-05T12:00:00Z", "delivery_date_end": "2026-10-06T12:00:00Z"},
               internal_status="DONE", priority_override=None)
    raw["tariffication_steps"][0]["tariff_rate"] = Decimal("1.25")
    assert run(app, [response(page)])[0]["changed"] == 1
    assert run(app, [response(page)])[0]["changed"] == 0
    with Session(app.state.engine) as db:
        order = db.get(Order, order_id)
        assert order.ozon_status == "awaiting_deliver" and order.ozon_substatus == "updated"
        assert order.shipment_deadline.day == 3 and order.shipment_date_without_delay.hour == 12
        assert order.ozon_delivering_date.day == order.ozon_delivery_date_begin.day == 5
        assert order.ozon_delivery_date_end.day == 6
        assert db.get(OzonPostingData, order_id).tariffication_steps[0]["tariff_rate"] == "1.25"
        assert order.internal_status == "BLOCKED" and order.priority_override == "P0" and order.priority_pinned
        assert order.production_started_at.replace(tzinfo=timezone.utc) == NOW
        assert order.assignment.user_id == uid
        for model in (Order, Assignment, Comment, Blocker, ManagerTask, StatusHistory):
            assert db.query(model).count() == 1
        assert db.scalar(select(ManagerTask)).status == "OPEN"


def test_cancellation_after_start_creates_one_task_and_notification(app, page):
    run(app, [response(page)])
    with Session(app.state.engine) as db:
        order = db.scalar(select(Order))
        order.production_started_at, order.internal_status = NOW, "IN_PRODUCTION"
        db.commit()
    page["postings"][0]["status"] = "cancelled"
    run(app, [response(page)])
    run(app, [response(page)])
    with Session(app.state.engine) as db:
        assert db.scalar(select(Order)).internal_status == "IN_PRODUCTION"
        assert db.query(ManagerTask).filter_by(source_type="OZON_CANCELLED_AFTER_START").count() == 1
        assert db.query(Notification).filter_by(type="ORDER_CANCELLED").count() == 1


def test_missing_old_posting_uses_get_instead_of_inferred_deletion(app, page):
    raw = page["postings"][0]
    with Session(app.state.engine) as db:
        upsert_posting(db, raw, is_mock=False, actor_id=None)
        db.scalar(select(Order)).production_started_at = NOW
        db.commit()
    raw["status"] = "cancelled"
    empty = {"postings": [], "has_next": False, "cursor": ""}
    result, requests = run(app, [response(empty), get_response(raw)])
    assert result["changed"] == result["checked_missing"] == 1
    assert requests[1].url.path == FBS_GET_PATH
    # Terminal cancellation no longer needs get, while all local data remains.
    assert run(app, [response(empty)])[0]["changed"] == 0
    with Session(app.state.engine) as db:
        assert db.query(Order).count() == 1 and db.scalar(select(Order)).ozon_status == "cancelled"


def test_error_dedup_recovery_and_new_outage(app, page):
    run(app, [response(page)])
    with Session(app.state.engine) as db:
        success = db.get(OzonSyncState, 1).last_successful_sync
    failures = [httpx.Response(503)] * 3
    for _ in range(2):
        assert run(app, failures)[0]["error_code"] == "OzonServerError"
    with Session(app.state.engine) as db:
        state = db.get(OzonSyncState, 1)
        assert state.status == "ERROR" and state.last_successful_sync == success
        assert state.last_attempt_at >= success and state.error_episode == 1
        assert db.query(Order).count() == 1
        assert db.query(Notification).filter_by(type="OZON_SYNC_ERROR").count() == 1
        assert db.query(ManagerTask).filter_by(source_type="OZON_RECONCILIATION_ERROR").count() == 1
        assert db.scalar(select(ManagerTask)).status == "OPEN"
    run(app, [response(page)])
    with Session(app.state.engine) as db:
        state = db.get(OzonSyncState, 1)
        assert state.status == "SUCCESS" and state.error_code is None and state.last_successful_sync > success
        assert db.scalar(select(ManagerTask)).status == "RESOLVED"
    run(app, failures)
    with Session(app.state.engine) as db:
        assert db.get(OzonSyncState, 1).error_episode == 2
        assert db.query(Notification).filter_by(type="OZON_SYNC_ERROR").count() == 2
        assert db.query(ManagerTask).count() == 1 and db.scalar(select(ManagerTask)).status == "OPEN"


@pytest.mark.parametrize("bad_page", ["loop", "malformed", "upstream"])
def test_later_page_failure_rolls_back_domain_writes(app, page, bad_page):
    page.update(has_next=True, cursor="same")
    second = copy.deepcopy(page)
    if bad_page == "malformed":
        second["postings"][0]["products"][0]["price"]["amount"] = "bad"
    replies = [response(page)] + ([httpx.Response(503)] * 3 if bad_page == "upstream" else [response(second)])
    assert "error_code" in run(app, replies)[0]
    with Session(app.state.engine) as db:
        assert db.query(Order).count() == db.query(StatusHistory).count() == 0
        assert db.query(Notification).filter_by(type="NEW_ORDER").count() == 0
        assert db.get(OzonSyncState, 1).last_successful_sync is None


def test_staleness_before_first_success_at_threshold_and_mode_isolation(app):
    config = app.state.settings
    with Session(app.state.engine) as db:
        assert sync_status(db, config, now=NOW)["stale"]
        db.add(OzonSyncState(id=1, status="SUCCESS", last_successful_sync=NOW, last_attempt_at=NOW))
        db.commit()
        assert not sync_status(db, config, now=NOW + timedelta(seconds=599))["stale"]
        status = sync_status(db, config, now=NOW + timedelta(seconds=600))
        assert status["stale"] and status["age_seconds"] == 600
        config.ozon_mock_mode = True
        assert sync_status(db, config, now=NOW)["last_successful_sync"] is None


def test_state_api_requires_auth_and_returns_safe_status(app):
    app.state.settings.ozon_mock_mode = True
    with TestClient(app) as client:
        assert client.get("/api/ozon/sync-state").status_code == 401
        login(client)
        state = client.get("/api/ozon/sync-state").json()
        assert state["status"] == "NEVER" and state["stale"] and state["age_seconds"] is None
        assert "api_key" not in state and "client_id" not in state
        assert client.get("/api/health").status_code == client.get("/api/health/ready").status_code == 200


def test_outage_widens_window_and_window_remains_valid(app, page, monkeypatch):
    monkeypatch.setattr("app.ozon_reconciliation.utc_now", lambda: NOW)
    with Session(app.state.engine) as db:
        db.add(OzonSyncState(id=1, status="ERROR", last_successful_sync=NOW - timedelta(days=500)))
        db.commit()
    _, requests = run(app, [response(page)])
    window = json.loads(requests[0].content)["filter"]
    assert datetime.fromisoformat(window["to"]) - datetime.fromisoformat(window["since"]) == timedelta(days=365)


def test_scheduler_runs_immediately_sequentially_and_stops(monkeypatch, app):
    stop = asyncio.Event()
    calls = []

    def once(*args):
        calls.append(1)
        stop.set()

    monkeypatch.setattr("app.ozon_reconciliation.reconcile", once)
    asyncio.run(reconciliation_loop(app.state.engine, Mock(), app.state.settings, Mock(), stop))
    assert calls == [1]


def test_mock_reconciliation_preserves_local_seed_scenarios(app, monkeypatch):
    app.state.settings.ozon_mock_mode = True
    monkeypatch.setattr("app.ozon_reconciliation.utc_now", lambda: NOW)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
    client = MockOzonClient()
    assert reconcile(app.state.engine, client, app.state.settings, Mock())["changed"] == 1
    assert reconcile(app.state.engine, client, app.state.settings, Mock())["changed"] == 0
    with Session(app.state.engine) as db:
        assert db.query(Order).count() == 8


def test_lifespan_starts_worker_and_local_api_works_during_slow_ozon(app, page, monkeypatch):
    entered, release = Event(), Event()

    def blocked_list(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return page

    client = Mock(list_fbs=blocked_list)
    monkeypatch.setattr("app.ozon_credentials.create_ozon_client", lambda _: client)
    app.state.settings.ozon_reconciliation_enabled = True
    try:
        with TestClient(app) as local:
            assert entered.wait(5)
            assert local.get("/api/health").status_code == local.get("/api/health/ready").status_code == 200
            login(local)
            assert local.get("/api/ozon/sync-state").json()["status"] == "RUNNING"
            assert local.get("/api/orders").status_code == 200
            release.set()
        client.close.assert_called_once()
        with Session(app.state.engine) as db:
            assert db.get(OzonSyncState, 1).status == "SUCCESS"
    finally:
        release.set()
