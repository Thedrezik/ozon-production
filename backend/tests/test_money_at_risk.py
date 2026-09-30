from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_orders import login, setup_app

from app.models import Order
from app.money_at_risk import aggregate, bucket_boundaries
from app.orders import seed_mock_orders
from app.tariff import parse_normalized_steps

NOW = datetime(2026, 9, 30, 8, tzinfo=timezone.utc)  # 11:00 in Moscow


def row(number, costs, hours, *, blocked=False, feasible=True, level="P2", status="QUEUED"):
    steps = parse_normalized_steps([
        {"starts_at": None if index == 0 else (NOW + timedelta(hours=hours[index - 1])).isoformat(),
         "tariff_type": "step", "cost": cost, "currency": "RUB"}
        for index, cost in enumerate(costs)
    ])
    return ({"id": number, "posting_number": f"MOCK-{number}", "internal_status": status}, steps,
            {"blocked": blocked, "feasible": feasible, "level": level})


def test_multiple_orders_same_bucket_and_correct_total():
    result = aggregate([row(1, ["0", "100"], [0.5]), row(2, ["10", "35"], [0.75])], NOW,
                       "Europe/Moscow")
    first = result["buckets"][0]
    assert first["amount"] == Decimal(125)
    assert first["order_count"] == 2
    assert {item["posting_number"] for item in first["orders"]} == {"MOCK-1", "MOCK-2"}
    assert result["total"] == sum((bucket["amount"] for bucket in result["buckets"]), Decimal(0))


def test_multiple_future_steps_count_only_new_high_water_mark():
    result = aggregate([row(1, ["0", "100", "80", "150"], [0.5, 2, 5])], NOW,
                       "Europe/Moscow", near_hours=1)
    assert result["total"] == Decimal(150)
    assert sum((item["amount"] for bucket in result["buckets"]
                for item in bucket["orders"]), Decimal(0)) == Decimal(150)
    assert sum(bucket["order_count"] for bucket in result["buckets"]) == 2


def test_blocked_high_risk_already_degraded_and_unknown_money():
    previous = parse_normalized_steps([
        {"starts_at": None, "tariff_type": "a", "cost": "0", "currency": "RUB"},
        {"starts_at": (NOW - timedelta(hours=1)).isoformat(), "tariff_type": "b",
         "cost": "40", "currency": "RUB"},
        {"starts_at": (NOW + timedelta(hours=1)).isoformat(), "tariff_type": "c",
         "cost": "75", "currency": "RUB"},
    ])
    missing = parse_normalized_steps([
        {"starts_at": None, "tariff_type": "a", "rate_percent": "2"},
        {"starts_at": (NOW + timedelta(hours=1)).isoformat(), "tariff_type": "b", "rate_percent": "5"},
    ])
    rows = [row(1, ["0", "20"], [1], blocked=True),
            row(2, ["0", "30"], [1], feasible=False),
            ({"id": 3, "posting_number": "MOCK-3", "internal_status": "QUEUED"}, previous,
             {"blocked": False, "feasible": True, "level": "P2"}),
            ({"id": 4, "posting_number": "MOCK-4", "internal_status": "QUEUED"}, missing,
             {"blocked": False, "feasible": True, "level": "P2"})]
    result = aggregate(rows, NOW, "Europe/Moscow")
    assert result["categories"]["BLOCKED_RISK"] == Decimal(20)
    assert result["categories"]["HIGH_RISK"] == Decimal(30)
    assert result["categories"]["CAN_STILL_SAVE"] == Decimal(35)
    assert result["categories"]["ALREADY_DEGRADED"] == Decimal(40)
    assert result["already_degraded"]["order_count"] == 1
    assert result["total"] == Decimal(85)
    assert result["unpriced_count"] >= 1


def test_local_day_boundary_and_configurable_cutoffs():
    boundaries = bucket_boundaries(NOW, "Europe/Moscow", 1, (12, 16))
    assert boundaries[0]["ends_at"] == datetime(2026, 9, 30, 9, tzinfo=timezone.utc)
    assert boundaries[-1]["key"] == "tomorrow"
    assert boundaries[-1]["ends_at"] == datetime(2026, 10, 1, 21, tzinfo=timezone.utc)
    just_before_midnight = datetime(2026, 9, 30, 20, 59, 59, tzinfo=timezone.utc)
    boundaries = bucket_boundaries(just_before_midnight, "Europe/Moscow", 1, (12, 16))
    assert boundaries[0]["key"] == "today"
    assert boundaries[0]["ends_at"] == datetime(2026, 9, 30, 21, tzinfo=timezone.utc)
    assert bucket_boundaries(NOW, "Europe/Moscow", 1, (14,))[1]["key"] == "by_14"


def test_unknown_intermediate_cost_stops_future_money_and_unknown_feasibility_is_high_risk():
    steps = parse_normalized_steps([
        {"starts_at": None, "tariff_type": "a", "cost": "0", "currency": "RUB"},
        {"starts_at": (NOW + timedelta(hours=1)).isoformat(), "tariff_type": "b"},
        {"starts_at": (NOW + timedelta(hours=2)).isoformat(), "tariff_type": "c",
         "cost": "100", "currency": "RUB"},
    ])
    result = aggregate([({"id": 1, "posting_number": "MOCK-1", "internal_status": "QUEUED"}, steps,
                         {"blocked": False, "feasible": None, "level": "P2"})], NOW, "Europe/Moscow")
    assert result["total"] == Decimal(0)
    assert result["unpriced_count"] == 1
    known = aggregate([row(1, ["0", "10"], [1], feasible=None)], NOW, "Europe/Moscow")
    assert known["categories"]["HIGH_RISK"] == Decimal(10)


def test_finance_permission_and_drilldown_on_mock_data(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        order = db.scalar(select(Order).where(Order.posting_number == "MOCK-NEAR-DEADLINE"))
        assert order is not None
        order.tariff_steps = [
            {"starts_at": None, "tariff_type": "a", "cost": "0", "currency": "RUB"},
            {"starts_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
             "tariff_type": "b", "cost": "120", "currency": "RUB"},
        ]
        db.commit()
    with TestClient(app) as client:
        headers = login(client)
        summary = client.get("/api/money-at-risk")
        assert summary.status_code == 200
        data = summary.json()
        assert Decimal(data["total"]) >= Decimal(120)
        first = next(bucket for bucket in data["buckets"] if bucket["order_count"])
        detail = client.get(f"/api/money-at-risk/orders?bucket={first['key']}").json()
        assert detail["total"] == first["order_count"]
        assert Decimal(detail["amount"]) == Decimal(first["amount"])
        assert any(item["posting_number"] == "MOCK-NEAR-DEADLINE" for item in detail["items"])
        client.post("/api/users", headers=headers, json={"username": "viewer", "display_name": "Viewer",
                    "password": "viewer-password-123", "roles": ["VIEWER"]})
        with TestClient(app) as viewer:
            login(viewer, "viewer", "viewer-password-123")
            assert viewer.get("/api/money-at-risk").status_code == 403
            assert viewer.get(f"/api/money-at-risk/orders?bucket={first['key']}").status_code == 403
