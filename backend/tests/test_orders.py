import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import create_admin
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import Assignment, Order, StatusHistory, User
from app.order_events import OrderEvents
from app.orders import seed_mock_orders
from app.rbac import seed_rbac


def setup_app(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'orders.db'}"))
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as db:
        seed_rbac(db)
        db.commit()
        create_admin("admin", "Admin", "admin-password-123", db)
    return app


def login(client, username="admin", password="admin-password-123"):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_mock_seed_is_idempotent_and_statuses_are_separate(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        assert seed_mock_orders(db) == 7
        assert seed_mock_orders(db) == 0
        orders = db.scalars(select(Order)).all()
        assert len(orders) == 7
        assert {o.internal_status for o in orders} >= {"BLOCKED", "CANCELLED", "READY_TO_SHIP"}
        assert all(o.ozon_status != o.internal_status for o in orders)
        assert db.query(StatusHistory).count() == 7


def test_queue_filters_assignment_permissions_and_history(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
    with TestClient(app) as admin:
        headers = login(admin)
        response = admin.post("/api/users", headers=headers, json={"username": "worker", "display_name": "Worker", "password": "worker-password-123", "roles": ["PRODUCTION_WORKER"]})
        worker_id = response.json()["id"]
        response = admin.post("/api/users", headers=headers, json={"username": "viewer", "display_name": "Viewer", "password": "viewer-password-123", "roles": ["VIEWER"]})
        assert response.status_code == 201
        queue = admin.get("/api/orders?limit=2").json()
        assert queue["total"] == 7 and len(queue["items"]) == 2
        assert admin.get("/api/orders?blocked=true").json()["total"] == 1
        assert admin.get("/api/orders?ready=true").json()["total"] == 1
        assert admin.get("/api/orders?overdue=true").json()["total"] == 1
        assert admin.get("/api/orders?status=INVALID").status_code == 422
        order = admin.get("/api/orders?status=QUEUED").json()["items"][0]
        order_id = order["id"]
        assert admin.put(f"/api/orders/{order_id}/assignment", headers=headers, json={"user_id": worker_id}).status_code == 200
        assert admin.get(f"/api/orders?assigned_user_id={worker_id}").json()["total"] == 1
        assert admin.put(f"/api/orders/{order_id}/assignment", headers=headers, json={"user_id": None}).status_code == 200
        with TestClient(app) as worker:
            worker_headers = login(worker, "worker", "worker-password-123")
            assert worker.post(f"/api/orders/{order_id}/claim").status_code == 403
            assert worker.post(f"/api/orders/{order_id}/claim", headers=worker_headers).status_code == 200
            assert worker.post(f"/api/orders/{order_id}/claim", headers=worker_headers).status_code == 409
            assert worker.put(f"/api/orders/{order_id}/assignment", headers=worker_headers, json={"user_id": None}).status_code == 403
            assert worker.post(f"/api/orders/{order_id}/status", headers=worker_headers, json={"status": "READY_TO_SHIP"}).status_code == 409
            assert worker.post(f"/api/orders/{order_id}/status", headers=worker_headers, json={"status": "IN_PRODUCTION"}).status_code == 200
            assert worker.post(f"/api/orders/{order_id}/status", headers=worker_headers, json={"status": "PRODUCED"}).status_code == 200
            assert worker.post(f"/api/orders/{order_id}/status", headers=worker_headers, json={"status": "PACKING"}).status_code == 200
            assert worker.post(f"/api/orders/{order_id}/status", headers=worker_headers, json={"status": "READY_TO_SHIP"}).status_code == 200
            history = worker.get(f"/api/orders/{order_id}/history").json()
            assert [row["new_status"] for row in history][-4:] == ["IN_PRODUCTION", "PRODUCED", "PACKING", "READY_TO_SHIP"]
            assert all(row["changed_by"] == worker_id for row in history[-4:])
        with TestClient(app) as viewer:
            viewer_headers = login(viewer, "viewer", "viewer-password-123")
            assert viewer.get("/api/orders").status_code == 200
            assert viewer.post(f"/api/orders/{order_id}/claim", headers=viewer_headers).status_code == 403
        with Session(app.state.engine) as db:
            assert db.scalar(select(Assignment.user_id).where(Assignment.order_id == order_id)) == worker_id
            assert db.scalar(select(User.id).where(User.username == "worker")) == worker_id



def test_realtime_event_bus_broadcasts_and_unsubscribes():
    async def scenario():
        bus = OrderEvents()
        first, second = bus.subscribe(), bus.subscribe()
        bus.publish(42)
        assert await asyncio.wait_for(first.get(), 1) == 42
        assert await asyncio.wait_for(second.get(), 1) == 42
        bus.unsubscribe(first)
        bus.unsubscribe(second)

    asyncio.run(scenario())
