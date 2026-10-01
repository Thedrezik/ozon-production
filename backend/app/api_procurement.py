from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.auth import Db, require
from app.models import (
    AuditLog,
    Blocker,
    Order,
    OrderTimelineEvent,
    ProcurementBlockerLink,
    ProcurementHistory,
    ProcurementOrderLink,
    ProcurementTask,
    User,
    utc_now,
)
from app.notifications import emit, manager_ids
from app.procurement import (
    NEXT_STATUSES,
    STATUSES,
    is_overdue,
    sync_all_overdue,
    sync_overdue,
)
from app.rbac import user_permissions

router = APIRouter(prefix="/api/procurement")


class CreateInput(BaseModel):
    material_name: str = Field(min_length=1, max_length=240)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=5000)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    responsible_user_id: int | None = None
    needed_by: datetime | None = None
    order_ids: list[int] = Field(default_factory=list, max_length=100)
    blocker_ids: list[int] = Field(default_factory=list, max_length=100)


class UpdateInput(BaseModel):
    status: Literal["ORDERED", "PURCHASED", "DELIVERED", "CANCELLED"]
    responsible_user_id: int | None = None


class LinkInput(BaseModel):
    order_ids: list[int] = Field(default_factory=list, max_length=100)
    blocker_ids: list[int] = Field(default_factory=list, max_length=100)


class ResponsibleInput(BaseModel):
    responsible_user_id: int | None


def fetch(db: Db, task_id: int) -> ProcurementTask:
    row = db.scalar(select(ProcurementTask).options(
        selectinload(ProcurementTask.responsible_user), selectinload(ProcurementTask.order_links),
        selectinload(ProcurementTask.blocker_links)).where(ProcurementTask.id == task_id))
    if row is None:
        raise HTTPException(404, "Procurement task not found")
    return row


def data(row: ProcurementTask) -> dict:
    return {"id": row.id, "material_name": row.material_name, "quantity": row.quantity,
            "unit": row.unit, "description": row.description, "severity": row.severity,
            "status": row.status, "responsible_user_id": row.responsible_user_id,
            "responsible_name": row.responsible_user.display_name if row.responsible_user else None,
            "needed_by": row.needed_by, "is_overdue": is_overdue(row),
            "created_at": row.created_at, "updated_at": row.updated_at,
            "ordered_at": row.ordered_at, "purchased_at": row.purchased_at,
            "delivered_at": row.delivered_at, "cancelled_at": row.cancelled_at,
            "order_ids": [link.order_id for link in row.order_links],
            "blocker_ids": [link.blocker_id for link in row.blocker_links]}


def validate_assignee(db: Db, user_id: int | None) -> None:
    if user_id is None:
        return
    user = db.get(User, user_id)
    if user is None or not user.is_active or "procurement.manage" not in user_permissions(user):
        raise HTTPException(422, "Responsible user must be active and able to manage procurement")


def linked_ids(db: Db, order_ids: list[int], blocker_ids: list[int]) -> tuple[list[int], list[int]]:
    orders = set(order_ids)
    blockers = set(blocker_ids)
    found_blockers = {row.id: row.order_id for row in db.scalars(select(Blocker).where(Blocker.id.in_(blockers))).all()}
    if set(found_blockers) != blockers:
        raise HTTPException(422, "Unknown blocker")
    orders.update(found_blockers.values())
    if orders and set(db.scalars(select(Order.id).where(Order.id.in_(orders))).all()) != orders:
        raise HTTPException(422, "Unknown order")
    return sorted(orders), sorted(blockers)


@router.get("")
def list_tasks(db: Db, actor: Annotated[User, Depends(require("procurement.view"))],
               mine: bool = False, status: str | None = None, overdue: bool = False,
               limit: int = 50, offset: int = 0) -> dict:
    if (status is not None and status not in STATUSES) or not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Invalid filter")
    sync_all_overdue(db)
    db.commit()
    query = select(ProcurementTask)
    if mine:
        query = query.where(ProcurementTask.responsible_user_id == actor.id)
    if status:
        query = query.where(ProcurementTask.status == status)
    if overdue:
        query = query.where(ProcurementTask.status.in_(("NEW", "ORDERED", "PURCHASED")),
                            ProcurementTask.needed_by < utc_now())
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.options(selectinload(ProcurementTask.responsible_user),
                                    selectinload(ProcurementTask.order_links),
                                    selectinload(ProcurementTask.blocker_links))
                      .order_by(ProcurementTask.needed_by.asc().nulls_last(), ProcurementTask.id.desc())
                      .limit(limit).offset(offset)).all()
    return {"items": [data(row) for row in rows], "total": total}


@router.get("/{task_id}")
def get_task(task_id: int, db: Db, _actor: Annotated[User, Depends(require("procurement.view"))]) -> dict:
    return data(fetch(db, task_id))


@router.get("/{task_id}/history")
def history(task_id: int, db: Db, _actor: Annotated[User, Depends(require("procurement.view"))]) -> dict:
    fetch(db, task_id)
    rows = db.scalars(select(ProcurementHistory).options(selectinload(ProcurementHistory.actor))
                      .where(ProcurementHistory.task_id == task_id).order_by(ProcurementHistory.id)).all()
    return {"items": [{"old_status": row.old_status, "new_status": row.new_status,
                       "description": row.description, "created_at": row.created_at,
                       "actor_name": row.actor.display_name if row.actor else None} for row in rows]}


@router.post("", status_code=201)
def create_task(payload: CreateInput, db: Db, request: Request,
                actor: Annotated[User, Depends(require("procurement.create"))]) -> dict:
    name, unit = payload.material_name.strip(), payload.unit.strip()
    if not name or not unit:
        raise HTTPException(422, "Material and unit cannot be blank")
    if payload.needed_by is not None and payload.needed_by.utcoffset() is None:
        raise HTTPException(422, "Needed-by must include a timezone")
    validate_assignee(db, payload.responsible_user_id)
    order_ids, blocker_ids = linked_ids(db, payload.order_ids, payload.blocker_ids)
    row = ProcurementTask(material_name=name, quantity=payload.quantity, unit=unit,
                          description=payload.description.strip(), severity=payload.severity,
                          responsible_user_id=payload.responsible_user_id, needed_by=payload.needed_by,
                          status="NEW", order_links=[ProcurementOrderLink(order_id=i) for i in order_ids],
                          blocker_links=[ProcurementBlockerLink(blocker_id=i) for i in blocker_ids])
    db.add(row)
    db.flush()
    db.add(ProcurementHistory(task_id=row.id, actor_user_id=actor.id, old_status=None,
                              new_status="NEW", description="Закупка создана"))
    for order_id in order_ids:
        db.add(OrderTimelineEvent(order_id=order_id, event_type="procurement_created",
                                  description=f"Закупка #{row.id}: {name}", actor_user_id=actor.id))
    db.add(AuditLog(actor_user_id=actor.id, action="procurement.created", detail=f"#{row.id}"))
    sync_overdue(db, row)
    recipients = manager_ids(db)
    if row.responsible_user_id is not None:
        recipients.append(row.responsible_user_id)
    emit(db, type="PROCUREMENT_CREATED", event_key=f"procurement:{row.id}",
         user_ids=recipients, title=f"Новая закупка: {name}",
         body=f"{row.quantity} {unit}", url="/procurement")
    db.commit()
    for order_id in order_ids:
        request.app.state.order_events.publish(order_id)
    return data(fetch(db, row.id))


@router.post("/{task_id}/links")
def add_links(task_id: int, payload: LinkInput, db: Db, request: Request,
              actor: Annotated[User, Depends(require("procurement.manage"))]) -> dict:
    row = db.scalar(select(ProcurementTask).where(ProcurementTask.id == task_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Procurement task not found")
    if row.status in ("DELIVERED", "CANCELLED"):
        raise HTTPException(409, "Procurement task is closed")
    order_ids, blocker_ids = linked_ids(db, payload.order_ids, payload.blocker_ids)
    existing_orders = {link.order_id for link in row.order_links}
    existing_blockers = {link.blocker_id for link in row.blocker_links}
    added_orders = set(order_ids) - existing_orders
    added_blockers = set(blocker_ids) - existing_blockers
    if not added_orders and not added_blockers:
        return data(fetch(db, task_id))
    row.order_links.extend(ProcurementOrderLink(order_id=i) for i in sorted(added_orders))
    row.blocker_links.extend(ProcurementBlockerLink(blocker_id=i) for i in sorted(added_blockers))
    row.updated_at = utc_now()
    db.add(ProcurementHistory(task_id=row.id, actor_user_id=actor.id, old_status=row.status,
                              new_status=row.status, description="Добавлены связи с заказами и проблемами"))
    for order_id in added_orders:
        db.add(OrderTimelineEvent(order_id=order_id, event_type="procurement_linked",
                                  description=f"Закупка #{row.id}: {row.material_name}", actor_user_id=actor.id))
    db.add(AuditLog(actor_user_id=actor.id, action="procurement.linked", detail=f"#{row.id}"))
    sync_overdue(db, row)
    db.commit()
    for order_id in added_orders:
        request.app.state.order_events.publish(order_id)
    return data(fetch(db, task_id))


@router.patch("/{task_id}")
def update_task(task_id: int, payload: UpdateInput, db: Db, request: Request,
                actor: Annotated[User, Depends(require("procurement.manage"))]) -> dict:
    row = db.scalar(select(ProcurementTask).where(ProcurementTask.id == task_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Procurement task not found")
    if payload.status not in NEXT_STATUSES[row.status]:
        raise HTTPException(409, "Invalid procurement transition")
    validate_assignee(db, payload.responsible_user_id)
    if payload.responsible_user_id is not None:
        row.responsible_user_id = payload.responsible_user_id
    old_status = row.status
    row.status = payload.status
    row.updated_at = utc_now()
    setattr(row, {"ORDERED": "ordered_at", "PURCHASED": "purchased_at",
                  "DELIVERED": "delivered_at", "CANCELLED": "cancelled_at"}[payload.status], row.updated_at)
    db.add(ProcurementHistory(task_id=row.id, actor_user_id=actor.id, old_status=old_status,
                              new_status=row.status, description=f"Статус: {old_status} → {row.status}"))
    for link in row.order_links:
        db.add(OrderTimelineEvent(order_id=link.order_id, event_type="procurement_updated",
                                  description=f"Закупка #{row.id}: {row.status}", actor_user_id=actor.id))
    db.add(AuditLog(actor_user_id=actor.id, action="procurement.updated", detail=f"#{row.id} {row.status}"))
    sync_overdue(db, row)
    order_ids = [link.order_id for link in row.order_links]
    db.commit()
    for order_id in order_ids:
        request.app.state.order_events.publish(order_id)
    return data(fetch(db, task_id))


@router.put("/{task_id}/responsible")
def set_responsible(task_id: int, payload: ResponsibleInput, db: Db,
                    actor: Annotated[User, Depends(require("procurement.manage"))]) -> dict:
    row = db.scalar(select(ProcurementTask).where(ProcurementTask.id == task_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Procurement task not found")
    if row.status in ("DELIVERED", "CANCELLED"):
        raise HTTPException(409, "Procurement task is closed")
    validate_assignee(db, payload.responsible_user_id)
    if row.responsible_user_id != payload.responsible_user_id:
        previous = row.responsible_user_id
        row.responsible_user_id = payload.responsible_user_id
        row.updated_at = utc_now()
        db.add(ProcurementHistory(task_id=row.id, actor_user_id=actor.id, old_status=row.status,
                                  new_status=row.status,
                                  description=f"Ответственный: {previous or '—'} → {row.responsible_user_id or '—'}"))
        db.add(AuditLog(actor_user_id=actor.id, action="procurement.assigned", detail=f"#{row.id}"))
        db.commit()
    return data(fetch(db, task_id))
