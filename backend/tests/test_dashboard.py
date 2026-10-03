from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_orders import login, setup_app

from app.models import Assignment, Order
from app.orders import seed_mock_orders


def test_manager_dashboard_matches_drill_downs_and_permissions(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
    with TestClient(app) as client:
        headers = login(client)
        data = client.get("/api/dashboard").json()
        assert data["blocked"] == client.get("/api/orders?blocked=true").json()["total"]
        assert data["ready"] == client.get("/api/orders?ready=true").json()["total"]
        assert data["overdue"] == client.get("/api/orders?overdue=true").json()["total"]
        assert data["critical"] == client.get("/api/orders?priority_level=P0").json()["total"]
        assert data["money_at_risk"]["total"] == client.get("/api/money-at-risk").json()["total"]
        assert client.get("/api/orders?priority_level=INVALID").status_code == 422
        client.post("/api/users", headers=headers, json={"username": "worker", "display_name": "Worker",
                                                        "password": "worker-password-123", "roles": ["PRODUCTION_WORKER"]})
        with TestClient(app) as worker:
            login(worker, "worker", "worker-password-123")
            response = worker.get("/api/dashboard")
            assert response.status_code == 200
            assert "money_at_risk" not in response.json()


def test_focus_projection_tracks_work_and_protects_finance(tmp_path):
    from test_core_workflow import setup

    app = setup(tmp_path)
    with Session(app.state.engine) as db:
        orders = db.scalars(select(Order)).all()
        focus = next(order for order in orders if order.posting_number == "MOCK-NEAR-DEADLINE")
        focus_id = focus.id
        for order in orders:
            if order.id != focus_id:
                order.internal_status = "DONE"
        db.add(Assignment(order_id=focus_id, user_id=1))
        db.commit()
    with TestClient(app) as client:
        headers = login(client)
        focus = client.get("/api/dashboard").json()["attention"][0]
        assert focus["id"] == focus_id
        assert focus["items"][0]["product_name"] == "Стол письменный"
        assert focus["items"][0]["quantity"] == 2
        assert focus["assigned_user"] == {"id": 1, "display_name": "Admin"}
        assert focus["money_at_risk"] == "470.00"
        assert focus["problems"] == []
        response = client.post("/api/blockers", headers=headers,
                               json={"order_id": focus_id, "description": "Нет кромки"})
        assert response.status_code == 201
        blocker_id = response.json()["id"]
        focus = client.get("/api/dashboard").json()["attention"][0]
        assert focus["internal_status"] == "BLOCKED"
        assert focus["problems"] == ["Нет кромки"]
        assert focus["money_at_risk"] == "470.00"
        client.post("/api/users", headers=headers, json={"username": "worker", "display_name": "Worker",
                    "password": "worker-password-123", "roles": ["PRODUCTION_WORKER"]})
        with TestClient(app) as worker:
            login(worker, "worker", "worker-password-123")
            focus = worker.get("/api/dashboard").json()["attention"][0]
            assert "money_at_risk" not in focus
            assert focus["financial_delta"] is None
            assert focus["problems"] == ["Нет кромки"]
        assert client.patch(f"/api/blockers/{blocker_id}", headers=headers,
                            json={"status": "RESOLVED"}).status_code == 200
        assert client.get("/api/dashboard").json()["attention"][0]["problems"] == []
        with Session(app.state.engine) as db:
            db.get(Order, focus_id).tariff_steps = None
            db.commit()
        assert client.get("/api/dashboard").json()["attention"][0]["money_at_risk"] is None
        with Session(app.state.engine) as db:
            db.get(Order, focus_id).ozon_status = "cancelled"
            db.commit()
        assert client.get("/api/dashboard").json()["attention"] == []
