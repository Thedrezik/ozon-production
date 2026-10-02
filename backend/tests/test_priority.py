from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_orders import login, setup_app

from app.models import AuditLog, Order, Permission, ProductProductionProfile, Role
from app.orders import seed_mock_orders
from app.priority import PriorityInput, PriorityWeights, evaluate, sort_key

NOW = datetime(2026, 9, 30, 9, tzinfo=timezone.utc)


def scenario(hours, **kwargs):
    return PriorityInput(shipment_deadline=NOW + timedelta(hours=hours),
                         internal_status="QUEUED", remaining_minutes=45, **kwargs)


def test_ordinary_urgent_and_deterministic():
    normal = evaluate(scenario(48), NOW)
    urgent = evaluate(scenario(1), NOW)
    assert normal == evaluate(scenario(48), NOW)
    assert urgent["level"] < normal["level"]
    assert sort_key(urgent, 2) < sort_key(normal, 1)
    assert urgent["feasible"] is True
    assert any("45 мин" in reason for reason in urgent["reasons"])


def test_financial_effect_and_tariff_deadline():
    low = evaluate(scenario(12, tariff_deadline=NOW + timedelta(hours=2), tariff_impact=Decimal(100)), NOW)
    high = evaluate(scenario(12, tariff_deadline=NOW + timedelta(hours=2), tariff_impact=Decimal(2500)), NOW)
    assert high["score"] > low["score"]
    assert high["financial_impact"] == Decimal(2500)
    assert any("2500.00 ₽" in reason for reason in high["reasons"])
    unknown = evaluate(scenario(12, tariff_deadline=NOW + timedelta(hours=2), order_value=Decimal(50000)), NOW)
    assert unknown["financial_impact"] is None
    assert any("неизвестен" in reason for reason in unknown["reasons"])


def test_blocked_infeasible_and_override():
    blocked = evaluate(scenario(1, blocked=True), NOW)
    assert blocked["blocked"] and blocked["feasible"] is False
    assert blocked["level"] in ("P0", "P1")
    impossible = evaluate(PriorityInput(shipment_deadline=NOW + timedelta(hours=1),
                                        internal_status="QUEUED", remaining_minutes=120), NOW)
    assert impossible["feasible"] is False
    assert any("не хватает 60 мин" in reason for reason in impossible["reasons"])
    overridden = evaluate(scenario(48, override="P0", pinned=True), NOW)
    assert overridden["level"] == "P0" and overridden["pinned"]
    assert "Ручной приоритет" in overridden["reasons"][1]


def test_close_deadlines_stable_order_and_weights():
    a = evaluate(scenario(3), NOW)
    b = evaluate(scenario(4), NOW)
    assert sort_key(a, 5) < sort_key(b, 4)
    assert sort_key(a, 4) < sort_key(a, 5)
    heavy_finance = PriorityWeights(20, 20, 50, 10, Decimal(100))
    risky = evaluate(scenario(24, tariff_deadline=NOW + timedelta(hours=12),
                              tariff_impact=Decimal(100)), NOW, heavy_finance)
    plain = evaluate(scenario(24), NOW, heavy_finance)
    assert risky["score"] > plain["score"]


def test_queue_priority_override_settings_and_permissions(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        order = db.scalar(select(Order).where(Order.posting_number == "MOCK-URGENT"))
        order.items[0].offer_id = "URGENT-OFFER"
        db.add(ProductProductionProfile(offer_id="URGENT-OFFER", product_name="Шкаф", production_minutes=180,
                                        packing_minutes=30, complexity="HIGH"))
        db.commit()
        order_id = order.id
    with TestClient(app) as client:
        headers = login(client)
        queue = client.get("/api/orders").json()
        urgent = next(row for row in queue["items"] if row["id"] == order_id)
        assert urgent["priority"]["remaining_minutes"] == 210
        assert urgent["priority"]["feasible"] is False
        assert client.put(f"/api/orders/{order_id}/priority", json={"level": "P0", "pinned": True},
                          headers=headers).status_code == 200
        assert client.get("/api/orders").json()["items"][0]["id"] == order_id
        bad = {"deadline_weight": 40, "tariff_weight": 25, "finance_weight": 20,
               "feasibility_weight": 14, "high_impact_rub": "1000", "high_value_rub": "10000"}
        assert client.put("/api/orders/priority-settings", json=bad, headers=headers).status_code == 422
        bad["feasibility_weight"] = 15
        assert client.put("/api/orders/priority-settings", json=bad, headers=headers).status_code == 200
        client.post("/api/users", headers=headers, json={"username": "viewer", "display_name": "Viewer",
                        "password": "viewer-password-123", "roles": ["VIEWER"]})
        with TestClient(app) as viewer:
            viewer_headers = login(viewer, "viewer", "viewer-password-123")
            tariff_mock = next(row for row in viewer.get("/api/orders").json()["items"]
                               if row["posting_number"] == "MOCK-NEAR-DEADLINE")
            assert tariff_mock["priority"]["financial_impact"] is None
            assert all("₽" not in reason for reason in tariff_mock["priority"]["reasons"])
            assert viewer.put(f"/api/orders/{order_id}/priority", json={"level": "P1"},
                              headers=viewer_headers).status_code == 403
            assert viewer.put("/api/orders/priority-settings", json=bad, headers=viewer_headers).status_code == 403
    with Session(app.state.engine) as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "order.priority_changed"))
        assert db.scalar(select(AuditLog).where(AuditLog.action == "priority.settings_changed"))


def test_p4_queue_filter_and_priority_response_finance_permission(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        order_id = db.scalar(select(Order.id).where(Order.posting_number == "MOCK-NEAR-DEADLINE"))
        role = db.scalar(select(Role).where(Role.name == "VIEWER"))
        role.permissions.append(db.scalar(select(Permission).where(Permission.name == "orders.change_priority")))
        db.commit()
    with TestClient(app) as admin:
        headers = login(admin)
        admin.post("/api/users", headers=headers, json={"username": "dispatcher", "display_name": "Dispatcher",
                   "password": "dispatcher-password-123", "roles": ["VIEWER"]})
        with TestClient(app) as dispatcher:
            limited_headers = login(dispatcher, "dispatcher", "dispatcher-password-123")
            response = dispatcher.put(f"/api/orders/{order_id}/priority", headers=limited_headers,
                                      json={"level": "P4", "pinned": False})
            assert response.status_code == 200
            assert response.json()["priority"]["financial_impact"] is None
            assert all("₽" not in reason for reason in response.json()["priority"]["reasons"])
            filtered = dispatcher.get("/api/orders?priority_level=P4")
            assert filtered.status_code == 200
            assert order_id in {row["id"] for row in filtered.json()["items"]}
            assert all(row["priority"]["level"] == "P4" for row in filtered.json()["items"])
        response = admin.put(f"/api/orders/{order_id}/priority", headers=headers,
                             json={"level": "P1", "pinned": False})
        assert response.json()["priority"]["financial_impact"] is not None
