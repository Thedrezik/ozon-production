from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_orders import login, setup_app

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
            assert worker.get("/api/dashboard").status_code == 403
