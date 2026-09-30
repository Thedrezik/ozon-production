from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.manager_tasks import SOURCE_TYPES, ensure_task, sync_rule
from app.models import AuditLog, BlockerType, ManagerTask, Order
from app.orders import seed_mock_orders
from tests.test_orders import login, setup_app


def test_rule_boundary_deduplicates_all_supported_sources(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        order_id = db.scalar(select(Order.id).limit(1))
        for source_type in SOURCE_TYPES:
            first = ensure_task(db, source_type=source_type, source_id=42, order_id=order_id,
                                title="Проверить", description="Причина", severity="HIGH")
            db.flush()
            again = ensure_task(db, source_type=source_type, source_id=42, order_id=order_id,
                                title="Проверить", description="Причина", severity="HIGH")
            assert first.id == again.id
        db.commit()
        assert len(db.scalars(select(ManagerTask)).all()) == len(SOURCE_TYPES)
        for _ in range(2):
            sync_rule(db, active=False, source_type="DEADLINE_RISK", source_id=42,
                      order_id=order_id, title="Проверить", description="Причина", severity="HIGH")
        db.commit()
        row = db.scalar(select(ManagerTask).where(ManagerTask.source_type == "DEADLINE_RISK"))
        assert row.status == "RESOLVED" and row.resolved_at is not None


def test_manager_task_filters_claim_and_blocker_resolution(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        db.add(BlockerType(code="OTHER", display_name="Другое"))
        db.commit()
    with TestClient(app) as admin:
        headers = login(admin)
        order_id = admin.get("/api/orders?status=QUEUED").json()["items"][0]["id"]
        response = admin.post("/api/blockers", headers=headers, json={
            "order_id": order_id, "type_code": "OTHER", "description": "Нет детали", "severity": "CRITICAL"})
        assert response.status_code == 201
        task = admin.get("/api/manager-tasks?severity=CRITICAL&source_type=BLOCKER&status=OPEN").json()
        assert task["total"] == 1
        task_id = task["items"][0]["id"]
        assert admin.get("/api/manager-tasks?severity=LOW").json()["total"] == 0
        assert admin.get("/api/manager-tasks?source_type=UNKNOWN").status_code == 422
        claim = admin.patch(f"/api/manager-tasks/{task_id}", headers=headers, json={"status": "IN_PROGRESS"})
        assert claim.status_code == 200
        assert claim.json()["assigned_to"] == admin.get("/api/auth/me").json()["id"]
        assert admin.get(f"/api/manager-tasks?status=IN_PROGRESS&assigned_to={claim.json()['assigned_to']}").json()["total"] == 1
        assert admin.patch(f"/api/manager-tasks/{task_id}", headers=headers,
                           json={"status": "RESOLVED"}).status_code == 409
        assert admin.patch("/api/blockers/1", headers=headers, json={"status": "RESOLVED"}).status_code == 200
        assert admin.get("/api/manager-tasks?status=RESOLVED").json()["total"] == 1
        with Session(app.state.engine) as db:
            assert db.scalar(select(AuditLog.id).where(AuditLog.action == "manager_task.updated"))
