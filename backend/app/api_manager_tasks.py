from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.auth import Db, require
from app.manager_tasks import ACTIVE_STATUSES, SEVERITIES, SOURCE_TYPES, STATUSES
from app.models import AuditLog, ManagerTask, User, utc_now
from app.procurement import sync_all_overdue
from app.rbac import user_permissions

router = APIRouter(prefix="/api/manager-tasks")


def task_data(row: ManagerTask) -> dict:
    return {
        "id": row.id, "source_type": row.source_type, "source_id": row.source_id,
        "order_id": row.order_id, "posting_number": row.order.posting_number if row.order else None,
        "title": row.title, "description": row.description, "severity": row.severity,
        "status": row.status, "assigned_to": row.assigned_to,
        "assignee_name": row.assignee.display_name if row.assignee else None,
        "created_at": row.created_at, "due_at": row.due_at, "resolved_at": row.resolved_at,
    }


@router.get("")
def list_tasks(db: Db, _actor: Annotated[User, Depends(require("manager_tasks.view"))],
               task_id: int | None = None, severity: str | None = None, source_type: str | None = None,
               assigned_to: int | None = None, status: str | None = None,
               limit: int = 50, offset: int = 0) -> dict:
    if ((severity is not None and severity not in SEVERITIES)
            or (source_type is not None and source_type not in SOURCE_TYPES)
            or (status is not None and status not in (*STATUSES, "ACTIVE"))
            or not 1 <= limit <= 100 or offset < 0):
        raise HTTPException(422, "Invalid filter")
    sync_all_overdue(db)
    db.commit()
    query = select(ManagerTask)
    if task_id is not None:
        query = query.where(ManagerTask.id == task_id)
    if severity:
        query = query.where(ManagerTask.severity == severity)
    if source_type:
        query = query.where(ManagerTask.source_type == source_type)
    if assigned_to is not None:
        query = query.where(ManagerTask.assigned_to == assigned_to)
    if status == "ACTIVE":
        query = query.where(ManagerTask.status.in_(ACTIVE_STATUSES))
    elif status:
        query = query.where(ManagerTask.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.options(joinedload(ManagerTask.order), joinedload(ManagerTask.assignee))
                      .order_by(ManagerTask.created_at.desc(), ManagerTask.id.desc())
                      .limit(limit).offset(offset)).all()
    return {"items": [task_data(row) for row in rows], "total": total}


class TaskUpdate(BaseModel):
    status: Literal["IN_PROGRESS", "RESOLVED", "DISMISSED"]
    assigned_to: int | None = None


@router.patch("/{task_id}")
def update_task(task_id: int, payload: TaskUpdate, db: Db, request: Request,
                actor: Annotated[User, Depends(require("manager_tasks.manage"))]) -> dict:
    task = db.scalar(select(ManagerTask).where(ManagerTask.id == task_id).with_for_update())
    if task is None:
        raise HTTPException(404, "Manager task not found")
    if task.status not in ACTIVE_STATUSES:
        raise HTTPException(409, "Manager task already closed")
    if payload.status == "IN_PROGRESS" and task.status != "OPEN":
        raise HTTPException(409, "Manager task already in progress")
    if task.source_type in ("BLOCKER", "PROCUREMENT_OVERDUE") and payload.status == "RESOLVED":
        raise HTTPException(409, "Resolve the source first")
    if payload.assigned_to is not None:
        assignee = db.get(User, payload.assigned_to)
        if assignee is None or not assignee.is_active or "manager_tasks.manage" not in user_permissions(assignee):
            raise HTTPException(422, "Assignee must be an active manager")
        task.assigned_to = assignee.id
    elif payload.status == "IN_PROGRESS" and task.assigned_to is None:
        task.assigned_to = actor.id
    task.status = payload.status
    if payload.status not in ACTIVE_STATUSES:
        task.resolved_at = utc_now()
    db.add(AuditLog(actor_user_id=actor.id, action="manager_task.updated",
                    detail=f"{task.id} {payload.status}"))
    db.commit()
    request.app.state.order_events.publish(task.order_id or 0)
    return task_data(db.scalar(select(ManagerTask).options(joinedload(ManagerTask.order),
                                      joinedload(ManagerTask.assignee)).where(ManagerTask.id == task_id)))
