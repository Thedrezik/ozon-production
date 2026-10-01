import copy
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    AuditLog,
    Blocker,
    BlockerType,
    Comment,
    InternalStatus,
    ManagerTask,
    Order,
    OrderItem,
    OrderTimelineEvent,
    OzonPostingData,
    StatusHistory,
    User,
)
from app.orders import STATUS_LABELS, STATUSES
from app.ozon import FBS_LIST_PATH, OzonResponseError
from app.ozon_import import Posting, import_fbs, upsert_posting
from tests.test_orders import login, setup_app
from tests.test_ozon import client_for

SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc)
TO = datetime(2026, 10, 4, tzinfo=timezone.utc)
WINDOW = {"since": SINCE.isoformat(), "to": TO.isoformat()}


@pytest.fixture
def page():
    return json.loads((Path(__file__).parents[1] / "app/fixtures/fbs_v4.json").read_text(encoding="utf-8"),
                      parse_float=Decimal)


@pytest.fixture
def app(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        for index, status in enumerate(STATUSES):
            db.add(InternalStatus(name=status, display_name=STATUS_LABELS[index], sort_order=index))
        db.commit()
    return app


def actor(db):
    return db.scalar(select(User.id))


def response(page):
    from app.ozon_import import diagnostic_json
    return httpx.Response(200, text=diagnostic_json(page))


def test_initial_http_import_and_repeat_are_idempotent(app, page):
    client, requests, _ = client_for([response(page), response(page)])
    with client, Session(app.state.engine) as db:
        result = import_fbs(db, client, SINCE, TO, is_mock=False, actor_id=actor(db))
        db.commit()
        assert result == {"received": 1, "changed": 1, "pages": 1}
        order = db.scalar(select(Order))
        assert order.internal_status == "NEW" and order.ozon_status == "awaiting_packaging"
        assert order.order_number == "0210000001-0001" and order.ozon_order_id == "33301885134"
        assert order.warehouse_id == "20605650762000" and order.warehouse_name == "Мебель FBS"
        assert order.shipment_deadline.replace(tzinfo=timezone.utc) == datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
        assert order.ozon_in_process_at and order.shipment_date_without_delay
        assert order.order_value == Decimal("19970.60")
        assert len(order.items) == 2
        assert order.items[1].quantity == 2 and order.items[1].sku == "1904686182"
        assert order.items[1].price == Decimal("3490.2500")
        assert order.items[1].currency == "RUB" and order.items[1].offer_id == "SHELF-OAK"
        snapshot = db.get(OzonPostingData, order.id)
        assert json.loads(snapshot.raw_json, parse_float=Decimal) == page["postings"][0]
        assert snapshot.tariffication_steps[0]["tariff_deadline_at"] == "2026-10-02T12:00:00Z"
        item_ids = [i.id for i in order.items]
        assert import_fbs(db, client, SINCE, TO, is_mock=False, actor_id=actor(db))["changed"] == 0
        db.commit()
        assert db.query(Order).count() == db.query(OzonPostingData).count() == db.query(StatusHistory).count() == 1
        assert db.query(OrderItem).count() == 2 and [i.id for i in order.items] == item_ids
        assert db.query(AuditLog).filter(AuditLog.action.like("ozon.%")).count() == 1
    body = json.loads(requests[0].content)
    assert requests[0].url.path == FBS_LIST_PATH
    assert body == {"filter": WINDOW, "sort_dir": "ASC", "cursor": "", "limit": 100,
                    "with": {"analytics_data": True, "financial_data": True}}


def test_update_preserves_all_production_data(app, page):
    raw = page["postings"][0]
    with Session(app.state.engine) as db:
        uid = actor(db)
        upsert_posting(db, raw, is_mock=False, actor_id=uid)
        order = db.scalar(select(Order))
        order.internal_status = "BLOCKED"
        order.priority_override = "P0"
        order.priority_pinned = True
        order.production_started_at = SINCE
        db.add(BlockerType(code="MATERIAL", display_name="Материал"))
        db.add(Assignment(order_id=order.id, user_id=uid, assigned_by=uid))
        db.add(Comment(order_id=order.id, author_user_id=uid, body="Кромка"))
        db.add(OrderTimelineEvent(order_id=order.id, event_type="comment", description="Кромка"))
        db.flush()
        db.add(Blocker(order_id=order.id, type_code="MATERIAL", description="Кромка", severity="HIGH", status="OPEN"))
        db.add(ManagerTask(order_id=order.id, source_type="BLOCKER", source_id=1, title="Кромка", description="Кромка", severity="HIGH", status="OPEN", assigned_to=uid))
        db.commit()
        original_id = order.id
        raw.update(status="cancelled", substatus="new_external_substatus", warehouse_name="injected",
                   internal_status="CANCELLED", priority_override=None, assignment=None)
        raw["products"][0]["price"]["amount"] = "13000.15"
        raw["products"].pop()
        raw["delivery_method"]["warehouse"] = "Новый склад"
        raw["shipment_date"] = "2026-10-03T15:00:00+03:00"
        assert upsert_posting(db, raw, is_mock=False, actor_id=uid)
        db.commit()
        assert order.id == original_id and order.internal_status == "BLOCKED"
        assert order.ozon_status == "cancelled" and order.ozon_substatus == "new_external_substatus"
        assert order.warehouse_name == "Новый склад"
        assert order.priority_override == "P0" and order.priority_pinned
        assert order.production_started_at.replace(tzinfo=timezone.utc) == SINCE
        assert order.assignment.user_id == uid
        assert len(order.items) == 1 and order.items[0].price == Decimal("13000.1500")
        assert order.shipment_deadline.hour == 12
        for model in (Order, Assignment, Blocker, Comment, ManagerTask, StatusHistory):
            assert db.query(model).count() == 1
        assert db.query(OrderTimelineEvent).count() == 2


def test_unknown_fields_and_incomplete_optional_data(app, page):
    raw = page["postings"][0]
    for key in ("substatus", "order_id", "order_number", "delivery_method", "in_process_at", "delivering_date",
                "shipment_date_without_delay", "financial_data", "tariffication", "tariffication_steps"):
        raw.pop(key)
    raw["future_field"] = {"new": [1, "yes"]}
    for item in raw["products"]:
        item.pop("price")
        item.pop("sku")
        item.pop("offer_id")
    with Session(app.state.engine) as db:
        upsert_posting(db, raw, is_mock=False, actor_id=actor(db))
        db.commit()
        order = db.scalar(select(Order))
        assert order.order_value is None and order.ozon_order_id is None and order.warehouse_id is None
        assert order.items[0].price is None
        assert json.loads(db.get(OzonPostingData, order.id).raw_json)["future_field"] == raw["future_field"]


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1", "not-money", True, 0.1])
def test_invalid_money_rejected(page, amount):
    page["postings"][0]["products"][0]["price"]["amount"] = amount
    with pytest.raises((ValidationError, TypeError)):
        Posting.model_validate(page["postings"][0])


def test_decimal_numeric_token_and_non_rub_total(app, page):
    page["postings"][0]["products"][0]["price"] = {"amount": Decimal("0.1001"), "currency": "USD"}
    client, _, _ = client_for([response(page)])
    with client, Session(app.state.engine) as db:
        import_fbs(db, client, SINCE, TO, is_mock=False, actor_id=actor(db))
        db.commit()
        order = db.scalar(select(Order))
        assert order.items[0].price == Decimal("0.1001") and order.order_value is None
        assert json.loads(db.get(OzonPostingData, order.id).raw_json, parse_float=Decimal) == page["postings"][0]


def test_empty_products_do_not_invent_order_value(app, page):
    raw = page["postings"][0]
    raw["products"] = []
    with Session(app.state.engine) as db:
        upsert_posting(db, raw, is_mock=False, actor_id=actor(db))
        db.commit()
        order = db.scalar(select(Order))
        assert order.items == [] and order.order_value is None


def test_rounded_total_outside_existing_numeric_range_stays_unknown(app, page):
    raw = page["postings"][0]
    raw["products"] = [raw["products"][0]]
    raw["products"][0]["price"]["amount"] = "9999999999.995"
    with Session(app.state.engine) as db:
        upsert_posting(db, raw, is_mock=False, actor_id=actor(db))
        db.commit()
        order = db.scalar(select(Order))
        assert order.order_value is None
        assert order.items[0].price == Decimal("9999999999.9950")


def test_cursor_pagination_and_duplicate_across_pages(app, page):
    first = copy.deepcopy(page)
    first.update(has_next=True, cursor="page-2")
    client, requests, _ = client_for([response(first), response(page)])
    with client, Session(app.state.engine) as db:
        assert import_fbs(db, client, SINCE, TO, is_mock=False, actor_id=actor(db)) == {"received": 2, "changed": 1, "pages": 2}
        db.commit()
        assert db.query(Order).count() == 1
    assert json.loads(requests[1].content)["cursor"] == "page-2"


def test_cursor_loop_rejected(app, page):
    page.update(has_next=True, cursor="same")
    client, _, _ = client_for([response(page), response(page)])
    with client, Session(app.state.engine) as db:
        with pytest.raises(OzonResponseError):
            import_fbs(db, client, SINCE, TO, is_mock=False, actor_id=actor(db))
        db.rollback()
        assert db.query(Order).count() == 0


def test_api_mock_permissions_csrf_and_validation(app):
    with TestClient(app) as client:
        assert client.post("/api/ozon/fbs/import", json=WINDOW).status_code == 401
        headers = login(client)
        assert client.post("/api/ozon/fbs/import", json=WINDOW).status_code == 403
        assert client.post("/api/ozon/fbs/import", json={**WINDOW, "to": "2028-01-01T00:00:00Z"}, headers=headers).status_code == 422
        assert client.post("/api/ozon/fbs/import", json=WINDOW, headers=headers).json()["changed"] == 1
        assert client.post("/api/ozon/fbs/import", json=WINDOW, headers=headers).json()["changed"] == 0
        assert client.get("/api/health").status_code == client.get("/api/health/ready").status_code == 200
        client.post("/api/users", headers=headers, json={"username": "worker", "display_name": "Worker", "password": "worker-password-123", "roles": ["PRODUCTION_WORKER"]})
        headers = login(client, "worker", "worker-password-123")
        assert client.post("/api/ozon/fbs/import", json=WINDOW, headers=headers).status_code == 403


def test_api_rolls_back_earlier_pages_on_bad_payload(app, page):
    page.update(has_next=True, cursor="next")
    bad = copy.deepcopy(page)
    bad["postings"][0]["posting_number"] = "different"
    bad["postings"][0]["products"][0]["price"]["amount"] = "invalid"
    ozon, _, _ = client_for([response(page), response(bad)])
    with TestClient(app) as client, ozon:
        app.state.ozon_client = ozon
        headers = login(client)
        result = client.post("/api/ozon/fbs/import", json=WINDOW, headers=headers)
        assert result.status_code == 502 and result.json() == {"detail": "Invalid Ozon FBS payload"}
    with Session(app.state.engine) as db:
        assert db.query(Order).count() == db.query(OzonPostingData).count() == 0


def test_mock_real_collision_is_rejected(app, page):
    with Session(app.state.engine) as db:
        upsert_posting(db, page["postings"][0], is_mock=True, actor_id=actor(db))
        db.commit()
        with pytest.raises(ValueError, match="mock and real"):
            upsert_posting(db, page["postings"][0], is_mock=False, actor_id=actor(db))
        db.rollback()
        assert db.query(Order).count() == 1


def test_first_sync_of_existing_production_order_preserves_history(app, page):
    with Session(app.state.engine) as db:
        uid = actor(db)
        order = Order(posting_number=page["postings"][0]["posting_number"], ozon_status="awaiting_packaging",
                      internal_status="IN_PRODUCTION", shipment_deadline=TO, is_mock=False,
                      priority_override="P1", priority_pinned=True)
        db.add(order)
        db.flush()
        original_id = order.id
        db.add(Assignment(order_id=order.id, user_id=uid))
        db.add(StatusHistory(order_id=order.id, old_status="QUEUED", new_status="IN_PRODUCTION", changed_by=uid))
        db.commit()
        assert upsert_posting(db, page["postings"][0], is_mock=False, actor_id=uid)
        db.commit()
        assert order.id == original_id and order.internal_status == "IN_PRODUCTION"
        assert order.priority_override == "P1" and order.priority_pinned
        assert order.assignment.user_id == uid
        assert db.query(StatusHistory).count() == db.query(Order).count() == 1
        assert db.query(AuditLog).filter_by(action="ozon.posting.updated").count() == 1


def test_fbs_retry_uses_shared_http_policy(app, page):
    client, requests, clock = client_for([httpx.Response(429, headers={"Retry-After": "2"}), response(page)])
    with client, Session(app.state.engine) as db:
        assert import_fbs(db, client, SINCE, TO, is_mock=False, actor_id=actor(db))["changed"] == 1
    assert len(requests) == 2 and all(r.url.path == FBS_LIST_PATH for r in requests)
    assert clock.waits == [2]


@pytest.mark.parametrize("body", [{"result": {"postings": [], "has_next": False}},
                                  {"postings": [], "has_next": "false"}, []])
def test_old_or_malformed_fbs_envelope_rejected(body):
    client, requests, _ = client_for([httpx.Response(200, json=body)])
    with client, pytest.raises(OzonResponseError):
        client.list_fbs(SINCE, TO)
    assert len(requests) == 1
