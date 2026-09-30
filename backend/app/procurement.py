from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.manager_tasks import sync_rule
from app.models import ProcurementTask, utc_now

OPEN_STATUSES = ("NEW", "ORDERED", "PURCHASED")
STATUSES = (*OPEN_STATUSES, "DELIVERED", "CANCELLED")
NEXT_STATUSES = {
    "NEW": ("ORDERED", "PURCHASED", "DELIVERED", "CANCELLED"),
    "ORDERED": ("PURCHASED", "DELIVERED", "CANCELLED"),
    "PURCHASED": ("DELIVERED", "CANCELLED"),
    "DELIVERED": (), "CANCELLED": (),
}


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def is_overdue(task: ProcurementTask, now: datetime | None = None) -> bool:
    return (task.status in OPEN_STATUSES and task.needed_by is not None
            and utc(task.needed_by) < (now or utc_now()))


def sync_overdue(db: Session, task: ProcurementTask) -> None:
    active = is_overdue(task) and task.severity in ("HIGH", "CRITICAL")
    sync_rule(db, active=active, source_type="PROCUREMENT_OVERDUE", source_id=task.id,
              order_id=task.order_links[0].order_id if task.order_links else None,
              title=f"Просрочена закупка: {task.material_name}",
              description=f"Материал {task.material_name}: {task.quantity} {task.unit}. {task.description}".strip(),
              severity=task.severity, due_at=task.needed_by)


def sync_all_overdue(db: Session) -> None:
    # A small database query supplies the manager queue without another worker.
    tasks = db.scalars(select(ProcurementTask).options(selectinload(ProcurementTask.order_links)).where(
        ProcurementTask.severity.in_(("HIGH", "CRITICAL")),
        ProcurementTask.status.in_(OPEN_STATUSES), ProcurementTask.needed_by < utc_now())).all()
    for task in tasks:
        sync_overdue(db, task)
