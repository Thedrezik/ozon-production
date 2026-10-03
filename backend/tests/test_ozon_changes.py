import copy
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    AuditLog,
    Blocker,
    BlockerType,
    Comment,
    ManagerTask,
    Notification,
    NotificationDelivery,
    Order,
    OrderTimelineEvent,
    ProductProductionProfile,
    StatusHistory,
    utc_now,
)
from app.ozon_webhook import apply_posting
from tests.test_orders import login
from tests.test_ozon_webhook import context as make_context
from tests.test_ozon_webhook import event, run


@pytest.fixture
def context(tmp_path):
    return make_context.__wrapped__(tmp_path)


def apply(c):
    with Session(c.app.state.engine) as db:
        changed = apply_posting(db, c.raw, c.app.state.settings, from_get=True)
        db.commit()
        return changed


@pytest.mark.parametrize("status", ["NEW", "IN_PRODUCTION", "PRODUCED", "BLOCKED"])
def test_cancellation_preserves_history_and_alerts_worker_and_manager(context, status):
    c = context
    headers = login(c.client)
    worker = c.client.post("/api/users", headers=headers, json={
        "username": "worker", "display_name": "Worker", "password": "worker-password-123",
        "roles": ["PRODUCTION_WORKER"],
    }).json()["id"]
    assert apply(c)
    with Session(c.app.state.engine) as db:
        order = db.scalar(select(Order))
        oid = order.id
        order.internal_status = status
        order.priority_override, order.priority_pinned = "P0", True
        # Also exercise legacy stage data with no production_started_at.
        if status == "PRODUCED":
            order.production_completed_at = utc_now()
        if status == "BLOCKED":
            order.production_started_at = utc_now()
        db.add(Assignment(order_id=oid, user_id=worker))
        db.add(Comment(order_id=oid, author_user_id=worker, body="История"))
        db.add(BlockerType(code="MATERIAL", display_name="Материал"))
        db.add(Blocker(order_id=oid, type_code="MATERIAL", description="Кромка",
                       severity="HIGH", status="OPEN"))
        db.add(OrderTimelineEvent(order_id=oid, event_type="test", description="До отмены"))
        db.add(ManagerTask(order_id=oid, source_type="BLOCKER", source_id=1, title="История",
                           description="История", severity="HIGH", status="RESOLVED"))
        db.commit()
        old_audit = set(db.scalars(select(AuditLog.id)))
        old_history = set(db.scalars(select(StatusHistory.id)))
    c.raw["status"] = "cancelled"
    assert apply(c)
    assert not apply(c)
    # A different nonoperational snapshot must also avoid repeating side effects.
    c.raw["diagnostic"] = "repeat"
    assert apply(c)
    with Session(c.app.state.engine) as db:
        order = db.get(Order, oid)
        assert order.internal_status == status and order.priority_override == "P0" and order.priority_pinned
        assert order.assignment.user_id == worker
        assert db.query(Comment).count() == db.query(Blocker).count() == 1
        assert old_audit <= set(db.scalars(select(AuditLog.id)))
        assert old_history == set(db.scalars(select(StatusHistory.id)))
        assert db.query(OrderTimelineEvent).count() == 2
        tasks = db.scalars(select(ManagerTask).where(ManagerTask.source_type == "OZON_CANCELLED_AFTER_START")).all()
        assert len(tasks) == int(status != "NEW")
        assert db.query(ManagerTask).filter_by(source_type="BLOCKER", status="RESOLVED").count() == 1
        notices = db.scalars(select(Notification).where(Notification.type == "ORDER_CANCELLED")).all()
        assert len(notices) == (0 if status == "NEW" else 2)
        if status != "NEW":
            assert worker in {n.user_id for n in notices}
        delta = json.loads(db.scalar(select(AuditLog.detail).where(AuditLog.action == "ozon.posting.changed")))
        assert delta["changes"]["ozon_status"] == {"old": "awaiting_packaging", "new": "cancelled"}
    assert c.client.get("/api/orders").json()["total"] == 0
    dashboard = c.client.get("/api/dashboard").json()
    assert dashboard["workload"] == [] and dashboard["overdue"] == 0
    assert dashboard["blocked"] == dashboard["ready"] == dashboard["critical"] == 0
    assert c.client.get(f"/api/orders?assigned_user_id={worker}").json()["total"] == 0
    archive = c.client.get("/api/orders?ozon_status=cancelled").json()["items"]
    assert archive[0]["id"] == oid and archive[0]["priority"]["level"] == "P4"
    assert c.client.get(f"/api/orders?order_id={oid}").json()["total"] == 1
    assert c.client.post(f"/api/orders/{oid}/claim", headers=headers).status_code == 409
    if status == "IN_PRODUCTION":
        assert c.client.post(f"/api/orders/{oid}/status", headers=headers,
                             json={"status": "PRODUCED"}).status_code == 409


@pytest.mark.parametrize("hours", [1, 24])
def test_deadline_changes_recalculate_priority_risk_and_pending_notices(context, hours):
    c = context
    login(c.client)
    now = utc_now()
    c.raw["shipment_date"] = (now + timedelta(hours=24 if hours == 1 else 1)).isoformat()
    c.raw["shipment_date_without_delay"] = c.raw["shipment_date"]
    assert apply(c)
    with Session(c.app.state.engine) as db:
        order = db.scalar(select(Order))
        oid = order.id
        for item in order.items:
            db.add(ProductProductionProfile(offer_id=item.offer_id, product_name=item.product_name,
                       production_minutes=20, packing_minutes=10, complexity="LOW"))
        c.raw["tariffication"] = {"current_tariff_type": "commission", "current_tariff_charge": {"amount": "0", "currency": "RUB"},
                                  "next_tariff_type": "commission", "next_tariff_charge": {"amount": "120", "currency": "RUB"},
                                  "next_tariff_starts_at": (now + timedelta(hours=10)).isoformat()}
        from app.ozon_tariff import normalize
        order.tariff_steps = normalize(c.raw, now)
        # Add an optional channel delivery for the existing deadline notice.
        old_notice = db.scalar(select(Notification).where(Notification.type == "SHIPMENT_DEADLINE"))
        if old_notice:
            db.add(NotificationDelivery(notification_id=old_notice.id, channel="TELEGRAM", status="PENDING"))
        db.commit()
    before = c.client.get(f"/api/orders?order_id={oid}").json()["items"][0]["priority"]
    risk_before = c.client.get("/api/money-at-risk").json()
    c.raw["shipment_date"] = (now + timedelta(hours=hours)).isoformat()
    c.raw["shipment_date_without_delay"] = c.raw["shipment_date"]
    c.raw["analytics_data"] = {"delivery_date_begin": (now + timedelta(days=3)).isoformat(),
                                "delivery_date_end": (now + timedelta(days=4)).isoformat()}
    assert apply(c)
    assert not apply(c)
    after = c.client.get(f"/api/orders?order_id={oid}").json()["items"][0]["priority"]
    risk_after = c.client.get("/api/money-at-risk").json()
    assert (after["score"] > before["score"]) == (hours == 1)
    assert risk_before["categories"] != risk_after["categories"]
    assert Decimal(risk_after["total"]) == Decimal(120)
    with Session(c.app.state.engine) as db:
        notices = db.scalars(select(Notification).where(Notification.type == "SHIPMENT_DEADLINE")).all()
        assert len(notices) == 1
        assert (notices[0].read_at is None) == (hours == 1)
        if hours == 24:
            assert db.scalar(select(NotificationDelivery.status).where(
                NotificationDelivery.channel == "TELEGRAM")) == "SKIPPED"
        change = json.loads(db.scalar(select(AuditLog.detail).where(AuditLog.action == "ozon.posting.changed")))
        assert "Срок отгрузки" in db.scalar(select(OrderTimelineEvent.description))
        assert set(change["changes"]) >= {"shipment_deadline", "shipment_date_without_delay",
                                         "ozon_delivery_date_begin", "ozon_delivery_date_end"}
    c.raw["status"] = "cancelled"
    assert apply(c)
    assert Decimal(c.client.get("/api/money-at-risk").json()["total"]) == 0
    with Session(c.app.state.engine) as db:
        assert all(n.read_at for n in db.scalars(select(Notification).where(
            Notification.type.in_(("SHIPMENT_DEADLINE", "TARIFF_DEADLINE")))))


def test_explicit_import_uses_shared_cancellation_effects_and_sse(context):
    c = context
    headers = login(c.client)
    assert apply(c)
    with Session(c.app.state.engine) as db:
        db.scalar(select(Order)).internal_status = "PRODUCED"
        db.commit()
    raw = copy.deepcopy(c.raw)
    raw["status"] = "cancelled"
    for product in raw["products"]:
        product["price"] = {"amount": product["price"], "currency": product.pop("currency_code")}
    c.app.state.ozon_client = Mock()
    c.app.state.ozon_client.list_fbs.return_value = {"postings": [raw], "has_next": False}
    c.app.state.order_events = Mock()
    window = {"since": "2026-10-01T00:00:00Z", "to": "2026-10-04T00:00:00Z"}
    assert c.client.post("/api/ozon/fbs/import", headers=headers, json=window).json()["changed"] == 1
    assert c.client.post("/api/ozon/fbs/import", headers=headers, json=window).json()["changed"] == 0
    c.app.state.order_events.publish.assert_called_once_with(0)
    with Session(c.app.state.engine) as db:
        assert db.query(ManagerTask).filter_by(source_type="OZON_CANCELLED_AFTER_START").count() == 1


def test_webhook_deadline_change_publishes_after_commit(context):
    c = context
    c.client.post("/api/ozon/webhook", json=event())
    assert run(c)
    c.raw["shipment_date"] = "2026-10-03T12:00:00Z"
    c.client.post("/api/ozon/webhook", json=event("TYPE_CUTOFF_DATE_CHANGED"))
    assert run(c)
    assert c.bus.publish.call_count == 2
    with Session(c.app.state.engine) as db:
        assert db.query(OrderTimelineEvent).count() == 1
