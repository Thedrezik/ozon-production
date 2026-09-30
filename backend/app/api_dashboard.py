"""Small manager snapshot built from the existing priority and risk services."""

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from app.api_money_at_risk import _snapshot
from app.api_orders import priority_for, priority_settings, production_profiles
from app.auth import Db, require
from app.models import Assignment, ManagerTask, Order, User, utc_now
from app.procurement import sync_all_overdue
from app.rbac import user_permissions

router = APIRouter(prefix="/api/dashboard")
ACTIVE = ("DONE", "CANCELLED", "HANDED_TO_SHIPPING")


@router.get("")
def dashboard(db: Db, request: Request,
              actor: Annotated[User, Depends(require("analytics.view"))]) -> dict:
    now = utc_now()
    orders = db.scalars(select(Order).options(selectinload(Order.items),
                                                joinedload(Order.assignment).joinedload(Assignment.user))
                        .where(Order.internal_status.notin_(ACTIVE))).all()
    profiles = production_profiles(db)
    settings = priority_settings(db)
    ranked = [(order, priority_for(order, profiles, settings, now)) for order in orders]
    critical = [pair for pair in ranked if pair[1]["level"] == "P0"]
    blocked = sum(order.internal_status == "BLOCKED" for order in orders)
    ready = sum(order.internal_status == "READY_TO_SHIP" for order in orders)
    overdue = db.scalar(select(func.count()).select_from(Order).where(
        Order.shipment_deadline < now, Order.internal_status.notin_(("DONE", "CANCELLED")))) or 0
    sync_all_overdue(db)
    db.commit()
    task_counts = dict(db.execute(select(ManagerTask.status, func.count()).group_by(ManagerTask.status)).all())
    tasks = db.scalars(select(ManagerTask).options(joinedload(ManagerTask.order))
                       .where(ManagerTask.status.in_(("OPEN", "IN_PROGRESS")))
                       .order_by(ManagerTask.created_at.desc(), ManagerTask.id.desc()).limit(5)).all()
    workload = Counter(order.assignment.user_id for order in orders if order.assignment)
    names = {order.assignment.user_id: order.assignment.user.display_name for order in orders
             if order.assignment}
    attention = sorted((pair for pair in ranked if pair[1]["level"] == "P0" or
                        pair[0].internal_status == "BLOCKED"),
                       key=lambda pair: (pair[1]["level"] != "P0", pair[0].shipment_deadline))[:5]
    result = {
        "as_of": now, "critical": len(critical), "blocked": blocked, "ready": ready,
        "overdue": overdue, "manager_tasks": sum(task_counts.get(key, 0) for key in ("OPEN", "IN_PROGRESS")),
        "attention": [{"id": order.id, "posting_number": order.posting_number,
                       "priority_level": priority["level"], "reason": priority["reasons"][0]
                       if priority["reasons"] else "Требует внимания"}
                      for order, priority in attention],
        "tasks": [{"id": task.id, "title": task.title, "severity": task.severity,
                   "posting_number": task.order.posting_number if task.order else None}
                  for task in tasks],
        "workload": [{"id": user_id, "name": names[user_id], "active_orders": count}
                     for user_id, count in workload.most_common(5)],
    }
    if "finance.view" in user_permissions(actor):
        risk = _snapshot(db, request, now)
        result["money_at_risk"] = {"total": risk["total"], "buckets": [
            {key: value for key, value in bucket.items() if key != "orders"} for bucket in risk["buckets"]]}
    return result
