import asyncio
import heapq
from datetime import timezone
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import joinedload, selectinload

from app.auth import Current, Db, require
from app.models import (
    Assignment,
    AuditLog,
    Blocker,
    Comment,
    CommentMention,
    InternalStatus,
    Order,
    OrderItem,
    OrderTimelineEvent,
    PrioritySettings,
    ProductProductionProfile,
    Role,
    StatusHistory,
    User,
    utc_now,
)
from app.orders import STATUSES, TRANSITIONS, transition
from app.performance import MAX_OFFSET, order_batches
from app.priority import LEVELS, PriorityInput, PriorityWeights, evaluate, sort_key
from app.rbac import user_permissions
from app.tariff import evaluate as evaluate_tariff
from app.tariff import parse_normalized_steps

router = APIRouter(prefix="/api/orders")


class StatusInput(BaseModel):
    status: Literal["NEW", "QUEUED", "SENT_TO_PRODUCTION", "IN_PRODUCTION", "BLOCKED", "PRODUCED", "QUALITY_CHECK", "PACKING", "READY_TO_SHIP", "HANDED_TO_SHIPPING", "DONE", "CANCELLED"]


class StatusSettingsInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    sort_order: int = Field(ge=0, le=1000)


class AssignmentInput(BaseModel):
    user_id: int | None


class BulkActionInput(BaseModel):
    order_ids: list[int] = Field(min_length=1, max_length=100)
    action: Literal["assign", "status"]
    user_id: int | None = None
    status: Literal["NEW", "QUEUED", "SENT_TO_PRODUCTION", "IN_PRODUCTION", "BLOCKED", "PRODUCED", "QUALITY_CHECK", "PACKING", "READY_TO_SHIP", "HANDED_TO_SHIPPING", "DONE", "CANCELLED"] | None = None


class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    mention_user_ids: list[int] = Field(default_factory=list, max_length=50)


class PriorityOverrideInput(BaseModel):
    level: Literal["P0", "P1", "P2", "P3", "P4"] | None = None
    pinned: bool = False


class PrioritySettingsInput(BaseModel):
    deadline_weight: int = Field(ge=0, le=100)
    tariff_weight: int = Field(ge=0, le=100)
    finance_weight: int = Field(ge=0, le=100)
    feasibility_weight: int = Field(ge=0, le=100)
    high_impact_rub: Decimal = Field(gt=0, le=1_000_000_000, max_digits=12, decimal_places=2)
    high_value_rub: Decimal = Field(gt=0, le=1_000_000_000, max_digits=12, decimal_places=2)


def order_query():
    return select(Order).options(selectinload(Order.items), joinedload(Order.assignment).joinedload(Assignment.user))


def priority_settings(db: Db) -> PrioritySettings:
    return db.get(PrioritySettings, 1) or PrioritySettings(
        id=1, deadline_weight=40, tariff_weight=25, finance_weight=20,
        feasibility_weight=15, high_impact_rub=Decimal(1000), high_value_rub=Decimal(10000))


def priority_for(order: Order, profiles: dict, settings: PrioritySettings, now) -> dict:
    def utc(value):
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value

    remaining = 0
    known = True
    for item in order.items:
        profile = (profiles.get(("offer_id", item.offer_id)) if item.offer_id else None) or (
            profiles.get(("sku", item.sku)) if item.sku else None)
        if profile is None:
            known = False
            break
        if order.internal_status in ("PRODUCED", "QUALITY_CHECK", "PACKING", "READY_TO_SHIP"):
            minutes = profile.packing_minutes if order.internal_status != "READY_TO_SHIP" else 0
        else:
            minutes = profile.production_minutes + profile.packing_minutes
        remaining += minutes * item.quantity
    tariff = tariff_for(order, now)
    next_step = tariff["next"] if tariff else None
    delta = tariff["delta_to_next_tariff"] if tariff else None
    return evaluate(PriorityInput(
        shipment_deadline=utc(order.shipment_deadline),
        shipment_date_without_delay=utc(order.shipment_date_without_delay),
        tariff_deadline=next_step["starts_at"] if next_step else
        (utc(order.tariff_deadline) if tariff is None else None),
        tariff_impact=max(delta, Decimal(0)) if delta is not None and next_step["currency"] == "RUB" else
        (order.tariff_impact if tariff is None else None),
        order_value=order.order_value,
        internal_status="CANCELLED" if order.ozon_status == "cancelled" else order.internal_status,
        remaining_minutes=remaining if known else None,
        blocked=order.internal_status == "BLOCKED", override=order.priority_override,
        pinned=order.priority_pinned), now,
        PriorityWeights(settings.deadline_weight, settings.tariff_weight, settings.finance_weight,
                        settings.feasibility_weight, settings.high_impact_rub, settings.high_value_rub))


def tariff_for(order: Order, now) -> dict | None:
    if order.tariff_steps is None:
        return None
    return evaluate_tariff(parse_normalized_steps(order.tariff_steps), now)


def visible_priority(priority: dict, can_view_finance: bool) -> dict:
    if can_view_finance:
        return priority
    return {**priority, "financial_impact": None,
            "reasons": [reason for reason in priority["reasons"]
                        if not reason.startswith(("Подтверждённый эффект тарифа:", "Стоимость заказа:"))]}


def production_profiles(db: Db, orders=None) -> dict[tuple[str, str], ProductProductionProfile]:
    query = select(ProductProductionProfile)
    if orders is not None:
        offers = {item.offer_id for order in orders for item in order.items if item.offer_id}
        skus = {item.sku for order in orders for item in order.items if item.sku}
        query = query.where(or_(ProductProductionProfile.offer_id.in_(offers),
                               ProductProductionProfile.sku.in_(skus)))
    profiles = db.scalars(query).all()
    return {(key, value): profile for profile in profiles
            for key, value in (("offer_id", profile.offer_id), ("sku", profile.sku)) if value}


def order_data(order: Order, profiles: dict[tuple[str, str], ProductProductionProfile] | None = None,
               priority: dict | None = None, tariff: dict | None = None) -> dict:
    profiles = profiles or {}
    def utc(value):
        # SQLite loses tzinfo on reload; timestamps in storage are always UTC.
        # Preserve timezone information when the UI sends a deadline back to API.
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value

    return {
        "id": order.id, "posting_number": order.posting_number,
        "order_number": order.order_number, "warehouse_id": order.warehouse_id,
        "ozon_status": order.ozon_status, "internal_status": order.internal_status,
        "production_started_at": utc(order.production_started_at),
        "production_completed_at": utc(order.production_completed_at),
        "packing_started_at": utc(order.packing_started_at),
        "ready_to_ship_at": utc(order.ready_to_ship_at),
        "handed_to_shipping_at": utc(order.handed_to_shipping_at),
        "done_at": utc(order.done_at),
        "shipment_deadline": utc(order.shipment_deadline),
        "shipment_date_without_delay": utc(order.shipment_date_without_delay),
        "tariff_deadline": utc(order.tariff_deadline), "priority": priority, "tariff": tariff, "items": [
            {"product_name": item.product_name, "offer_id": item.offer_id, "sku": item.sku,
             "quantity": item.quantity,
             "production_profile": (
                 {"product_name": profile.product_name, "production_minutes": profile.production_minutes,
                  "packing_minutes": profile.packing_minutes, "complexity": profile.complexity,
                  "production_group": profile.production_group}
                 if (profile := profiles.get(("offer_id", item.offer_id)) if item.offer_id else None)
                 or (profile := profiles.get(("sku", item.sku)) if item.sku else None) else None
             )} for item in order.items
        ],
        "assigned_user": ({"id": order.assignment.user.id, "display_name": order.assignment.user.display_name}
                          if order.assignment else None),
    }


@router.get("/statuses")
def list_statuses(db: Db, _actor: Annotated[User, Depends(require("orders.view"))]) -> list[dict]:
    rows = db.scalars(select(InternalStatus).order_by(InternalStatus.sort_order, InternalStatus.name)).all()
    return [{"code": row.name, "display_name": row.display_name, "sort_order": row.sort_order} for row in rows]


@router.put("/statuses/{code}")
def update_status(code: str, payload: StatusSettingsInput, db: Db, request: Request,
                  actor: Annotated[User, Depends(require("settings.manage"))]) -> dict:
    row = db.get(InternalStatus, code)
    if row is None:
        raise HTTPException(404, "Status not found")
    row.display_name = payload.display_name.strip()
    if not row.display_name:
        raise HTTPException(422, "Display name cannot be blank")
    row.sort_order = payload.sort_order
    db.add(AuditLog(actor_user_id=actor.id, action="status.settings_changed", detail=code))
    db.commit()
    request.app.state.order_events.publish(0)
    return {"code": row.name, "display_name": row.display_name, "sort_order": row.sort_order}


@router.get("")
def list_orders(
    db: Db, _actor: Annotated[User, Depends(require("orders.view"))],
    order_id: int | None = None, status: str | None = None, assigned_user_id: int | None = None,
    blocked: bool | None = None, ready: bool | None = None, overdue: bool | None = None,
    priority_level: str | None = None,
    q: str | None = None, ozon_status: str | None = None,
    product: str | None = None, warehouse: str | None = None,
    limit: int = 20, offset: int = 0,
) -> dict:
    if status is not None and status not in STATUSES:
        raise HTTPException(422, "Unknown status")
    if priority_level is not None and priority_level not in LEVELS:
        raise HTTPException(422, "Unknown priority level")
    if not 1 <= limit <= 100 or not 0 <= offset <= MAX_OFFSET:
        raise HTTPException(422, "Invalid pagination")
    query = select(Order)
    # Exact lookup and explicit cancellation filters retain access to the archive.
    if order_id is None and ozon_status != "cancelled" and status != "CANCELLED":
        query = query.where(Order.ozon_status != "cancelled")
    if order_id is None and status is None and ozon_status is None:
        query = query.where(Order.internal_status.notin_(("DONE", "CANCELLED", "HANDED_TO_SHIPPING")))
    if order_id is not None:
        query = query.where(Order.id == order_id)
    if status:
        query = query.where(Order.internal_status == status)
    if assigned_user_id is not None:
        query = query.join(Assignment).where(Assignment.user_id == assigned_user_id)
    if blocked is not None:
        query = query.where((Order.internal_status == "BLOCKED") if blocked else (Order.internal_status != "BLOCKED"))
    if ready is not None:
        query = query.where((Order.internal_status == "READY_TO_SHIP") if ready else (Order.internal_status != "READY_TO_SHIP"))
    if overdue is not None:
        active = Order.internal_status.notin_(("DONE", "CANCELLED"))
        query = query.where((Order.shipment_deadline < utc_now()) & active if overdue else
                            (Order.shipment_deadline >= utc_now()) | ~active)
    if priority_level is not None:
        query = query.where(Order.internal_status.notin_(("DONE", "CANCELLED", "HANDED_TO_SHIPPING")))
    if ozon_status:
        query = query.where(Order.ozon_status == ozon_status)
    if product:
        query = query.where(Order.id.in_(select(OrderItem.order_id).where(OrderItem.product_name.ilike(f"%{product.strip()}%"))))
    if warehouse:
        query = query.where(Order.warehouse_id == warehouse)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.where(or_(Order.posting_number.ilike(term),
                                Order.order_number.ilike(term),
                                Order.id.in_(select(OrderItem.order_id).where(or_(
                                    OrderItem.sku.ilike(term), OrderItem.offer_id.ilike(term),
                                    OrderItem.product_name.ilike(term))))))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    if not total:
        return {"items": [], "total": total}
    settings = priority_settings(db)
    now = utc_now()
    matches = 0
    def candidates():
        nonlocal matches
        for batch in order_batches(db, query):
            profile_map = production_profiles(db, batch)
            for order in batch:
                priority = priority_for(order, profile_map, settings, now)
                if priority_level is None or priority["level"] == priority_level:
                    matches += 1
                    yield sort_key(priority, order.id), order.id, priority
    selected = heapq.nsmallest(offset + limit, candidates(), key=lambda row: row[0])[offset:]
    total = matches
    orders = {order.id: order for order in db.scalars(order_query().where(
        Order.id.in_([row[1] for row in selected])))}
    ranked = [(orders[order_id], priority) for _, order_id, priority in selected if order_id in orders]
    profile_map = production_profiles(db, orders.values())
    can_view_finance = "finance.view" in user_permissions(_actor)
    def visible_tariff(order):
        tariff = tariff_for(order, now)
        if tariff is None or can_view_finance:
            return tariff
        def without_money(step):
            return {**step, "cost": None} if step else None
        return {**tariff, "current": without_money(tariff["current"]),
                "next": without_money(tariff["next"]),
                "timeline": [without_money(step) for step in tariff["timeline"]],
                "current_tariff_cost": None, "next_tariff_cost": None,
                "delta_to_next_tariff": None, "potential_saving": None, "potential_loss": None}

    return {"items": [order_data(order, profile_map, visible_priority(priority, can_view_finance), visible_tariff(order))
                      for order, priority in ranked],
            "total": total}


@router.post("/bulk")
def bulk_action(payload: BulkActionInput, db: Db, request: Request,
                actor: Annotated[User, Depends(require("orders.view"))]) -> dict:
    permissions = user_permissions(actor)
    required = "orders.assign" if payload.action == "assign" else "orders.change_status"
    if required not in permissions:
        raise HTTPException(403, "Permission denied")
    ids = sorted(set(payload.order_ids))
    if len(ids) != len(payload.order_ids):
        raise HTTPException(422, "Duplicate order IDs")
    orders = db.scalars(select(Order).where(Order.id.in_(ids)).order_by(Order.id).with_for_update()).all()
    if len(orders) != len(ids):
        raise HTTPException(404, "One or more orders not found")
    target = None
    if payload.action == "assign":
        if payload.status is not None:
            raise HTTPException(422, "Status is not valid for assignment")
        if payload.user_id is not None:
            target = db.scalar(select(User).options(selectinload(User.roles).selectinload(Role.permissions)).where(User.id == payload.user_id))
            if target is None or not target.is_active or "orders.change_status" not in user_permissions(target):
                raise HTTPException(422, "Assignee must be an active production user")
        if any(order.internal_status in ("DONE", "CANCELLED") for order in orders):
            raise HTTPException(409, "Closed orders cannot be assigned")
    else:
        if payload.status is None or payload.user_id is not None:
            raise HTTPException(422, "Status is required for status action")
        if payload.status == "BLOCKED":
            raise HTTPException(409, "Create a blocker to mark orders blocked")
        for order in orders:
            if order.ozon_status == "cancelled" and payload.status != "CANCELLED":
                raise HTTPException(409, "Ozon cancelled this posting; manager review required")
            if order.internal_status == "BLOCKED" and payload.status != "CANCELLED":
                active = db.scalar(select(Blocker.id).where(Blocker.order_id == order.id, Blocker.status.in_(("OPEN", "IN_PROGRESS"))).limit(1))
                if active is not None:
                    raise HTTPException(409, f"Resolve active blockers first: {order.posting_number}")
            try:
                if payload.status not in TRANSITIONS.get(order.internal_status, set()):
                    raise ValueError
            except ValueError:
                raise HTTPException(409, f"Invalid status transition for {order.posting_number}") from None
            if "orders.assign" not in permissions:
                assigned_id = db.scalar(select(Assignment.user_id).where(Assignment.order_id == order.id))
                if assigned_id != actor.id or payload.status in ("BLOCKED", "CANCELLED", "DONE", "NEW"):
                    raise HTTPException(403, f"Manager action required: {order.posting_number}")
    for order in orders:
        if payload.action == "assign":
            assignment = db.scalar(select(Assignment).where(Assignment.order_id == order.id))
            if payload.user_id is None:
                if assignment:
                    db.delete(assignment)
            elif assignment:
                assignment.user_id = target.id
                assignment.assigned_by = actor.id
            else:
                db.add(Assignment(order_id=order.id, user_id=target.id, assigned_by=actor.id))
            description = f"Ответственный: {target.display_name}" if target else "Ответственный снят"
            db.add(OrderTimelineEvent(order_id=order.id, event_type="assignment_changed", description=description, actor_user_id=actor.id))
        else:
            transition(db, order, payload.status, actor.id)
    db.add(AuditLog(actor_user_id=actor.id, action=f"order.bulk_{payload.action}",
                    entity_type="orders", entity_id="bulk",
                    new_value={"order_ids": ids, "action": payload.action,
                               "user_id": payload.user_id, "status": payload.status},
                    detail=f"{','.join(order.posting_number for order in orders)}; target={payload.user_id if payload.action == 'assign' else payload.status}"))
    db.commit()
    request.app.state.order_events.publish(0)
    return {"updated": len(orders), "order_ids": ids}


@router.get("/priority-settings")
def get_priority_settings(db: Db, _actor: Annotated[User, Depends(require("orders.view"))]) -> dict:
    row = priority_settings(db)
    return {name: getattr(row, name) for name in PrioritySettingsInput.model_fields}


@router.put("/priority-settings")
def set_priority_settings(payload: PrioritySettingsInput, db: Db, request: Request,
                          actor: Annotated[User, Depends(require("settings.manage"))]) -> dict:
    if sum((payload.deadline_weight, payload.tariff_weight, payload.finance_weight,
            payload.feasibility_weight)) != 100:
        raise HTTPException(422, "Priority weights must sum to 100")
    row = priority_settings(db)
    for name, value in payload.model_dump().items():
        setattr(row, name, value)
    db.add(row)
    db.add(AuditLog(actor_user_id=actor.id, action="priority.settings_changed", detail="weights"))
    db.commit()
    request.app.state.order_events.publish(0)
    return payload.model_dump()


@router.put("/{order_id}/priority")
def set_priority_override(order_id: int, payload: PriorityOverrideInput, db: Db, request: Request,
                          actor: Annotated[User, Depends(require("orders.change_priority"))]) -> dict:
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "Order not found")
    if order.internal_status in ("DONE", "CANCELLED", "HANDED_TO_SHIPPING"):
        raise HTTPException(409, "Order is closed")
    old = f"{order.priority_override or '-'}:{order.priority_pinned}"
    order.priority_override = payload.level
    order.priority_pinned = payload.pinned
    db.add(AuditLog(actor_user_id=actor.id, action="order.priority_changed",
                    detail=f"{order.posting_number}: {old} -> {payload.level or '-'}:{payload.pinned}"))
    db.add(OrderTimelineEvent(order_id=order_id, event_type="priority_changed",
                              description=f"Ручной приоритет: {payload.level or 'автоматический'}; закреплено: {payload.pinned}",
                              actor_user_id=actor.id))
    db.commit()
    request.app.state.order_events.publish(order_id)
    loaded = db.scalar(order_query().where(Order.id == order_id))
    profiles = production_profiles(db, [loaded])
    priority = priority_for(loaded, profiles, priority_settings(db), utc_now())
    return order_data(loaded, profiles, visible_priority(priority, "finance.view" in user_permissions(actor)))


@router.get("/events")
async def events(request: Request, db: Db, _current: Current):
    user, _session = _current
    if "orders.view" not in user_permissions(user):
        raise HTTPException(403, "Permission denied")
    bus = request.app.state.order_events
    # Authentication is complete. A 20-second stream must not occupy a DB slot.
    db.close()
    try:
        queue = bus.subscribe()
    except ValueError:
        raise HTTPException(503, "Event stream capacity reached", headers={"Retry-After": "5"}) from None

    async def stream():
        deadline = asyncio.get_running_loop().time() + 20
        try:
            yield ": connected\n\n"
            while not await request.is_disconnected():
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    order_id = await asyncio.wait_for(queue.get(), timeout=remaining)
                except TimeoutError:
                    break  # Reconnect through auth to pick up role/session changes.
                yield f"event: orders\ndata: {order_id}\n\n"
                # Coalesce bursts without extending the authentication deadline.
                await asyncio.sleep(min(0.5, max(0, deadline - asyncio.get_running_loop().time())))
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


@router.get("/{order_id}/history")
def history(order_id: int, db: Db, _actor: Annotated[User, Depends(require("orders.view"))],
            limit: int = 200, offset: int = 0) -> list[dict]:
    if not 1 <= limit <= 200 or not 0 <= offset <= MAX_OFFSET:
        raise HTTPException(422, "Invalid pagination")
    if db.get(Order, order_id) is None:
        raise HTTPException(404, "Order not found")
    rows = db.scalars(select(StatusHistory).where(StatusHistory.order_id == order_id)
                      .order_by(StatusHistory.id).limit(limit).offset(offset)).all()
    return [{"old_status": row.old_status, "new_status": row.new_status,
             "changed_at": row.changed_at, "changed_by": row.changed_by} for row in rows]


@router.get("/{order_id}/timeline")
def timeline(order_id: int, db: Db, _actor: Annotated[User, Depends(require("orders.view"))],
             limit: int = 100, offset: int = 0) -> dict:
    if db.get(Order, order_id) is None:
        raise HTTPException(404, "Order not found")
    if not 1 <= limit <= 200 or not 0 <= offset <= MAX_OFFSET:
        raise HTTPException(422, "Invalid pagination")
    identities = union_all(*[
        select(model.id.label("row_id"), literal(kind).label("kind"),
               timestamp.label("created_at"), (literal(prefix) + cast(model.id, String)).label("sort_id"))
        .where(model.order_id == order_id)
        for model, timestamp, kind, prefix in (
            (Comment, Comment.created_at, "comment", "comment-"),
            (StatusHistory, StatusHistory.changed_at, "status", "status-"),
            (OrderTimelineEvent, OrderTimelineEvent.created_at, "event", "event-"))
    ]).subquery()
    total = db.scalar(select(func.count()).select_from(identities)) or 0
    selected = db.execute(select(identities.c.row_id, identities.c.kind)
        .order_by(identities.c.created_at, identities.c.sort_id).offset(offset).limit(limit)).all()
    ids = {kind: [row_id for row_id, row_kind in selected if row_kind == kind]
           for kind in ("comment", "status", "event")}
    comments = db.scalars(select(Comment).options(joinedload(Comment.author), selectinload(Comment.mentions))
                          .where(Comment.id.in_(ids["comment"]))).all()
    statuses = db.scalars(select(StatusHistory).options(joinedload(StatusHistory.changed_by_user))
                          .where(StatusHistory.id.in_(ids["status"]))).all()
    status_labels = {row.name: row.display_name for row in db.scalars(select(InternalStatus)).all()}
    events = db.scalars(select(OrderTimelineEvent).options(joinedload(OrderTimelineEvent.actor))
                        .where(OrderTimelineEvent.id.in_(ids["event"]))).all()
    items = [
        {"id": f"comment-{row.id}", "kind": "comment", "body": row.body,
         "author": row.author.display_name if row.author else "Удалённый пользователь",
         "author_user_id": row.author_user_id,
         "created_at": row.created_at, "mention_user_ids": [m.user_id for m in row.mentions]}
        for row in comments
    ] + [
        {"id": f"status-{row.id}", "kind": "system", "event_type": "status_changed",
         "body": f"Статус изменён: {status_labels.get(row.old_status, '—')} → {status_labels.get(row.new_status, row.new_status)}",
         "author": None, "created_at": row.changed_at, "mention_user_ids": []} for row in statuses
    ] + [
        {"id": f"event-{row.id}", "kind": "system", "event_type": row.event_type,
         "body": row.description, "author": row.actor.display_name if row.actor else None,
         "created_at": row.created_at, "mention_user_ids": []} for row in events
    ]
    items.sort(key=lambda item: (item["created_at"], item["id"]))
    return {"items": items, "total": total}


@router.post("/{order_id}/comments", status_code=201)
def create_comment(order_id: int, payload: CommentInput, db: Db, request: Request,
                   actor: Annotated[User, Depends(require("comments.create"))]) -> dict:
    if db.get(Order, order_id) is None:
        raise HTTPException(404, "Order not found")
    body = payload.body.strip()
    if not body:
        raise HTTPException(422, "Comment cannot be blank")
    mention_ids = sorted(set(payload.mention_user_ids))
    if mention_ids:
        found = set(db.scalars(select(User.id).where(User.id.in_(mention_ids), User.is_active)).all())
        if found != set(mention_ids):
            raise HTTPException(422, "Mentioned users must be active")
    comment = Comment(order_id=order_id, author_user_id=actor.id, body=body,
                      mentions=[CommentMention(user_id=user_id) for user_id in mention_ids])
    db.add(comment)
    db.add(AuditLog(actor_user_id=actor.id, action="order.comment_created", detail=str(order_id)))
    db.commit()
    db.refresh(comment)
    request.app.state.order_events.publish(order_id)
    return {"id": comment.id, "kind": "comment", "body": comment.body,
            "author": actor.display_name, "created_at": comment.created_at,
            "mention_user_ids": mention_ids}


@router.post("/{order_id}/claim")
def claim(order_id: int, db: Db, actor: Annotated[User, Depends(require("orders.change_status"))], request: Request) -> dict:
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "Order not found")
    if order.ozon_status == "cancelled" or order.internal_status not in ("NEW", "QUEUED", "SENT_TO_PRODUCTION"):
        raise HTTPException(409, "Order cannot be claimed")
    if db.scalar(select(Assignment.id).where(Assignment.order_id == order_id)) is not None:
        raise HTTPException(409, "Order already assigned")
    db.add(Assignment(order_id=order_id, user_id=actor.id, assigned_by=actor.id))
    db.add(OrderTimelineEvent(order_id=order_id, event_type="assignment_changed",
                              description=f"Заказ взял в работу {actor.display_name}", actor_user_id=actor.id))
    if order.internal_status == "NEW":
        transition(db, order, "QUEUED", actor.id)
    db.add(AuditLog(actor_user_id=actor.id, action="order.claimed", detail=order.posting_number))
    db.commit()
    request.app.state.order_events.publish(order_id)
    loaded = db.scalar(order_query().where(Order.id == order_id))
    return order_data(loaded, production_profiles(db, [loaded]))


@router.put("/{order_id}/assignment")
def assign(order_id: int, payload: AssignmentInput, db: Db, request: Request,
           actor: Annotated[User, Depends(require("orders.assign"))]) -> dict:
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "Order not found")
    if order.internal_status in ("DONE", "CANCELLED"):
        raise HTTPException(409, "Order is closed")
    assignment = db.scalar(select(Assignment).where(Assignment.order_id == order_id))
    if payload.user_id is None:
        if assignment:
            db.delete(assignment)
    else:
        target = db.scalar(select(User).options(selectinload(User.roles).selectinload(Role.permissions)).where(User.id == payload.user_id))
        if target is None or not target.is_active or "orders.change_status" not in user_permissions(target):
            raise HTTPException(422, "Assignee must be an active production user")
        if assignment:
            assignment.user_id = target.id
            assignment.assigned_by = actor.id
        else:
            db.add(Assignment(order_id=order_id, user_id=target.id, assigned_by=actor.id))
    description = (f"Ответственный: {target.display_name}" if payload.user_id is not None
                   else "Ответственный снят")
    db.add(OrderTimelineEvent(order_id=order_id, event_type="assignment_changed",
                              description=description, actor_user_id=actor.id))
    db.add(AuditLog(actor_user_id=actor.id, action="order.assigned", detail=order.posting_number))
    db.commit()
    request.app.state.order_events.publish(order_id)
    loaded = db.scalar(order_query().where(Order.id == order_id))
    return order_data(loaded, production_profiles(db, [loaded]))


@router.post("/{order_id}/status")
def change_status(order_id: int, payload: StatusInput, db: Db, request: Request,
                  actor: Annotated[User, Depends(require("orders.change_status"))]) -> dict:
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "Order not found")
    if payload.status == "BLOCKED":
        raise HTTPException(409, "Create a blocker to mark an order blocked")
    if order.internal_status == "BLOCKED" and payload.status != "CANCELLED":
        active = db.scalar(select(Blocker.id).where(Blocker.order_id == order_id,
                                                    Blocker.status.in_(("OPEN", "IN_PROGRESS"))).limit(1))
        if active is not None:
            raise HTTPException(409, "Resolve active blockers first")
    if "orders.assign" not in user_permissions(actor):
        assigned_id = db.scalar(select(Assignment.user_id).where(Assignment.order_id == order_id))
        if assigned_id != actor.id:
            raise HTTPException(403, "Only the assigned worker can change this order")
        if payload.status in ("BLOCKED", "CANCELLED", "DONE", "NEW"):
            raise HTTPException(403, "Manager action required")
    try:
        transition(db, order, payload.status, actor.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    db.add(AuditLog(actor_user_id=actor.id, action="order.status_changed", detail=order.posting_number))
    db.commit()
    request.app.state.order_events.publish(order_id)
    loaded = db.scalar(order_query().where(Order.id == order_id))
    return order_data(loaded, production_profiles(db, [loaded]))
