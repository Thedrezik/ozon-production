import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
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
    OrderTimelineEvent,
    Role,
    StatusHistory,
    User,
    utc_now,
)
from app.orders import STATUSES, transition
from app.rbac import user_permissions

router = APIRouter(prefix="/api/orders")


class StatusInput(BaseModel):
    status: Literal["NEW", "QUEUED", "SENT_TO_PRODUCTION", "IN_PRODUCTION", "BLOCKED", "PRODUCED", "QUALITY_CHECK", "PACKING", "READY_TO_SHIP", "HANDED_TO_SHIPPING", "DONE", "CANCELLED"]


class StatusSettingsInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    sort_order: int = Field(ge=0, le=1000)


class AssignmentInput(BaseModel):
    user_id: int | None


class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    mention_user_ids: list[int] = Field(default_factory=list, max_length=50)


def order_query():
    return select(Order).options(selectinload(Order.items), joinedload(Order.assignment).joinedload(Assignment.user))


def order_data(order: Order) -> dict:
    return {
        "id": order.id, "posting_number": order.posting_number,
        "ozon_status": order.ozon_status, "internal_status": order.internal_status,
        "production_started_at": order.production_started_at,
        "production_completed_at": order.production_completed_at,
        "packing_started_at": order.packing_started_at,
        "ready_to_ship_at": order.ready_to_ship_at,
        "handed_to_shipping_at": order.handed_to_shipping_at,
        "done_at": order.done_at,
        "shipment_deadline": order.shipment_deadline, "items": [
            {"product_name": item.product_name, "quantity": item.quantity} for item in order.items
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
    status: str | None = None, assigned_user_id: int | None = None,
    blocked: bool | None = None, ready: bool | None = None, overdue: bool | None = None,
    limit: int = 20, offset: int = 0,
) -> dict:
    if status is not None and status not in STATUSES:
        raise HTTPException(422, "Unknown status")
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Invalid pagination")
    query = select(Order)
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
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    ids = db.scalars(query.order_by(Order.shipment_deadline, Order.id).limit(limit).offset(offset).with_only_columns(Order.id)).all()
    if not ids:
        return {"items": [], "total": total}
    orders = db.scalars(order_query().where(Order.id.in_(ids))).all()
    by_id = {order.id: order for order in orders}
    return {"items": [order_data(by_id[order_id]) for order_id in ids], "total": total}


@router.get("/events")
async def events(request: Request, _current: Current):
    user, _session = _current
    if "orders.view" not in user_permissions(user):
        raise HTTPException(403, "Permission denied")
    bus = request.app.state.order_events
    queue = bus.subscribe()

    async def stream():
        try:
            yield ": connected\n\n"
            while not await request.is_disconnected():
                try:
                    order_id = await asyncio.wait_for(queue.get(), timeout=20)
                except TimeoutError:
                    break  # Reconnect through auth to pick up role/session changes.
                yield f"event: orders\ndata: {order_id}\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


@router.get("/{order_id}/history")
def history(order_id: int, db: Db, _actor: Annotated[User, Depends(require("orders.view"))]) -> list[dict]:
    if db.get(Order, order_id) is None:
        raise HTTPException(404, "Order not found")
    rows = db.scalars(select(StatusHistory).where(StatusHistory.order_id == order_id).order_by(StatusHistory.id)).all()
    return [{"old_status": row.old_status, "new_status": row.new_status,
             "changed_at": row.changed_at, "changed_by": row.changed_by} for row in rows]


@router.get("/{order_id}/timeline")
def timeline(order_id: int, db: Db, _actor: Annotated[User, Depends(require("orders.view"))],
             limit: int = 100, offset: int = 0) -> dict:
    if db.get(Order, order_id) is None:
        raise HTTPException(404, "Order not found")
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(422, "Invalid pagination")
    comments = db.scalars(select(Comment).options(joinedload(Comment.author), selectinload(Comment.mentions))
                          .where(Comment.order_id == order_id).order_by(Comment.created_at, Comment.id)).all()
    statuses = db.scalars(select(StatusHistory).options(joinedload(StatusHistory.changed_by_user))
                          .where(StatusHistory.order_id == order_id)).all()
    status_labels = {row.name: row.display_name for row in db.scalars(select(InternalStatus)).all()}
    events = db.scalars(select(OrderTimelineEvent).options(joinedload(OrderTimelineEvent.actor))
                        .where(OrderTimelineEvent.order_id == order_id)).all()
    items = [
        {"id": f"comment-{row.id}", "kind": "comment", "body": row.body,
         "author": row.author.display_name if row.author else "Удалённый пользователь",
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
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total}


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
    if order.internal_status not in ("NEW", "QUEUED", "SENT_TO_PRODUCTION"):
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
    return order_data(db.scalar(order_query().where(Order.id == order_id)))


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
    return order_data(db.scalar(order_query().where(Order.id == order_id)))


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
    return order_data(db.scalar(order_query().where(Order.id == order_id)))
