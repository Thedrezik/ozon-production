from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_orders import login, setup_app

from app.orders import seed_mock_orders
from app.tariff import evaluate, parse_normalized_steps

NOW = datetime(2026, 9, 30, 9, tzinfo=timezone.utc)


def steps(*costs):
    return parse_normalized_steps([
        {"starts_at": None if index == 0 else (NOW + timedelta(hours=index)).isoformat(),
         "tariff_type": "discount" if index == 0 else "surcharge",
         "rate_percent": str(index), "cost": cost, "currency": "RUB"}
        for index, cost in enumerate(costs)
    ])


def test_current_next_and_multiple_steps():
    timeline = steps("-120.00", "0.00", "350.00")
    before = evaluate(timeline, NOW)
    assert before["current_tariff_cost"] == Decimal("-120.00")
    assert before["next_tariff_cost"] == Decimal("0.00")
    assert before["delta_to_next_tariff"] == Decimal("120.00")
    assert len(before["timeline"]) == 3
    middle = evaluate(timeline, NOW + timedelta(hours=1))
    assert middle["current_tariff_cost"] == Decimal("0.00")
    assert middle["next_tariff_cost"] == Decimal("350.00")
    assert middle["delta_to_next_tariff"] == Decimal("350.00")
    assert evaluate(timeline, NOW + timedelta(hours=2))["next"] is None


def test_deadline_and_utc_timezone_boundary():
    timeline = steps("10.00", "20.00")
    moscow = timezone(timedelta(hours=3))
    assert evaluate(timeline, datetime(2026, 9, 30, 12, 59, 59, tzinfo=moscow))["current_tariff_cost"] == Decimal(10)
    at_boundary = evaluate(timeline, datetime(2026, 9, 30, 13, tzinfo=moscow))
    assert at_boundary["current_tariff_cost"] == Decimal(20)
    assert at_boundary["next"] is None
    assert at_boundary["current"]["starts_at"] == NOW + timedelta(hours=1)


def test_missing_money_and_currency_mismatch():
    timeline = parse_normalized_steps([
        {"starts_at": None, "tariff_type": "discount", "rate_percent": "-2"},
        {"starts_at": (NOW + timedelta(hours=1)).isoformat(), "tariff_type": "standard",
         "rate_percent": "0", "cost": "25.00", "currency": "RUB"},
    ])
    result = evaluate(timeline, NOW)
    assert result["next"]["rate_percent"] == Decimal(0)
    assert result["delta_to_next_tariff"] is None
    assert result["potential_saving"] is None
    assert result["potential_loss"] is None
    mixed = parse_normalized_steps([
        {"starts_at": None, "tariff_type": "a", "cost": "10", "currency": "RUB"},
        {"starts_at": (NOW + timedelta(hours=1)).isoformat(), "tariff_type": "b",
         "cost": "20", "currency": "USD"},
    ])
    assert evaluate(mixed, NOW)["delta_to_next_tariff"] is None


def test_positive_and_negative_financial_effect():
    increase = evaluate(steps("0.00", "15.25"), NOW)
    assert increase["delta_to_next_tariff"] == Decimal("15.25")
    assert increase["potential_saving"] == Decimal("15.25")
    assert increase["potential_loss"] == Decimal(0)
    decrease = evaluate(steps("10.00", "-5.50"), NOW)
    assert decrease["delta_to_next_tariff"] == Decimal("-15.50")
    assert decrease["potential_saving"] == Decimal(0)
    assert decrease["potential_loss"] == Decimal("15.50")


@pytest.mark.parametrize("payload", [
    [{"starts_at": None, "tariff_type": "a", "cost": 1.2, "currency": "RUB"}],
    [{"starts_at": None, "tariff_type": "a", "cost": "1"}],
    [{"starts_at": None, "tariff_type": "a"},
     {"starts_at": "2026-09-30T10:00:00", "tariff_type": "b"}],
])
def test_reject_unsafe_inputs(payload):
    with pytest.raises((TypeError, ValueError)):
        parse_normalized_steps(payload)
    with pytest.raises(ValueError):
        evaluate((), NOW.replace(tzinfo=None))


def test_mock_queue_tariff_permissions(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
    with TestClient(app) as client:
        headers = login(client)
        row = next(item for item in client.get("/api/orders").json()["items"]
                   if item["posting_number"] == "MOCK-NEAR-DEADLINE")
        assert row["tariff"]["delta_to_next_tariff"] == "120.00"
        assert len(row["tariff"]["timeline"]) == 3
        client.post("/api/users", headers=headers, json={"username": "viewer", "display_name": "Viewer",
                    "password": "viewer-password-123", "roles": ["VIEWER"]})
        with TestClient(app) as viewer:
            login(viewer, "viewer", "viewer-password-123")
            hidden = next(item for item in viewer.get("/api/orders").json()["items"]
                          if item["posting_number"] == "MOCK-NEAR-DEADLINE")
            assert hidden["tariff"]["delta_to_next_tariff"] is None
            assert all(step["cost"] is None for step in hidden["tariff"]["timeline"])
            assert hidden["tariff"]["next"]["rate_percent"] == "0"
