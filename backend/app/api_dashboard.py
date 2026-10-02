"""Small manager snapshot built from the existing priority and risk services."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api_money_at_risk import _snapshot
from app.api_orders import priority_for, priority_settings, production_profiles
from app.auth import Db, require
from app.models import Assignment, ManagerTask, Order, User, utc_now
from app.performance import active_orders, order_batches
from app.procurement import sync_all_overdue
from app.rbac import user_permissions
from app.tariff import parse_normalized_steps

router = APIRouter(prefix="/api/dashboard")
ACTIVE = ("DONE", "CANCELLED", "HANDED_TO_SHIPPING")


@router.get("")
def dashboard(db: Db, request: Request,
              actor: Annotated[User, Depends(require("analytics.view"))]) -> dict:
    now = utc_now()
    # Commit before reading projections: commit expires ORM state and otherwise
    # causes thousands of lazy reloads while rendering the response.
    sync_all_overdue(db)
    db.commit()
    settings = priority_settings(db)
    critical = 0
    attention = []
    can_view_finance = "finance.view" in user_permissions(actor)
    def rows():
        nonlocal critical
        for batch in order_batches(db, active_orders()):
            profiles = production_profiles(db, batch)
            for order in batch:
                priority = priority_for(order, profiles, settings, now)
                critical += priority["level"] == "P0"
                if priority["level"] == "P0" or order.internal_status == "BLOCKED":
                    attention.append((priority["level"] != "P0", order.shipment_deadline,
                                      order.id, {"id": order.id, "posting_number": order.posting_number,
                                      "priority_level": priority["level"], "reason": priority["reasons"][0]
                                      if priority["reasons"] else "Требует внимания"}))
                    attention.sort(key=lambda row: row[:3])
                    del attention[5:]
                yield ({"id": order.id, "posting_number": order.posting_number,
                        "internal_status": order.internal_status},
                       parse_normalized_steps(order.tariff_steps) if can_view_finance and order.tariff_steps else (),
                       priority)
    if can_view_finance:
        risk = _snapshot(db, request, now, source_rows=rows())
    else:
        for _row in rows():
            pass
    counts = dict(db.execute(select(Order.internal_status, func.count()).where(
        Order.internal_status.notin_(ACTIVE), Order.ozon_status != "cancelled")
        .group_by(Order.internal_status)).all())
    blocked, ready = counts.get("BLOCKED", 0), counts.get("READY_TO_SHIP", 0)
    overdue = db.scalar(select(func.count()).select_from(Order).where(
        Order.shipment_deadline < now, Order.internal_status.notin_(ACTIVE),
        Order.ozon_status != "cancelled")) or 0
    task_counts = dict(db.execute(select(ManagerTask.status, func.count()).group_by(ManagerTask.status)).all())
    tasks = db.scalars(select(ManagerTask).options(joinedload(ManagerTask.order))
                       .where(ManagerTask.status.in_(("OPEN", "IN_PROGRESS")))
                       .order_by(ManagerTask.created_at.desc(), ManagerTask.id.desc()).limit(5)).all()
    workload = db.execute(select(User.id, User.display_name, func.count().label("count"))
        .join(Assignment, Assignment.user_id == User.id).join(Order, Order.id == Assignment.order_id)
        .where(Order.internal_status.notin_(ACTIVE), Order.ozon_status != "cancelled")
        .group_by(User.id, User.display_name).order_by(func.count().desc(), User.id).limit(5)).all()
    result = {
        "as_of": now, "critical": critical, "blocked": blocked, "ready": ready,
        "overdue": overdue, "manager_tasks": sum(task_counts.get(key, 0) for key in ("OPEN", "IN_PROGRESS")),
        "attention": [row[3] for row in attention],
        "tasks": [{"id": task.id, "title": task.title, "severity": task.severity,
                   "posting_number": task.order.posting_number if task.order else None}
                  for task in tasks],
        "workload": [{"id": user_id, "name": name, "active_orders": count}
                     for user_id, name, count in workload],
    }
    if can_view_finance:
        result["money_at_risk"] = {"total": risk["total"], "buckets": [
            {key: value for key, value in bucket.items() if key != "orders"} for bucket in risk["buckets"]]}
    return result
