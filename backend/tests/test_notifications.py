from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BlockerType, Notification, NotificationDelivery
from app.notifications import emit
from app.orders import seed_mock_orders
from tests.test_orders import login, setup_app


def test_blocker_notifications_preferences_and_reprocessing(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        db.add(BlockerType(code="OTHER", display_name="Other"))
        db.commit()
    with TestClient(app) as admin:
        headers = login(admin)
        order_id = admin.get("/api/orders?status=QUEUED").json()["items"][0]["id"]
        payload = {"order_id": order_id, "type_code": "OTHER", "description": "Нет детали"}
        result = admin.post("/api/blockers", json=payload, headers=headers)
        assert result.status_code == 201
        blocker_id = result.json()["id"]
        notices = admin.get("/api/notifications").json()
        created = [n for n in notices["items"] if n["type"] == "BLOCKER_CREATED"]
        assert len(created) == 1
        assert "Нет детали" in created[0]["body"]
        assert admin.post(f"/api/notifications/{created[0]['id']}/read", headers=headers).status_code == 200
        assert next(n for n in admin.get("/api/notifications").json()["items"] if n["id"] == created[0]["id"])["read_at"]
        # A mandatory manager notice cannot be switched off.
        assert admin.put("/api/notifications/preferences", headers=headers,
                         json={"type": "BLOCKER_CREATED", "channel": "IN_APP", "enabled": False}).status_code == 409
        assert admin.put("/api/notifications/preferences", headers=headers,
                         json={"type": "BLOCKER_RESOLVED", "channel": "IN_APP", "enabled": False}).status_code == 200
        assert admin.patch(f"/api/blockers/{blocker_id}", headers=headers,
                           json={"status": "RESOLVED"}).status_code == 200
        assert not [n for n in admin.get("/api/notifications").json()["items"] if n["type"] == "BLOCKER_RESOLVED"]
        # Replaying the same source event cannot create a second row.
        with Session(app.state.engine) as db:
            emit(db, type="BLOCKER_CREATED", event_key=f"blocker:{blocker_id}",
                 user_ids=[1], title="Replay", body="Replay")
            db.commit()
            count = db.scalar(select(func.count(Notification.id)).where(Notification.type == "BLOCKER_CREATED"))
            assert count == 1
            assert db.scalar(select(func.count(NotificationDelivery.id)).join(Notification).where(
                Notification.type == "BLOCKER_CREATED")) == 1


def test_optional_preference_and_delivery_queue(tmp_path):
    app = setup_app(tmp_path)
    with TestClient(app) as admin:
        headers = login(admin)
        assert admin.put("/api/notifications/preferences", headers=headers,
                         json={"type": "NEW_ORDER", "channel": "IN_APP", "enabled": False}).status_code == 200
        assert admin.put("/api/notifications/preferences", headers=headers,
                         json={"type": "NEW_ORDER", "channel": "WEB_PUSH", "enabled": True}).status_code == 200
        with Session(app.state.engine) as db:
            assert emit(db, type="NEW_ORDER", event_key="order:100", user_ids=[1],
                        title="New", body="Order") == 1
            assert emit(db, type="NEW_ORDER", event_key="order:100", user_ids=[1],
                        title="New", body="Order") == 0
            db.commit()
            delivery = db.scalar(select(NotificationDelivery))
            assert delivery.channel == "WEB_PUSH" and delivery.status == "PENDING"
        assert len(admin.get("/api/notifications").json()["items"]) == 1


def test_resolved_blocker_and_deadline_reconciliation(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        db.add(BlockerType(code="OTHER", display_name="Other"))
        db.commit()
    with TestClient(app) as admin:
        headers = login(admin)
        order_id = admin.get("/api/orders?status=QUEUED").json()["items"][0]["id"]
        blocker = admin.post("/api/blockers", headers=headers, json={
            "order_id": order_id, "type_code": "OTHER", "description": "Деталь найдена"}).json()
        assert admin.patch(f"/api/blockers/{blocker['id']}", headers=headers,
                           json={"status": "RESOLVED"}).status_code == 200
        first = admin.get("/api/notifications").json()["items"]
        second = admin.get("/api/notifications").json()["items"]
        assert len(first) == len(second)
        assert len([n for n in first if n["type"] == "BLOCKER_RESOLVED"]) == 1
        assert any(n["type"] in ("SHIPMENT_DEADLINE", "ORDER_OVERDUE", "TARIFF_DEADLINE") for n in first)
