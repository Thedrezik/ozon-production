import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    InternalStatus,
    ManagerTask,
    Notification,
    NotificationDelivery,
    Order,
    OzonPostingData,
    OzonWebhookEvent,
    StatusHistory,
    utc_now,
)
from app.orders import STATUS_LABELS, STATUSES
from app.ozon import FBS_GET_PATH, MockOzonClient, OzonNetworkError, OzonResponseError
from app.ozon_import import diagnostic_json
from app.ozon_webhook import allowed_source, process_one
from tests.test_orders import login, setup_app
from tests.test_ozon import client_for

URL = "/api/ozon/webhook"
NUMBER = "0210000001-0001-1"
BASE = {"posting_number": NUMBER, "warehouse_id": 20605650762000, "seller_id": 15}


def event(kind="TYPE_NEW_POSTING", **overrides):
    data = {**BASE, "message_type": kind}
    if kind == "TYPE_NEW_POSTING":
        data.update(products=[{"sku": 1904686181, "offer_id": "DESK", "quantity": 1}],
                    shipment_date="2026-10-02T12:00:00Z", in_process_at=None)
    if kind in ("TYPE_STATE_CHANGED", "TYPE_POSTING_CANCELLED"):
        data.update(new_state="posting_delivered", changed_state_date="2026-10-01T12:00:00Z")
    if kind == "TYPE_POSTING_CANCELLED":
        data.update(new_state="posting_canceled", old_state="posting_created",
                    products=[{"sku": 1904686181, "quantity": 1}], reason={"id": 1, "message": "Отмена"})
    if kind == "TYPE_CUTOFF_DATE_CHANGED":
        data.update(old_cutoff_date="2026-10-02T12:00:00Z", new_cutoff_date="2026-10-03T12:00:00Z")
    if kind == "TYPE_DELIVERY_DATE_CHANGED":
        data.update(old_delivery_date_begin=None, old_delivery_date_end=None,
                    new_delivery_date_begin="2026-10-03T12:00:00Z", new_delivery_date_end="2026-10-03T16:00:00Z")
    return {**data, **overrides}


@pytest.fixture
def context(tmp_path):
    app = setup_app(tmp_path)
    app.state.settings.ozon_webhook_enabled = True
    with Session(app.state.engine) as db:
        for i, status in enumerate(STATUSES):
            db.add(InternalStatus(name=status, display_name=STATUS_LABELS[i], sort_order=i))
        db.commit()
    raw = json.loads((Path(__file__).parents[1] / "app/fixtures/fbs_v4.json").read_text(encoding="utf-8"),
                     parse_float=Decimal)["postings"][0]
    for product in raw["products"]:
        product["currency_code"] = product["price"]["currency"]
        product["price"] = product["price"]["amount"]
    api = Mock()
    api.get_fbs.side_effect = lambda number: copy.deepcopy(raw)
    bus = Mock()
    # No lifespan here: processing is invoked deterministically, never against production.
    client = TestClient(app)
    return SimpleNamespace(app=app, raw=raw, api=api, bus=bus, client=client)


def run(c):
    return process_one(c.app.state.engine, c.api, c.app.state.settings, c.bus)


def test_receipt_is_fast_durable_and_does_not_call_seller_api(context):
    c = context
    assert c.client.post(URL, json=event()).json() == {"result": True}
    c.api.get_fbs.assert_not_called()
    with Session(c.app.state.engine) as db:
        row = db.scalar(select(OzonWebhookEvent))
        assert row.status == "PENDING" and row.attempts == 0
        assert json.loads(row.payload_json) == event()
        assert db.query(Order).count() == 0
    assert run(c)
    with Session(c.app.state.engine) as db:
        order = db.scalar(select(Order))
        assert order.ozon_status == "awaiting_packaging" and order.internal_status == "NEW"
        assert order.order_value == Decimal("19970.60")
        assert order.items[1].price == Decimal("3490.2500")
        assert db.scalar(select(OzonWebhookEvent)).status == "PROCESSED"
        assert json.loads(db.get(OzonPostingData, order.id).raw_json, parse_float=Decimal) == c.raw
        assert db.query(StatusHistory).count() == 1
        assert db.query(Notification).filter_by(type="NEW_ORDER").count() == 1
    c.bus.publish.assert_called_once_with(1)


def test_duplicate_before_and_after_processing_is_http_200_and_noop(context):
    c = context
    payload = event()
    for _ in range(2):
        assert c.client.post(URL, json=payload).status_code == 200
    assert run(c)
    # Different whitespace/key order has the same canonical identity.
    assert c.client.post(URL, content=json.dumps(dict(reversed(list(payload.items()))), indent=2),
                         headers={"Content-Type": "application/json"}).json() == {"result": True}
    assert not run(c)
    with Session(c.app.state.engine) as db:
        assert db.query(OzonWebhookEvent).count() == db.query(Order).count() == 1
        assert db.query(Notification).filter_by(type="NEW_ORDER").count() == 1
        assert db.query(NotificationDelivery).count() == db.query(Notification).count()
        assert db.query(AuditLog).filter(AuditLog.action.like("ozon.posting.%")).count() == 1
    assert c.api.get_fbs.call_count == c.bus.publish.call_count == 1


def test_state_change_uses_current_authoritative_status_not_push_mapping(context):
    c = context
    c.client.post(URL, json=event())
    run(c)
    c.raw.update(status="delivered", substatus="posting_received")
    c.client.post(URL, json=event("TYPE_STATE_CHANGED", new_state="posting_transferring_to_delivery"))
    run(c)
    with Session(c.app.state.engine) as db:
        order = db.scalar(select(Order))
        assert order.ozon_status == "delivered" and order.ozon_substatus == "posting_received"
        assert order.internal_status == "NEW" and db.query(StatusHistory).count() == 1
    assert c.bus.publish.call_count == 2


@pytest.mark.parametrize("started", [False, True])
def test_cancellation_and_distinct_redelivery_have_no_duplicate_tasks_or_notifications(context, started):
    c = context
    c.client.post(URL, json=event())
    run(c)
    with Session(c.app.state.engine) as db:
        order = db.scalar(select(Order))
        order.internal_status = "IN_PRODUCTION" if started else "NEW"
        order.production_started_at = utc_now() if started else None
        db.commit()
    c.raw.update(status="cancelled", substatus="posting_canceled")
    cancelled = event("TYPE_POSTING_CANCELLED")
    for payload in (cancelled, cancelled, {**cancelled, "reason": {"id": 1, "message": "Повтор"}}):
        assert c.client.post(URL, json=payload).json() == {"result": True}
        run(c)
    with Session(c.app.state.engine) as db:
        order = db.scalar(select(Order))
        assert order.internal_status == ("IN_PRODUCTION" if started else "NEW")
        assert order.ozon_status == "cancelled"
        assert db.query(Notification).filter_by(type="ORDER_CANCELLED").count() == (1 if started else 0)
        assert db.query(ManagerTask).filter_by(source_type="OZON_CANCELLED_AFTER_START").count() == int(started)
        assert db.query(StatusHistory).count() == 1


def test_date_changes_refresh_shared_import_and_delivery_interval(context):
    c = context
    c.client.post(URL, json=event())
    run(c)
    c.raw["shipment_date"] = "2026-10-03T12:00:00Z"
    c.client.post(URL, json=event("TYPE_CUTOFF_DATE_CHANGED"))
    run(c)
    c.raw["analytics_data"] = {"delivery_date_begin": "2026-10-03T12:00:00Z",
                               "delivery_date_end": "2026-10-03T16:00:00Z"}
    c.client.post(URL, json=event("TYPE_DELIVERY_DATE_CHANGED"))
    run(c)
    with Session(c.app.state.engine) as db:
        order = db.scalar(select(Order))
        assert order.shipment_deadline.day == 3
        assert order.ozon_delivery_date_begin.hour == 12 and order.ozon_delivery_date_end.hour == 16


@pytest.mark.parametrize("kind,overrides", [
    ("TYPE_CUTOFF_DATE_CHANGED", {"new_cutoff_date": ""}),
    ("TYPE_DELIVERY_DATE_CHANGED", {"new_delivery_date_begin": None}),
])
def test_empty_dates_are_acknowledged_and_ignored(context, kind, overrides):
    c = context
    assert c.client.post(URL, json=event(kind, **overrides)).status_code == 200
    run(c)
    c.api.get_fbs.assert_not_called()
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(OzonWebhookEvent)).status == "IGNORED"


def test_cutoff_after_assembly_is_ignored(context):
    c = context
    c.raw["status"] = "awaiting_deliver"
    c.client.post(URL, json=event("TYPE_CUTOFF_DATE_CHANGED"))
    run(c)
    with Session(c.app.state.engine) as db:
        assert db.query(Order).count() == 0
        assert db.scalar(select(OzonWebhookEvent)).status == "IGNORED"


@pytest.mark.parametrize("body", ["{", "null", "[]", '{"message_type":"TYPE_NEW_POSTING"}',
                                  '{"message_type":"TYPE_PING","time":"no date"}',
                                  '{"message_type":"TYPE_PING","time":1790866800}',
                                  '{"message_type":"TYPE_PING","time":"1790866800"}',
                                  '{"message_type":"TYPE_PING","time":"2026-10-01T12:00:00"}',
                                  '{"message_type":"UNKNOWN","x":NaN}'])
def test_malformed_payload_has_documented_error_and_diagnostics(context, body):
    c = context
    response = c.client.post(URL, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json()["error"] == {"code": "ERROR_PARAMETER_VALUE_MISSED",
                                        "message": "Invalid webhook payload", "details": None}
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(OzonWebhookEvent)).status == "REJECTED"
    assert not run(c)


def test_unknown_event_is_saved_ignored_and_acknowledged(context):
    c = context
    assert c.client.post(URL, json={"message_type": "TYPE_FBO_POSTING_NEW", "uuid": "future"}).json() == {"result": True}
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(OzonWebhookEvent)).status == "IGNORED"
    assert not run(c)


def test_ping_handshake_and_periodic_check(context):
    c = context
    payload = {"message_type": "TYPE_PING", "time": "2026-10-01T12:00:00Z"}
    for _ in range(2):
        response = c.client.post(URL, json=payload)
        assert response.status_code == 200
        assert set(response.json()) == {"version", "name", "time"}
        assert response.json()["time"].endswith("+00:00")
    assert not run(c)


def test_processing_failure_is_durable_safe_retry_and_error_alert_resolves(context, caplog):
    c = context
    c.client.post(URL, json=event())
    c.api.get_fbs.side_effect = RuntimeError("SECRET-do-not-log")
    for _ in range(2):
        run(c)
        with Session(c.app.state.engine) as db:
            row = db.scalar(select(OzonWebhookEvent))
            assert row.status == "RETRY" and row.error_code == "PROCESSING_ERROR"
            row.next_attempt_at = utc_now() - timedelta(seconds=1)
            db.commit()
    assert "SECRET-do-not-log" not in caplog.text
    with Session(c.app.state.engine) as db:
        assert db.query(Order).count() == 0
        assert db.query(ManagerTask).count() == db.query(Notification).count() == 1
    c.api.get_fbs.side_effect = lambda _: copy.deepcopy(c.raw)
    assert run(c)
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(OzonWebhookEvent)).status == "PROCESSED"
        assert db.scalar(select(ManagerTask)).status == "RESOLVED"


def test_projection_failure_rolls_back_posting_notifications_and_completion(context, monkeypatch):
    c = context
    c.client.post(URL, json=event())
    def fail(*_):
        raise ValueError("bad projection")
    monkeypatch.setattr("app.ozon_webhook.refresh_projections", fail)
    run(c)
    with Session(c.app.state.engine) as db:
        assert db.query(Order).count() == db.query(StatusHistory).count() == 0
        assert db.query(Notification).filter_by(type="NEW_ORDER").count() == 0
        assert db.scalar(select(OzonWebhookEvent)).status == "RETRY"
    c.bus.publish.assert_called_once_with(0)


def test_retry_exhaustion_and_admin_replay_permissions(context):
    c = context
    c.client.post(URL, json=event())
    c.api.get_fbs.side_effect = OzonNetworkError()
    for _ in range(5):
        assert run(c)
        with Session(c.app.state.engine) as db:
            row = db.scalar(select(OzonWebhookEvent))
            row.next_attempt_at = utc_now() - timedelta(seconds=1)
            db.commit()
    assert not run(c)
    retry_url = "/api/ozon/webhook/events/1/retry"
    assert c.client.post(retry_url).status_code == 401
    headers = login(c.client)
    assert c.client.post(retry_url).status_code == 403
    assert c.client.post(retry_url, headers=headers).json() == {"status": "PENDING"}
    c.api.get_fbs.side_effect = lambda _: copy.deepcopy(c.raw)
    run(c)
    assert c.client.post(retry_url, headers=headers).json() == {"status": "PROCESSED"}
    assert not run(c)


def test_disabled_size_limit_content_type_and_database_failure(context, monkeypatch):
    c = context
    c.app.state.settings.ozon_webhook_enabled = False
    assert c.client.post(URL, json=event()).status_code == 503
    c.app.state.settings.ozon_webhook_enabled = True
    assert c.client.post(URL, content="x" * (256 * 1024 + 1)).status_code == 413
    assert c.client.post(URL, content=json.dumps(event())).status_code == 400
    from sqlalchemy.exc import OperationalError
    def fail(*_):
        raise OperationalError("INSERT", {}, Exception("secret"))
    monkeypatch.setattr("app.ozon_webhook.store_event", fail)
    response = c.client.post(URL, json=event())
    assert response.status_code == 503 and response.json()["error"]["code"] == "ERROR_UNKNOWN"


def test_source_ip_and_proxy_spoofing(context):
    c = context
    cfg = c.app.state.settings
    cfg.ozon_mock_mode = False
    def allowed(host, headers=()):
        return allowed_source(Request({"type": "http", "client": (host, 12),
                                       "headers": headers, "app": c.app}))
    assert allowed("195.34.21.15")
    assert not allowed("203.0.113.1", [(b"x-ozon-source-ip", b"195.34.21.15")])
    cfg.ozon_webhook_trusted_proxies = "172.18.0.4/32"
    assert allowed("172.18.0.4", [(b"x-ozon-source-ip", b"195.34.21.15")])
    assert not allowed("172.18.0.5", [(b"x-ozon-source-ip", b"195.34.21.15")])
    assert not allowed("172.18.0.4", [(b"x-ozon-source-ip", b"203.0.113.1")])
    assert c.client.post(URL, json=event()).status_code == 403


def test_real_seller_check_before_storage(context):
    c = context
    c.app.state.settings.ozon_mock_mode = False
    c.app.state.settings.ozon_client_id = "15"
    client = TestClient(c.app, client=("195.34.21.15", 1234))
    assert client.post(URL, json=event(seller_id=99)).status_code == 403
    with Session(c.app.state.engine) as db:
        assert db.query(OzonWebhookEvent).count() == 0
    assert client.post(URL, json=event()).status_code == 200
    with Session(c.app.state.engine) as db:
        assert not db.scalar(select(OzonWebhookEvent)).is_mock


def test_concurrent_duplicate_receipts_create_one_durable_event(context):
    c = context
    def post(_):
        return c.client.post(URL, json=event()).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(post, range(8))) == [200] * 8
    assert run(c) and not run(c)
    with Session(c.app.state.engine) as db:
        assert db.query(OzonWebhookEvent).count() == db.query(Order).count() == 1
        assert db.query(Notification).filter_by(type="NEW_ORDER").count() == 1


def test_existing_posting_without_snapshot_uses_same_upsert(context):
    c = context
    with Session(c.app.state.engine) as db:
        db.add(Order(posting_number=NUMBER, ozon_status="awaiting_packaging", internal_status="IN_PRODUCTION",
                     shipment_deadline=utc_now(), production_started_at=utc_now(), is_mock=True,
                     priority_override="P0", priority_pinned=True))
        db.commit()
    c.client.post(URL, json=event())
    run(c)
    with Session(c.app.state.engine) as db:
        order = db.scalar(select(Order))
        assert order.internal_status == "IN_PRODUCTION" and order.priority_override == "P0"
        assert order.priority_pinned and order.production_started_at
        assert db.query(Order).count() == db.query(OzonPostingData).count() == 1
        assert db.query(StatusHistory).count() == 0
        assert db.query(Notification).filter_by(type="NEW_ORDER").count() == 0


def test_wrong_posting_response_is_retried_without_mutation(context):
    c = context
    c.raw["posting_number"] = "wrong"
    c.client.post(URL, json=event())
    run(c)
    with Session(c.app.state.engine) as db:
        assert db.query(Order).count() == 0
        assert db.scalar(select(OzonWebhookEvent)).status == "RETRY"


def test_current_get_contract_and_response_validation(context):
    c = context
    client, requests, _ = client_for([httpx.Response(200, text=diagnostic_json({"result": c.raw}))])
    with client:
        assert client.get_fbs(NUMBER) == c.raw
    assert requests[0].url.path == FBS_GET_PATH
    assert json.loads(requests[0].content) == {"posting_number": NUMBER,
                                            "with": {"analytics_data": True, "financial_data": True}}
    client, _, _ = client_for([httpx.Response(200, json={"result": {"posting_number": "wrong"}})])
    with client, pytest.raises(OzonResponseError):
        client.get_fbs(NUMBER)
    assert MockOzonClient().get_fbs(NUMBER)["products"][0]["currency_code"] == "RUB"


def test_lifespan_worker_recovers_pending_inbox_and_does_not_delay_response(context, monkeypatch):
    c = context
    c.client.post(URL, json=event())
    entered, release = threading.Event(), threading.Event()
    def slow_get(_):
        entered.set()
        assert release.wait(5)
        return copy.deepcopy(c.raw)
    c.api.get_fbs.side_effect = slow_get
    monkeypatch.setattr("app.ozon_credentials.create_ozon_client", lambda _: c.api)
    with TestClient(c.app) as client:
        assert entered.wait(5)
        # HTTP receipt succeeds while the slow API call is still blocked.
        assert client.post(URL, json={"message_type": "TYPE_PING", "time": "2026-10-01T12:00:00Z"}).status_code == 200
        release.set()
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(OzonWebhookEvent).where(OzonWebhookEvent.message_type == "TYPE_NEW_POSTING")).status == "PROCESSED"


def test_deadline_and_risk_engines_observe_changed_data_and_exclude_cancellation(context):
    c = context
    now = utc_now()
    c.raw["shipment_date"] = (now + timedelta(hours=1)).isoformat()
    c.client.post(URL, json=event())
    run(c)
    headers = login(c.client)
    order = c.client.get("/api/orders").json()["items"][0]
    assert order["priority"]["level"] in ("P0", "P1", "P2")
    with Session(c.app.state.engine) as db:
        row = db.scalar(select(Order))
        row.tariff_steps = [{"starts_at": None, "cost": "100", "currency": "RUB", "tariff_type": "commission"},
                           {"starts_at": (now + timedelta(minutes=30)).isoformat(), "cost": "200",
                            "currency": "RUB", "tariff_type": "commission"}]
        db.commit()
    assert Decimal(c.client.get("/api/money-at-risk").json()["total"]) == 100
    c.raw["status"] = "cancelled"
    c.client.post(URL, json=event("TYPE_POSTING_CANCELLED"))
    run(c)
    assert Decimal(c.client.get("/api/money-at-risk").json()["total"]) == 0
    with Session(c.app.state.engine) as db:
        assert db.query(Notification).filter_by(type="SHIPMENT_DEADLINE").count() == 1
    assert headers
