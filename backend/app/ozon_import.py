"""Explicit, transactional FBS import. Updates only the external field allowlist."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Order,
    OrderItem,
    OzonPostingData,
    StatusHistory,
    utc_now,
)
from app.ozon import OzonClientInterface, OzonResponseError

# One API process: serialize upstream snapshots and their writes across push,
# reconciliation and explicit import, so a fetched list cannot undo a newer push.
posting_sync_lock = RLock()


def validate_window(since: datetime, to: datetime) -> None:
    if since.tzinfo is None or to.tzinfo is None or not since < to or to - since > timedelta(days=365):
        raise ValueError("Use timezone-aware dates and a positive window of at most 365 days")


def diagnostic_json(value) -> str:
    """Canonical JSON preserving decimal number tokens, including unknown fields."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite JSON number")
        return str(value)
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k) + ":" + diagnostic_json(v)
                              for k, v in sorted(value.items())) + "}"
    if isinstance(value, list):
        return "[" + ",".join(diagnostic_json(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class ExternalModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Money(ExternalModel):
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=4, allow_inf_nan=False)
    currency: str = Field(min_length=1, max_length=10)

    @field_validator("amount", mode="before")
    @classmethod
    def exact_money(cls, value):
        if isinstance(value, (float, bool)):
            raise TypeError("Money must be decoded using Decimal")
        return value


class Product(ExternalModel):
    name: str = Field(min_length=1, max_length=240)
    sku: int | None = None
    offer_id: str | None = Field(default=None, max_length=160)
    quantity: int = Field(gt=0, strict=True)
    price: Money | None = None


class Warehouse(ExternalModel):
    warehouse_id: int | None = None
    warehouse: str | None = Field(default=None, max_length=240)


class DeliveryInterval(ExternalModel):
    delivery_date_begin: datetime | None = None
    delivery_date_end: datetime | None = None

    @field_validator("delivery_date_begin", "delivery_date_end")
    @classmethod
    def utc_dates(cls, value):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("External dates require a timezone")
            return value.astimezone(timezone.utc)
        return None


class Posting(ExternalModel):
    posting_number: str = Field(min_length=1, max_length=80)
    order_number: str | None = Field(default=None, max_length=80)
    order_id: int | None = None
    status: str = Field(min_length=1, max_length=40)
    substatus: str | None = Field(default=None, max_length=80)
    shipment_date: datetime
    shipment_date_without_delay: datetime | None = None
    in_process_at: datetime | None = None
    delivering_date: datetime | None = None
    delivery_method: Warehouse | None = None
    analytics_data: DeliveryInterval | None = None
    products: list[Product]

    @field_validator("shipment_date", "shipment_date_without_delay", "in_process_at", "delivering_date")
    @classmethod
    def utc_dates(cls, value):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("External dates require a timezone")
            return value.astimezone(timezone.utc)
        return None


def upsert_posting(db: Session, raw: dict, *, is_mock: bool, actor_id: int | None,
                   source_raw: dict | None = None) -> bool:
    posting = Posting.model_validate(raw)
    # External columns only: production fields and relationships are never copied from payload.
    warehouse = posting.delivery_method
    fields = {
        "order_number": posting.order_number,
        "ozon_order_id": str(posting.order_id) if posting.order_id is not None else None,
        "ozon_status": posting.status, "ozon_substatus": posting.substatus,
        "warehouse_id": str(warehouse.warehouse_id) if warehouse and warehouse.warehouse_id is not None else None,
        "warehouse_name": warehouse.warehouse if warehouse else None,
        "shipment_deadline": posting.shipment_date,
        "shipment_date_without_delay": posting.shipment_date_without_delay,
        "ozon_in_process_at": posting.in_process_at,
        "ozon_delivering_date": posting.delivering_date,
    }
    if posting.analytics_data is not None:
        fields["ozon_delivery_date_begin"] = posting.analytics_data.delivery_date_begin
        fields["ozon_delivery_date_end"] = posting.analytics_data.delivery_date_end
    # The existing order_value is RUB-only. Missing prices/other currencies mean unknown.
    prices = [p.price for p in posting.products]
    total = sum((p.price.amount * p.quantity for p in posting.products if p.price), Decimal(0)).quantize(Decimal("0.01"))
    fields["order_value"] = (total
                             if prices and all(p and p.currency == "RUB" for p in prices)
                             and total < Decimal(10000000000) else None)
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    created_id = db.scalar(insert(Order).values(
        posting_number=posting.posting_number, internal_status="NEW", is_mock=is_mock,
        priority_pinned=False, created_at=utc_now(), **fields,
    ).on_conflict_do_nothing(index_elements=["posting_number"]).returning(Order.id))
    # Row lock serializes concurrent imports for both snapshot and item replacement.
    order = db.scalar(select(Order).where(Order.posting_number == posting.posting_number).with_for_update())
    if order.is_mock != is_mock:
        raise ValueError("Cannot merge mock and real postings")
    snapshot = db.get(OzonPostingData, order.id)
    source = raw if source_raw is None else source_raw
    raw_json = diagnostic_json(source)
    if snapshot is not None and snapshot.raw_json == raw_json:
        return False
    for name, value in fields.items():
        setattr(order, name, value)
    order.items = [OrderItem(product_name=p.name, offer_id=p.offer_id,
                            sku=str(p.sku) if p.sku is not None else None, quantity=p.quantity,
                            price=p.price.amount if p.price else None,
                            currency=p.price.currency if p.price else None) for p in posting.products]
    if snapshot is None:
        snapshot = OzonPostingData(order_id=order.id)
        db.add(snapshot)
    snapshot.raw_json = raw_json
    # JSON columns use decimal strings to avoid float conversion. Raw retains numeric types.
    for key in ("tariffication", "tariffication_steps"):
        value = source.get(key)
        setattr(snapshot, key, json.loads(diagnostic_json(value), parse_float=str))
    snapshot.imported_at = utc_now()
    if created_id is not None:
        db.add(StatusHistory(order_id=order.id, old_status=None, new_status="NEW", changed_by=actor_id))
    db.add(AuditLog(actor_user_id=actor_id,
                    action="ozon.posting.created" if created_id is not None else "ozon.posting.updated",
                    detail=f"order:{order.id}"))
    db.flush()
    return True


def import_fbs(db: Session, client: OzonClientInterface, since: datetime, to: datetime,
               *, is_mock: bool, actor_id: int | None,
               on_posting: Callable[[dict], bool] | None = None) -> dict:
    with posting_sync_lock:
        return _import_fbs(db, client, since, to, is_mock=is_mock,
                           actor_id=actor_id, on_posting=on_posting)


def _import_fbs(db: Session, client: OzonClientInterface, since: datetime, to: datetime,
                *, is_mock: bool, actor_id: int | None,
                on_posting: Callable[[dict], bool] | None = None) -> dict:
    """Caller commits once after all pages; any error rolls back the entire import."""
    validate_window(since, to)
    cursor = ""
    seen = set()
    changed = received = pages = 0
    while True:
        page = client.list_fbs(since, to, cursor=cursor)
        pages += 1
        if not isinstance(page.get("postings"), list) or type(page.get("has_next")) is not bool:
            raise OzonResponseError()
        for raw in page["postings"]:
            changed += (on_posting(raw) if on_posting else
                        upsert_posting(db, raw, is_mock=is_mock, actor_id=actor_id))
            received += 1
        if not page["has_next"]:
            return {"received": received, "changed": changed, "pages": pages}
        cursor = page.get("cursor")
        if not isinstance(cursor, str) or not cursor or cursor in seen or pages >= 10000:
            raise OzonResponseError()
        seen.add(cursor)
