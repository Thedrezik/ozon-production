from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Blocker,
    BlockerType,
    ManagerTask,
    ProcurementHistory,
    ProcurementTask,
    utc_now,
)
from app.orders import seed_mock_orders
from tests.test_orders import login, setup_app


def test_order_deadline_can_be_round_tripped_to_procurement(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
    with TestClient(app) as client:
        headers = login(client)
        order = client.get("/api/orders?q=MOCK-NORMAL").json()["items"][0]
        assert order["shipment_deadline"].endswith(("Z", "+00:00"))
        response = client.post("/api/procurement", headers=headers, json={
            "material_name": "Synthetic edge", "quantity": "2", "unit": "m",
            "order_ids": [order["id"]], "needed_by": order["shipment_deadline"],
        })
        assert response.status_code == 201
        assert response.json()["order_ids"] == [order["id"]]


def test_procurement_links_history_permissions_and_overdue(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        db.add(BlockerType(code="OTHER", display_name="Другое"))
        db.commit()
    with TestClient(app) as admin:
        headers = login(admin)
        admin.post("/api/users", headers=headers, json={"username": "buyer", "display_name": "Buyer",
                   "password": "buyer-password-123", "roles": ["PURCHASER"]})
        admin.post("/api/users", headers=headers, json={"username": "viewer", "display_name": "Viewer",
                   "password": "viewer-password-123", "roles": ["VIEWER"]})
        orders = admin.get("/api/orders?limit=100").json()["items"]
        first, second = orders[0]["id"], orders[1]["id"]
        blocker = admin.post("/api/blockers", headers=headers, json={
            "order_id": first, "type_code": "OTHER", "description": "Нужна кромка", "severity": "HIGH"})
        assert blocker.status_code == 201
        buyer_id = next(row["id"] for row in admin.get("/api/users").json()["items"] if row["username"] == "buyer")
        payload = {"material_name": "Кромка 2 мм", "quantity": "2.5", "unit": "м",
                   "description": "Белая", "severity": "HIGH", "responsible_user_id": buyer_id,
                   "needed_by": (utc_now() - timedelta(minutes=1)).isoformat(),
                   "blocker_ids": [blocker.json()["id"]], "order_ids": [second]}
        with TestClient(app) as viewer:
            viewer_headers = login(viewer, "viewer", "viewer-password-123")
            assert viewer.get("/api/procurement").status_code == 403
            assert viewer.post("/api/procurement", headers=viewer_headers, json=payload).status_code == 403
        created = admin.post("/api/procurement", headers=headers, json=payload)
        assert created.status_code == 201, created.text
        task = created.json()
        assert set(task["order_ids"]) == {first, second}
        assert task["blocker_ids"] == [blocker.json()["id"]]
        assert task["is_overdue"]
        assert len(admin.get("/api/manager-tasks?source_type=PROCUREMENT_OVERDUE").json()["items"]) == 1
        with TestClient(app) as buyer:
            buyer_headers = login(buyer, "buyer", "buyer-password-123")
            assert buyer.get("/api/procurement?mine=true").json()["total"] == 1
            assert buyer.post(f'/api/procurement/{task["id"]}/links', headers=buyer_headers,
                              json={"order_ids": [first]}).status_code == 200
            assert buyer.patch(f'/api/procurement/{task["id"]}', headers=buyer_headers,
                               json={"status": "ORDERED"}).status_code == 200
            delivered = buyer.patch(f'/api/procurement/{task["id"]}', headers=buyer_headers,
                                    json={"status": "DELIVERED"})
            assert delivered.status_code == 200, delivered.text
            assert not delivered.json()["is_overdue"]
            assert len(buyer.get(f'/api/procurement/{task["id"]}/history').json()["items"]) == 3
            assert buyer.patch(f'/api/procurement/{task["id"]}', headers=buyer_headers,
                               json={"status": "CANCELLED"}).status_code == 409
        with Session(app.state.engine) as db:
            assert db.get(Blocker, blocker.json()["id"]).status == "OPEN"
            assert db.get(ProcurementTask, task["id"]).delivered_at is not None
            assert db.scalar(select(ManagerTask).where(ManagerTask.source_type == "PROCUREMENT_OVERDUE")).status == "RESOLVED"
            assert len(db.scalars(select(ProcurementHistory)).all()) == 3


def test_procurement_validation_and_late_overdue_discovery(tmp_path):
    app = setup_app(tmp_path)
    with TestClient(app) as admin:
        headers = login(admin)
        payload = {"material_name": "Фурнитура", "quantity": "1", "unit": "шт.", "severity": "CRITICAL"}
        assert admin.post("/api/procurement", headers=headers,
                          json={**payload, "blocker_ids": [999]}).status_code == 422
        assert admin.post("/api/procurement", headers=headers,
                          json={**payload, "needed_by": "2026-09-30T12:00:00"}).status_code == 422
        created = admin.post("/api/procurement", headers=headers, json=payload)
        assert created.status_code == 201
        with Session(app.state.engine) as db:
            db.get(ProcurementTask, created.json()["id"]).needed_by = utc_now() - timedelta(hours=1)
            db.commit()
        assert admin.get("/api/manager-tasks?source_type=PROCUREMENT_OVERDUE").json()["total"] == 1
        assert admin.get("/api/manager-tasks?source_type=PROCUREMENT_OVERDUE").json()["total"] == 1
