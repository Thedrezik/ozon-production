from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Blocker, BlockerType, Order
from app.orders import seed_mock_orders
from tests.test_orders import login, setup_app


def test_blocker_lifecycle_and_permissions(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        for code in ("OTHER", "DEFECT"):
            db.add(BlockerType(code=code, display_name=code))
        db.commit()
    with TestClient(app) as admin:
        headers = login(admin)
        admin.post("/api/users", headers=headers, json={"username": "worker", "display_name": "Worker",
                    "password": "worker-password-123", "roles": ["PRODUCTION_WORKER"]})
        admin.post("/api/users", headers=headers, json={"username": "viewer", "display_name": "Viewer",
                    "password": "viewer-password-123", "roles": ["VIEWER"]})
        order_id = admin.get("/api/orders?status=QUEUED").json()["items"][0]["id"]
        with TestClient(app) as worker:
            worker_headers = login(worker, "worker", "worker-password-123")
            payload = {"order_id": order_id, "type_code": "OTHER", "description": "Нет детали"}
            assert worker.post("/api/blockers", headers=worker_headers, json=payload).status_code == 201
            assert worker.post("/api/blockers", headers=worker_headers, json=payload).status_code == 201
            assert worker.patch("/api/blockers/1", headers=worker_headers,
                                json={"status": "RESOLVED"}).status_code == 403
        with TestClient(app) as viewer:
            viewer_headers = login(viewer, "viewer", "viewer-password-123")
            assert viewer.get(f"/api/blockers?order_id={order_id}").status_code == 200
            assert viewer.post("/api/blockers", headers=viewer_headers, json=payload).status_code == 403
            assert viewer.get("/api/manager-tasks").status_code == 403
        assert len(admin.get("/api/manager-tasks").json()["items"]) == 2
        assert admin.get("/api/orders?blocked=true").json()["total"] == 2
        assert admin.post(f"/api/orders/{order_id}/status", headers=headers,
                          json={"status": "IN_PRODUCTION"}).status_code == 409
        assert admin.patch("/api/blockers/1", headers=headers, json={"status": "IN_PROGRESS"}).status_code == 200
        assert admin.patch("/api/blockers/1", headers=headers, json={"status": "RESOLVED"}).status_code == 200
        assert admin.get("/api/orders?status=BLOCKED").json()["total"] == 2
        assert admin.patch("/api/blockers/2", headers=headers, json={"status": "RESOLVED"}).status_code == 200
        assert admin.get("/api/manager-tasks?status=OPEN").json()["items"] == []
        with Session(app.state.engine) as db:
            assert db.get(Order, order_id).internal_status == "QUEUED"
            assert len(db.scalars(select(Blocker).where(Blocker.order_id == order_id)).all()) == 2
            assert db.scalar(select(AuditLog.id).where(AuditLog.action == "blocker.created"))
        timeline = admin.get(f"/api/orders/{order_id}/timeline").json()["items"]
        assert sum(item.get("event_type") == "blocker_created" for item in timeline) == 2
