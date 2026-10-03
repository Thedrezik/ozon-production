"""Small, transactional rule boundary for manager tasks.

Callers supply a stable source ID. The database constraint on (source_type, source_id)
is the final guard against duplicate event delivery.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.features import db_enabled
from app.models import ManagerTask, utc_now

SOURCE_TYPES = frozenset({
    "BLOCKER", "DEADLINE_RISK", "STALLED_ORDER", "UNASSIGNED_ORDER",
    "PROCUREMENT_OVERDUE", "OZON_CANCELLED_AFTER_START", "OZON_SYNC_ERROR",
    "API_KEY_EXPIRING",
    "OZON_RECONCILIATION_ERROR",
})
SEVERITIES = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
ACTIVE_STATUSES = frozenset({"OPEN", "IN_PROGRESS"})
STATUSES = ACTIVE_STATUSES | {"RESOLVED", "DISMISSED"}


def ensure_task(db: Session, *, source_type: str, source_id: int, order_id: int | None,
                title: str, description: str, severity: str, due_at=None,
                prefetched: dict[int, ManagerTask] | None = None) -> ManagerTask | None:
    if not db_enabled(db, "manager_tasks"):
        return None
    if source_type not in SOURCE_TYPES or severity not in SEVERITIES or source_id < 1:
        raise ValueError("Invalid manager task source or severity")
    task = (prefetched.get(source_id) if prefetched is not None else
            db.scalar(select(ManagerTask).where(ManagerTask.source_type == source_type,
                                               ManagerTask.source_id == source_id)))
    if task is None:
        task = ManagerTask(source_type=source_type, source_id=source_id, order_id=order_id,
                           title=title, description=description, severity=severity,
                           status="OPEN", due_at=due_at)
        try:
            with db.begin_nested():
                db.add(task)
                db.flush()
        except IntegrityError:
            task = db.scalar(select(ManagerTask).where(ManagerTask.source_type == source_type,
                                                        ManagerTask.source_id == source_id))
            if task is None:
                raise
    elif task.status in ACTIVE_STATUSES:
        task.title, task.description, task.severity, task.due_at = title, description, severity, due_at
    return task


def resolve_source(db: Session, *, source_type: str, source_id: int) -> ManagerTask | None:
    if not db_enabled(db, "manager_tasks"):
        return None
    task = db.scalar(select(ManagerTask).where(ManagerTask.source_type == source_type,
                                                ManagerTask.source_id == source_id))
    if task is not None and task.status in ACTIVE_STATUSES:
        task.status = "RESOLVED"
        task.resolved_at = utc_now()
    return task


def sync_rule(db: Session, *, active: bool, source_type: str, source_id: int,
              order_id: int | None, title: str, description: str,
              severity: str, due_at=None, prefetched: dict[int, ManagerTask] | None = None) -> ManagerTask | None:
    """Apply one evaluated rule inside the caller's transaction.

    Integration and scheduler callers evaluate their own source data, then call this
    with a stable source ID. Inactive causes close only for a still-active task.
    """
    if active:
        return ensure_task(db, source_type=source_type, source_id=source_id,
                           order_id=order_id, title=title, description=description,
                           severity=severity, due_at=due_at, prefetched=prefetched)
    return resolve_source(db, source_type=source_type, source_id=source_id)
