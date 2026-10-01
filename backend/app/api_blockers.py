from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.auth import Db, require
from app.manager_tasks import ensure_task, resolve_source
from app.models import (
    AuditLog,
    Blocker,
    BlockerType,
    Order,
    OrderTimelineEvent,
    User,
    utc_now,
)
from app.notifications import emit, manager_ids
from app.orders import transition

router = APIRouter(prefix="/api/blockers")
ACTIVE = ("OPEN", "IN_PROGRESS")
BLOCKABLE = ("QUEUED", "SENT_TO_PRODUCTION", "IN_PRODUCTION", "QUALITY_CHECK")


class BlockerInput(BaseModel):
    order_id: int
    type_code: str
    description: str = Field(min_length=1, max_length=5000)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    assigned_to: int | None = None
    expected_resolution_at: datetime | None = None


class BlockerUpdate(BaseModel):
    status: Literal["IN_PROGRESS", "RESOLVED", "CANCELLED"]
    assigned_to: int | None = None


def data(row: Blocker) -> dict:
    return {
        "id": row.id, "order_id": row.order_id, "posting_number": row.order.posting_number,
        "type_code": row.type_code, "description": row.description, "severity": row.severity,
        "status": row.status, "creator_user_id": row.creator_user_id,
        "assigned_to": row.assigned_to, "expected_resolution_at": row.expected_resolution_at,
        "created_at": row.created_at, "updated_at": row.updated_at, "resolved_at": row.resolved_at,
        "previous_production_status": row.previous_production_status,
        "photos": [],
    }


@router.get("/types")
def types(db: Db, _actor: Annotated[User, Depends(require("orders.view"))]) -> list[dict]:
    return [{"code": row.code, "display_name": row.display_name}
            for row in db.scalars(select(BlockerType).order_by(BlockerType.code))]


@router.get("")
def list_blockers(db: Db, _actor: Annotated[User, Depends(require("orders.view"))],
                  order_id: int | None = None, status: str | None = None,
                  limit: int = 50, offset: int = 0) -> dict:
    if status is not None and status not in ("OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"):
        raise HTTPException(422, "Unknown blocker status")
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Invalid pagination")
    query = select(Blocker).options(joinedload(Blocker.order))
    if order_id is not None:
        query = query.where(Blocker.order_id == order_id)
    if status:
        query = query.where(Blocker.status == status)
    rows = db.scalars(query.order_by(Blocker.created_at.desc(), Blocker.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [data(row) for row in rows]}


@router.post("", status_code=201)
def create_blocker(payload: BlockerInput, db: Db, request: Request,
                   actor: Annotated[User, Depends(require("blockers.create"))]) -> dict:
    order = db.scalar(select(Order).where(Order.id == payload.order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "Order not found")
    if order.internal_status not in (*BLOCKABLE, "BLOCKED"):
        raise HTTPException(409, "Order cannot be blocked")
    if db.get(BlockerType, payload.type_code) is None:
        raise HTTPException(422, "Unknown blocker type")
    description = payload.description.strip()
    if not description:
        raise HTTPException(422, "Description cannot be blank")
    if payload.expected_resolution_at is not None and payload.expected_resolution_at.utcoffset() is None:
        raise HTTPException(422, "Expected resolution must include a timezone")
    if payload.assigned_to is not None:
        target = db.get(User, payload.assigned_to)
        if target is None or not target.is_active:
            raise HTTPException(422, "Assignee must be active")
    previous = order.internal_status if order.internal_status != "BLOCKED" else None
    row = Blocker(order_id=order.id, type_code=payload.type_code, description=description,
                  severity=payload.severity, status="OPEN", creator_user_id=actor.id,
                  assigned_to=payload.assigned_to,
                  expected_resolution_at=payload.expected_resolution_at,
                  previous_production_status=previous)
    db.add(row)
    db.flush()
    ensure_task(db, source_type="BLOCKER", source_id=row.id, order_id=order.id,
                title=f"Проблема заказа {order.posting_number}", description=description,
                severity=payload.severity, due_at=payload.expected_resolution_at)
    emit(db, type="BLOCKER_CREATED", event_key=f"blocker:{row.id}",
         user_ids=manager_ids(db), title=f"Проблема заказа {order.posting_number}",
         body=description, url=f"/orders/{order.id}")
    if previous:
        transition(db, order, "BLOCKED", actor.id)
    db.add(OrderTimelineEvent(order_id=order.id, event_type="blocker_created",
                              description=f"Проблема #{row.id}: {description}", actor_user_id=actor.id))
    db.add(AuditLog(actor_user_id=actor.id, action="blocker.created", detail=f"{order.posting_number} #{row.id}"))
    db.commit()
    request.app.state.order_events.publish(order.id)
    return data(db.scalar(select(Blocker).options(joinedload(Blocker.order)).where(Blocker.id == row.id)))


@router.patch("/{blocker_id}")
def update_blocker(blocker_id: int, payload: BlockerUpdate, db: Db, request: Request,
                   actor: Annotated[User, Depends(require("blockers.resolve"))]) -> dict:
    order_id = db.scalar(select(Blocker.order_id).where(Blocker.id == blocker_id))
    if order_id is None:
        raise HTTPException(404, "Blocker not found")
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    row = db.scalar(select(Blocker).where(Blocker.id == blocker_id).with_for_update())
    if row.status not in ACTIVE:
        raise HTTPException(409, "Blocker already closed")
    if payload.status == "IN_PROGRESS" and row.status != "OPEN":
        raise HTTPException(409, "Blocker already in progress")
    if payload.assigned_to is not None:
        target = db.get(User, payload.assigned_to)
        if target is None or not target.is_active:
            raise HTTPException(422, "Assignee must be active")
        row.assigned_to = target.id
    row.status = payload.status
    row.updated_at = utc_now()
    if payload.status not in ACTIVE:
        row.resolved_at = row.updated_at
        resolve_source(db, source_type="BLOCKER", source_id=row.id)
        if payload.status == "RESOLVED":
            emit(db, type="BLOCKER_RESOLVED", event_key=f"blocker:{row.id}",
                 user_ids=manager_ids(db), title=f"Проблема устранена: {order.posting_number}",
                 body=row.description, url=f"/orders/{order.id}")
        db.flush()
        remaining = db.scalar(select(Blocker.id).where(Blocker.order_id == order_id,
                                                         Blocker.status.in_(ACTIVE)).limit(1))
        if remaining is None and order.internal_status == "BLOCKED":
            first = db.scalar(select(Blocker.previous_production_status).where(
                Blocker.order_id == order_id, Blocker.previous_production_status.is_not(None)
            ).order_by(Blocker.id.desc()).limit(1))
            if first:
                transition(db, order, first, actor.id)
    db.add(OrderTimelineEvent(order_id=order_id, event_type="blocker_updated",
                              description=f"Проблема #{row.id}: {payload.status}", actor_user_id=actor.id))
    db.add(AuditLog(actor_user_id=actor.id, action="blocker.updated", detail=f"{order.posting_number} #{row.id} {payload.status}"))
    db.commit()
    request.app.state.order_events.publish(order_id)
    return data(db.scalar(select(Blocker).options(joinedload(Blocker.order)).where(Blocker.id == blocker_id)))
