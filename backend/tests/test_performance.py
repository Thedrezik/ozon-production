"""Synthetic, private SQLite workload; never touches a deployment database."""
import asyncio
import os
import time
import tracemalloc
from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import event, insert, select, text
from sqlalchemy.orm import Session
from test_orders import login, setup_app

from app.models import (
    Assignment,
    Comment,
    Notification,
    NotificationPreference,
    Order,
    OrderItem,
    OrderTimelineEvent,
    ProcurementTask,
    StatusHistory,
    User,
    utc_now,
)
from app.order_events import OrderEvents
from app.orders import seed_mock_orders
from app.performance import BATCH_SIZE


def synthetic_app(tmp_path, size=2000):
    app = setup_app(tmp_path)
    now = utc_now()
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        db.execute(insert(Order), [{
            "posting_number": f"SYNTHETIC-{i}", "ozon_status": "awaiting_packaging",
            "internal_status": "QUEUED", "is_mock": True,
            "shipment_deadline": now + timedelta(days=2), "created_at": now,
            "production_started_at": now - timedelta(hours=2),
            "production_completed_at": now - timedelta(hours=1),
            "tariff_steps": [{"starts_at": None,
                           "tariff_type": "base", "cost": "10", "currency": "RUB"},
                          {"starts_at": (now + timedelta(hours=1)).isoformat(),
                           "tariff_type": "late", "cost": "20", "currency": "RUB"}],
        } for i in range(size)])
        ids = db.query(Order.id).filter(Order.posting_number.like("SYNTHETIC-%")).all()
        db.execute(insert(OrderItem), [{"order_id": row.id, "product_name": "Synthetic table",
                                            "offer_id": "SYNTHETIC", "quantity": 1} for row in ids])
        db.commit()
    return app


def test_synthetic_key_pages(tmp_path):
    size = int(os.getenv("PERFORMANCE_SIZE", "2000"))
    app = synthetic_app(tmp_path, size)
    with TestClient(app) as client:
        login(client)
        for path in ("/api/orders?limit=20", "/api/dashboard", "/api/money-at-risk",
                     f"/api/analytics?start={utc_now().date()}&end={utc_now().date()}"):
            queries = []
            def record(_conn, _cursor, statement, _parameters, _context, _many, queries=queries):
                queries.append(statement)
            event.listen(app.state.engine, "before_cursor_execute", record)
            trace = os.getenv("PERFORMANCE_TRACE", "1") != "0"
            if trace:
                tracemalloc.start()
            started = time.perf_counter()
            try:
                response = client.get(path)
                elapsed = time.perf_counter() - started
                peak = f"{tracemalloc.get_traced_memory()[1] / 1024**2:.2f}" if trace else "unmeasured"
            finally:
                if trace:
                    tracemalloc.stop()
                event.remove(app.state.engine, "before_cursor_execute", record)
            assert response.status_code == 200, response.text
            print(f"{path}: queries={len(queries)} seconds={elapsed:.3f} python_peak_mib={peak}")
            assert len(queries) <= 20 + 6 * ((size + 7 + BATCH_SIZE - 1) // BATCH_SIZE)
            data = response.json()
            if path.startswith("/api/orders"):
                assert data["total"] == size + 6 and len(data["items"]) == 20
            if path.startswith("/api/analytics"):
                assert data["throughput"]["produced"] >= size
            if path == "/api/money-at-risk":
                assert Decimal(data["total"]) >= size * 10
                # A local cutoff/midnight may precede the rolling near-hours end.
                # Drill into the actual disjoint bucket containing the workload.
                bucket = next(row["key"] for row in data["buckets"] if row["order_count"] >= size)
                detail = client.get("/api/money-at-risk/orders", params={"bucket": bucket, "limit": 3, "offset": 2}).json()
                assert detail["total"] >= size and len(detail["items"]) == 3
                assert Decimal(detail["amount"]) >= size * 10
        for path in ("/api/orders?limit=101", "/api/orders?offset=-1",
                     "/api/orders?offset=10001",
                     "/api/money-at-risk/orders?bucket=next_hours&limit=101",
                     "/api/analytics?start=2026-01-01&end=2026-01-01&page_size=101"):
            assert client.get(path).status_code == 422


def test_event_burst_is_coalesced():
    async def scenario():
        bus = OrderEvents()
        queues = [bus.subscribe() for _ in range(10)]
        for value in range(1000):
            bus.publish(value)
        assert len(bus._pending) == len(queues)
        await asyncio.sleep(0)
        assert all(queue.qsize() == 1 and queue.get_nowait() == 999 for queue in queues)
        for queue in queues:
            bus.unsubscribe(queue)
        assert not bus._subscribers
    asyncio.run(scenario())


def test_notifications_repeated_reconciliation_has_no_per_order_reads(tmp_path):
    from app.notifications import sync_deadline_notifications
    app = synthetic_app(tmp_path, 60)
    with Session(app.state.engine) as db:
        assert sync_deadline_notifications(db, "Europe/Moscow") >= 60
        db.commit()
    queries = []
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        queries.append(statement)
    event.listen(app.state.engine, "before_cursor_execute", record)
    try:
        with Session(app.state.engine) as db:
            assert sync_deadline_notifications(db, "Europe/Moscow") == 0
            db.commit()
    finally:
        event.remove(app.state.engine, "before_cursor_execute", record)
    assert len(queries) < 20


def test_batched_deadline_notifications_respect_channel_opt_out(tmp_path):
    from app.notifications import sync_deadline_notifications
    app = synthetic_app(tmp_path, 20)
    with Session(app.state.engine) as db:
        admin_id = db.scalar(select(User.id).where(User.username == "admin"))
        for kind in ("TARIFF_DEADLINE", "SHIPMENT_DEADLINE"):
            db.add(NotificationPreference(user_id=admin_id, type=kind, channel="IN_APP", enabled=False))
        db.commit()
        sync_deadline_notifications(db, "Europe/Moscow")
        db.commit()
        assert db.query(Notification).filter(Notification.type.in_(("TARIFF_DEADLINE", "SHIPMENT_DEADLINE"))).count() == 0
        assert db.query(Notification).filter_by(type="ORDER_OVERDUE").count() > 0


def test_overdue_procurement_manager_page_has_no_per_source_reads(tmp_path):
    from app.procurement import sync_all_overdue
    app = synthetic_app(tmp_path, 10)
    with Session(app.state.engine) as db:
        db.execute(insert(ProcurementTask), [{"material_name": f"Synthetic material {index}",
            "quantity": Decimal(1), "unit": "piece", "severity": "HIGH", "status": "NEW",
            "needed_by": utc_now() - timedelta(hours=1)} for index in range(60)])
        sync_all_overdue(db)
        db.commit()
    queries = []
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        queries.append(statement)
    with TestClient(app) as client:
        login(client)
        event.listen(app.state.engine, "before_cursor_execute", record)
        try:
            response = client.get("/api/manager-tasks?source_type=PROCUREMENT_OVERDUE&limit=20")
        finally:
            event.remove(app.state.engine, "before_cursor_execute", record)
    assert response.status_code == 200
    assert response.json()["total"] == 60 and len(response.json()["items"]) == 20
    assert len(queries) < 25


def test_stream_capacity_is_bounded():
    async def scenario():
        bus = OrderEvents()
        queues = [bus.subscribe() for _ in range(100)]
        import pytest
        with pytest.raises(ValueError):
            bus.subscribe()
        bus.unsubscribe(queues.pop())
        queues.append(bus.subscribe())
        for queue in queues:
            bus.unsubscribe(queue)
    asyncio.run(scenario())


def test_archive_and_exact_ranked_pagination(tmp_path, monkeypatch):
    from app import api_orders
    from app.priority import sort_key
    app = synthetic_app(tmp_path, 520)
    now = utc_now()
    monkeypatch.setattr(api_orders, "utc_now", lambda: now)
    with Session(app.state.engine) as db:
        closed = db.scalar(select(Order).where(Order.posting_number == "SYNTHETIC-0"))
        closed.internal_status = "DONE"
        closed_id = closed.id
        handed = db.scalar(select(Order).where(Order.posting_number == "SYNTHETIC-1"))
        handed.internal_status = "HANDED_TO_SHIPPING"
        handed.shipment_deadline = now - timedelta(hours=1)
        pinned = db.scalar(select(Order).where(Order.posting_number == "SYNTHETIC-500"))
        pinned.priority_override, pinned.priority_pinned = "P0", True
        admin_id = db.scalar(select(User.id).where(User.username == "admin"))
        db.add(Assignment(order_id=closed_id, user_id=admin_id, assigned_by=admin_id))
        db.add(Assignment(order_id=handed.id, user_id=admin_id, assigned_by=admin_id))
        db.add(Assignment(order_id=pinned.id, user_id=admin_id, assigned_by=admin_id))
        db.commit()
        orders = db.scalars(api_orders.order_query().where(Order.internal_status.notin_(
            ("DONE", "CANCELLED", "HANDED_TO_SHIPPING")), Order.ozon_status != "cancelled")).all()
        profiles = api_orders.production_profiles(db, orders)
        settings = api_orders.priority_settings(db)
        expected = [(api_orders.priority_for(order, profiles, settings, now), order.id)
                    for order in orders]
        expected.sort(key=lambda pair: sort_key(*pair))
    with TestClient(app) as client:
        login(client)
        result = client.get("/api/orders?limit=10&offset=15").json()
        assert [row["id"] for row in result["items"]] == [row[1] for row in expected[15:25]]
        assert result["total"] == len(expected)
        assert client.get("/api/orders?status=DONE").json()["items"][0]["id"] == closed_id
        assert client.get(f"/api/orders?order_id={closed_id}").json()["items"][0]["id"] == closed_id
        dashboard = client.get("/api/dashboard").json()
        assert dashboard["workload"][0]["active_orders"] == 1
        assert dashboard["overdue"] == client.get("/api/orders?overdue=true").json()["total"]


def test_timeline_sql_page_and_indexes(tmp_path):
    app = synthetic_app(tmp_path, 10)
    with Session(app.state.engine) as db:
        order_id = db.scalar(select(Order.id).where(Order.posting_number == "SYNTHETIC-0"))
        now = utc_now()
        db.execute(insert(Comment), [{"order_id": order_id, "body": "Synthetic", "created_at": now}
                                    for _ in range(1000)])
        db.execute(insert(OrderTimelineEvent), [{"order_id": order_id, "event_type": "synthetic",
                    "description": "Synthetic", "created_at": now} for _ in range(300)])
        db.commit()
        expected = []
        for model, timestamp, prefix in ((Comment, Comment.created_at, "comment"),
                (OrderTimelineEvent, OrderTimelineEvent.created_at, "event"),
                (StatusHistory, StatusHistory.changed_at, "status")):
            expected.extend((stamp, f"{prefix}-{row_id}") for row_id, stamp in db.execute(
                select(model.id, timestamp).where(model.order_id == order_id)))
        expected.sort()
        plan = db.execute(text("EXPLAIN QUERY PLAN SELECT id FROM notifications WHERE user_id=1 "
                               "ORDER BY created_at DESC, id DESC LIMIT 20")).all()
        assert any("ix_notifications_user_created_id" in row[-1] for row in plan)
    with TestClient(app) as client:
        login(client)
        page = client.get(f"/api/orders/{order_id}/timeline?limit=17&offset=950").json()
        assert page["total"] == 1300
        assert [row["id"] for row in page["items"]] == [row[1] for row in expected[950:967]]
        assert client.get(f"/api/orders/{order_id}/history?limit=201").status_code == 422
