"""Ozon push receiver and restart-safe database inbox, without periodic order sync."""

import asyncio
import copy
import hashlib
import ipaddress
import json
import logging
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.manager_tasks import ensure_task, resolve_source
from app.models import Order, OzonWebhookEvent, utc_now
from app.notifications import emit, manager_ids, sync_deadline_notifications
from app.ozon import OzonError
from app.ozon_import import diagnostic_json, posting_sync_lock, upsert_posting

router = APIRouter(prefix="/api/ozon")
logger = logging.getLogger(__name__)
MAX_BODY = 256 * 1024
OZON_NETWORKS = tuple(ipaddress.ip_network(n) for n in
                      ("195.34.21.0/24", "185.73.192.0/22", "91.223.93.0/24"))
POSTING_TYPES = frozenset({"TYPE_NEW_POSTING", "TYPE_STATE_CHANGED", "TYPE_POSTING_CANCELLED",
                           "TYPE_CUTOFF_DATE_CHANGED", "TYPE_DELIVERY_DATE_CHANGED"})


class Envelope(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_type: str = Field(min_length=1, max_length=100, strict=True)

    @field_validator("time", "shipment_date", "changed_state_date",
                     "in_process_at", "new_cutoff_date", "old_cutoff_date",
                     "new_delivery_date_begin", "new_delivery_date_end",
                     "old_delivery_date_begin", "old_delivery_date_end",
                     mode="before", check_fields=False)
    @classmethod
    def empty_date(cls, value):
        if value in (None, ""):
            return None
        if not isinstance(value, str) or "T" not in value:
            raise ValueError("Dates require ISO date-time strings")
        return value


class Ping(Envelope):
    time: AwareDatetime


class PostingEvent(Envelope):
    posting_number: str = Field(min_length=1, max_length=80, strict=True)
    seller_id: int = Field(ge=0, strict=True)
    warehouse_id: int = Field(ge=0, strict=True)


class PushProduct(BaseModel):
    sku: int = Field(ge=0, strict=True)
    quantity: int = Field(gt=0, strict=True)


class NewPosting(PostingEvent):
    products: list[PushProduct]
    # Late payment may leave this empty, as documented by Ozon.
    in_process_at: AwareDatetime | None = None
    shipment_date: AwareDatetime


class StateChanged(PostingEvent):
    new_state: str = Field(min_length=1, max_length=80, strict=True)
    changed_state_date: AwareDatetime


class CancellationReason(BaseModel):
    id: int = Field(strict=True)
    message: str


class Cancelled(StateChanged):
    products: list[PushProduct]
    old_state: str = Field(min_length=1, max_length=80, strict=True)
    reason: CancellationReason


class CutoffChanged(PostingEvent):
    new_cutoff_date: AwareDatetime | None
    old_cutoff_date: AwareDatetime | None


class DeliveryChanged(PostingEvent):
    new_delivery_date_begin: AwareDatetime | None
    new_delivery_date_end: AwareDatetime | None
    old_delivery_date_begin: AwareDatetime | None
    old_delivery_date_end: AwareDatetime | None


SCHEMAS = {"TYPE_PING": Ping, "TYPE_NEW_POSTING": NewPosting,
           "TYPE_STATE_CHANGED": StateChanged, "TYPE_POSTING_CANCELLED": Cancelled,
           "TYPE_CUTOFF_DATE_CHANGED": CutoffChanged, "TYPE_DELIVERY_DATE_CHANGED": DeliveryChanged}


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "error": {"code": code, "message": message, "details": None}})


def allowed_source(request: Request) -> bool:
    """Forwarded headers are accepted only from explicitly configured proxy peers."""
    config = request.app.state.settings
    host = request.client.host if request.client else ""
    if config.ozon_mock_mode:
        return host in ("127.0.0.1", "::1", "testclient")
    try:
        address = ipaddress.ip_address(host)
        proxies = [ipaddress.ip_network(n.strip()) for n in
                   config.ozon_webhook_trusted_proxies.split(",") if n.strip()]
        if any(address in network for network in proxies):
            # Caddy supplies this header from its actual remote socket, overwriting input.
            address = ipaddress.ip_address(request.headers.get("x-ozon-source-ip", ""))
        return any(address in network for network in OZON_NETWORKS)
    except ValueError:
        return False


def store_event(engine, canonical: str, message_type: str, posting_number: str | None,
                status: str, is_mock: bool, received_at) -> None:
    with Session(engine) as db:
        insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
        db.execute(insert(OzonWebhookEvent).values(
            event_key=hashlib.sha256(canonical.encode()).hexdigest(), payload_json=canonical,
            message_type=message_type, posting_number=posting_number, status=status,
            is_mock=is_mock, received_at=received_at, attempts=0, next_attempt_at=received_at,
            processed_at=received_at if status in ("PROCESSED", "IGNORED", "REJECTED") else None,
        ).on_conflict_do_nothing(index_elements=["event_key"]))
        db.commit()


@router.post("/webhook")
async def receive(request: Request):
    started = utc_now()
    config = request.app.state.settings
    if not config.ozon_webhook_enabled:
        return error(503, "ERROR_UNKNOWN", "Ozon webhook is disabled")
    if not allowed_source(request):
        return error(403, "ERROR_UNKNOWN", "Source is not allowed")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            return error(413, "ERROR_UNKNOWN", "Payload exceeds the size limit")
    canonical = json.dumps({"malformed_body": body.decode("utf-8", errors="replace")})
    kind, posting, status = "MALFORMED", None, "REJECTED"
    try:
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raise ValueError("Expected JSON")
        payload = json.loads(body, parse_float=Decimal,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid number")))
        canonical = diagnostic_json(payload)
        envelope = Envelope.model_validate(payload)
        kind = envelope.message_type
        model = SCHEMAS.get(kind, Envelope).model_validate(payload)
        posting = getattr(model, "posting_number", None)
        if kind in POSTING_TYPES:
            if not config.ozon_mock_mode and str(model.seller_id) != config.ozon_client_id:
                return error(403, "ERROR_UNKNOWN", "Seller is not allowed")
            status = "PENDING"
        else:
            status = "PROCESSED" if kind == "TYPE_PING" else "IGNORED"
    except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError):
        pass
    try:
        # Keep synchronous DB work off the event loop. No Seller API calls here.
        await asyncio.to_thread(store_event, request.app.state.engine, canonical, kind,
                                posting, status, config.ozon_mock_mode, started)
    except SQLAlchemyError:
        logger.error("Ozon webhook inbox unavailable")
        return error(503, "ERROR_UNKNOWN", "Event could not be stored")
    if status == "REJECTED":
        return error(400, "ERROR_PARAMETER_VALUE_MISSED", "Invalid webhook payload")
    if kind == "TYPE_PING":
        return {"version": "1.0", "name": "Ozon Production", "time": started.isoformat()}
    # A committed durable inbox entry is successful receipt, including redelivery.
    return {"result": True}


def import_shape(raw: dict) -> dict:
    """Adapt only documented v3 get product prices to task 021's shared mapper."""
    mapped = copy.deepcopy(raw)
    for product in mapped.get("products", []):
        price = product.get("price")
        product["price"] = ({"amount": price, "currency": product.get("currency_code")}
                            if price not in (None, "") else None)
    return mapped


def refresh_projections(db: Session, order: Order, config) -> None:
    from app.api_orders import (
        priority_for,
        priority_settings,
        production_profiles,
        tariff_for,
    )
    from app.money_at_risk import aggregate
    from app.tariff import parse_normalized_steps

    now = utc_now()
    tariff_for(order, now)
    priority = priority_for(order, production_profiles(db), priority_settings(db), now)
    aggregate([({"id": order.id, "posting_number": order.posting_number,
                 "internal_status": "CANCELLED" if order.ozon_status == "cancelled" else order.internal_status},
                parse_normalized_steps(order.tariff_steps), priority)], now,
              config.organization_timezone, config.money_risk_near_hours,
              tuple(int(h) for h in config.money_risk_cutoff_hours.split(",")))
    # These are read-time projections, with no cached score/risk columns to invalidate.
    sync_deadline_notifications(db, config.organization_timezone)


def apply_posting(db: Session, raw: dict, config, *, from_get: bool = False,
                  actor_id: int | None = None) -> bool:
    """Shared upsert and domain effects for push and reconciliation."""
    previous = db.scalar(select(Order).where(
        Order.posting_number == raw["posting_number"]).with_for_update())
    created = previous is None
    was_cancelled = previous is not None and previous.ozon_status == "cancelled"
    changed = upsert_posting(db, import_shape(raw) if from_get else raw, is_mock=config.ozon_mock_mode,
                             actor_id=actor_id, source_raw=raw)
    order = db.scalar(select(Order).where(Order.posting_number == raw["posting_number"]))
    recipients = manager_ids(db)
    if created and order.ozon_status != "cancelled":
        emit(db, type="NEW_ORDER", event_key=f"order:{order.id}", user_ids=recipients,
             title=f"Новый заказ {order.posting_number}", body="Заказ добавлен в очередь",
             url=f"/orders/{order.id}")
    if order.ozon_status == "cancelled":
        if order.assignment is not None:
            recipients.append(order.assignment.user_id)
        if (order.production_started_at is not None or order.production_completed_at is not None
                or order.internal_status in ("IN_PRODUCTION", "PRODUCED", "QUALITY_CHECK",
                                             "PACKING", "READY_TO_SHIP", "HANDED_TO_SHIPPING", "DONE")):
            ensure_task(db, source_type="OZON_CANCELLED_AFTER_START", source_id=order.id,
                        order_id=order.id, title=f"Ozon отменил {order.posting_number}",
                        description="Производство уже начато. Проверьте дальнейшие действия.",
                        severity="CRITICAL")
        if not was_cancelled:
            emit(db, type="ORDER_CANCELLED", event_key=f"order:{order.id}",
                 user_ids=recipients, title=f"Отмена {order.posting_number}",
                 body="Ozon отменил отправление. Проверьте производство.",
                 url=f"/orders/{order.id}")
    else:
        resolve_source(db, source_type="OZON_CANCELLED_AFTER_START", source_id=order.id)
    if changed:
        refresh_projections(db, order, config)
    return changed


def process_one(engine, client, config, events) -> bool:
    with posting_sync_lock:
        return _process_one(engine, client, config, events)


def _process_one(engine, client, config, events) -> bool:
    """Commit domain writes and inbox completion atomically; return whether work existed."""
    event_id = None
    try:
        with Session(engine) as db:
            event = db.scalar(select(OzonWebhookEvent).where(
                OzonWebhookEvent.status.in_(("PENDING", "RETRY")),
                OzonWebhookEvent.next_attempt_at <= utc_now(),
            ).order_by(OzonWebhookEvent.id).limit(1).with_for_update(skip_locked=True))
            if event is None:
                return False
            event_id = event.id
            recovering = event.error_code is not None
            if event.is_mock != config.ozon_mock_mode:
                raise ValueError("Inbox mode mismatch")
            payload = json.loads(event.payload_json, parse_float=Decimal)
            empty_interval = (event.message_type == "TYPE_CUTOFF_DATE_CHANGED" and
                              not payload.get("new_cutoff_date")) or (
                event.message_type == "TYPE_DELIVERY_DATE_CHANGED" and
                (not payload.get("new_delivery_date_begin") or not payload.get("new_delivery_date_end")))
            changed = False
            if empty_interval:
                event.status = "IGNORED"
            else:
                # Always fetch current data: old/out-of-order pushes cannot revert a posting.
                raw = client.get_fbs(event.posting_number)
                if raw.get("posting_number") != event.posting_number:
                    raise ValueError("Posting mismatch")
                if event.message_type == "TYPE_CUTOFF_DATE_CHANGED" and raw.get("status") not in (
                        "awaiting_approve", "awaiting_packaging", "awaiting_registration", "awaiting_verification"):
                    event.status = "IGNORED"
                else:
                    changed = apply_posting(db, raw, config, from_get=True)
                    order = db.scalar(select(Order).where(Order.posting_number == event.posting_number))
                    event.status = "PROCESSED"
            event.attempts += 1
            event.processed_at = utc_now()
            event.error_code = None
            resolve_source(db, source_type="OZON_SYNC_ERROR", source_id=event.id)
            db.commit()
            if changed or recovering:
                try:
                    events.publish(order.id if changed else 0)
                except RuntimeError:
                    logger.error("Ozon webhook realtime publication unavailable")
            return True
    except Exception as exc:  # noqa: BLE001 - durable inbox boundary; safe error codes only
        # Never log provider data, raw exception messages, credentials or payloads.
        safe_code = type(exc).__name__ if isinstance(exc, (OzonError, ValidationError)) else "PROCESSING_ERROR"
        logger.error("Ozon webhook processing failed event_id=%s code=%s", event_id, safe_code)
        if event_id is None:
            return False
        with Session(engine) as db:
            event = db.scalar(select(OzonWebhookEvent).where(
                OzonWebhookEvent.id == event_id).with_for_update())
            event.attempts += 1
            event.status = "FAILED" if event.attempts >= 5 else "RETRY"
            event.error_code = safe_code
            event.next_attempt_at = utc_now() + timedelta(seconds=min(300, 5 * 2 ** event.attempts))
            ensure_task(db, source_type="OZON_SYNC_ERROR", source_id=event.id, order_id=None,
                        title="Ошибка обработки Ozon webhook", description=f"Событие {event.id}: {safe_code}",
                        severity="HIGH")
            emit(db, type="OZON_SYNC_ERROR", event_key=f"webhook:{event.id}",
                 user_ids=manager_ids(db), title="Ошибка Ozon webhook",
                 body=f"Не удалось обработать событие {event.id}. Код: {safe_code}")
            db.commit()
        try:
            events.publish(0)
        except RuntimeError:
            logger.error("Ozon webhook realtime publication unavailable")
        return True


async def processing_loop(engine, client, config, events, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            worked = await asyncio.to_thread(process_one, engine, client, config, events)
        except Exception:  # noqa: BLE001 - keep inbox worker alive on infrastructure errors
            logger.error("Ozon webhook inbox worker unavailable")
            worked = False
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.05 if worked else 0.5)
        except TimeoutError:
            pass
