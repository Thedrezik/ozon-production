"""Small manager snapshot built from the existing priority and risk services."""

from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api_money_at_risk import _snapshot
from app.api_orders import (
    priority_for,
    priority_settings,
    production_profiles,
    tariff_for,
    visible_priority,
)
from app.auth import Db, require
from app.features import db_enabled
from app.models import Assignment, Blocker, ManagerTask, Order, User, utc_now
from app.ozon_status import OZON_CANCELLED_STATUSES
from app.performance import active_orders, order_batches
from app.priority import sort_key
from app.procurement import sync_all_overdue
from app.rbac import user_permissions
from app.tariff import parse_normalized_steps

router = APIRouter(prefix="/api/dashboard")
ACTIVE = ("DONE", "CANCELLED", "HANDED_TO_SHIPPING")


@router.get("")
def dashboard(db: Db, request: Request,
              actor: Annotated[User, Depends(require("orders.view"))]) -> dict:
    now = utc_now()
    # Commit before reading projections: commit expires ORM state and otherwise
    # causes thousands of lazy reloads while rendering the response.
    if db_enabled(db, "procurement"):
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
                priority = visible_priority(priority, can_view_finance)
                critical += priority["level"] == "P0"
                if order.internal_status != "READY_TO_SHIP":
                    tariff = tariff_for(order, now)
                    attention.append((sort_key(priority, order.id), order.shipment_deadline,
                                      order.id, {"id": order.id, "posting_number": order.posting_number,
                                      "priority_level": priority["level"], "reason": priority["reasons"][0]
                                      if priority["reasons"] else "Требует внимания",
                                      "reasons": priority["reasons"],
                                      "internal_status": order.internal_status,
                                      "items": [{"product_name": item.product_name, "article": item.offer_id or item.sku,
                                                 "quantity": item.quantity} for item in order.items],
                                      "next_tariff_at": tariff["next"]["starts_at"] if tariff and tariff["next"] else None,
                                      "financial_delta": str(tariff["delta_to_next_tariff"]) if can_view_finance and tariff and tariff["delta_to_next_tariff"] is not None else None,
                                      "currency": tariff["next"]["currency"] if tariff and tariff["next"] else None,
                                      "shipment_deadline": order.shipment_deadline.replace(tzinfo=timezone.utc)}))
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
    # Enrich only the selected focus, not every active order or a client-side N+1.
    if attention:
        focus = attention[0][3]
        order = db.scalar(select(Order).options(joinedload(Order.assignment).joinedload(Assignment.user))
                          .where(Order.id == focus["id"]))
        focus["assigned_user"] = ({"id": order.assignment.user.id,
                                   "display_name": order.assignment.user.display_name}
                                  if order.assignment else None)
        focus["problems"] = list(db.scalars(select(Blocker.description).where(
            Blocker.order_id == order.id, Blocker.status.in_(("OPEN", "IN_PROGRESS")))
            .order_by(Blocker.created_at, Blocker.id).limit(3)))
        if can_view_finance:
            focus_risk = _snapshot(db, request, now, source_rows=[(
                {"id": order.id, "posting_number": order.posting_number, "internal_status": order.internal_status},
                parse_normalized_steps(order.tariff_steps) if order.tariff_steps else (),
                priority_for(order, production_profiles(db, [order]), settings, now))])
            focus["money_at_risk"] = str(focus_risk["total"]) if not focus_risk["unpriced_count"] else None
    counts = dict(db.execute(select(Order.internal_status, func.count()).where(
        Order.internal_status.notin_(ACTIVE), Order.ozon_status.notin_(OZON_CANCELLED_STATUSES))
        .group_by(Order.internal_status)).all())
    blocked, ready = counts.get("BLOCKED", 0), counts.get("READY_TO_SHIP", 0)
    overdue = db.scalar(select(func.count()).select_from(Order).where(
        Order.shipment_deadline < now, Order.internal_status.notin_(ACTIVE),
        Order.ozon_status.notin_(OZON_CANCELLED_STATUSES))) or 0
    task_counts = dict(db.execute(select(ManagerTask.status, func.count()).group_by(ManagerTask.status)).all()) if db_enabled(db, "manager_tasks") else {}
    tasks = db.scalars(select(ManagerTask).options(joinedload(ManagerTask.order))
                       .where(ManagerTask.status.in_(("OPEN", "IN_PROGRESS")))
                       .order_by(ManagerTask.created_at.desc(), ManagerTask.id.desc()).limit(5)).all() if db_enabled(db, "manager_tasks") else []
    workload = db.execute(select(User.id, User.display_name, func.count().label("count"))
        .join(Assignment, Assignment.user_id == User.id).join(Order, Order.id == Assignment.order_id)
        .where(Order.internal_status.notin_(ACTIVE), Order.ozon_status.notin_(OZON_CANCELLED_STATUSES))
        .group_by(User.id, User.display_name).order_by(func.count().desc(), User.id).limit(5)).all() if db_enabled(db, "analytics") and "analytics.view" in user_permissions(actor) else []
    cancelled = db.scalars(select(Order).where(Order.ozon_status.in_(OZON_CANCELLED_STATUSES),
        (Order.production_started_at.is_not(None)) | Order.internal_status.in_(
            ("IN_PRODUCTION", "PRODUCED", "QUALITY_CHECK", "PACKING", "READY_TO_SHIP", "HANDED_TO_SHIPPING", "DONE")), Order.internal_status != "CANCELLED")
        .order_by(Order.id.desc()).limit(20)).all()
    problems = db.scalars(select(Blocker).options(joinedload(Blocker.order)).where(
        Blocker.status.in_(("OPEN", "IN_PROGRESS")), Blocker.severity == "CRITICAL")
        .order_by(Blocker.created_at, Blocker.id).limit(5)).all()
    result = {
        "as_of": now, "critical": critical, "blocked": blocked, "ready": ready,
        "overdue": overdue, "manager_tasks": sum(task_counts.get(key, 0) for key in ("OPEN", "IN_PROGRESS")),
        "attention": [row[3] for row in attention],
        "cancelled_after_start": [{"id": row.id, "posting_number": row.posting_number} for row in cancelled],
        "critical_problems": [{"id": row.id, "order_id": row.order_id,
                               "posting_number": row.order.posting_number, "description": row.description}
                              for row in problems],
        "tasks": [{"id": task.id, "title": task.title, "severity": task.severity,
                   "posting_number": task.order.posting_number if task.order else None}
                  for task in tasks],
        "workload": [{"id": user_id, "name": name, "active_orders": count}
                     for user_id, name, count in workload],
    }
    if can_view_finance:
        result["money_at_risk"] = {"total": risk["total"], "unpriced_count": risk["unpriced_count"], "buckets": [
            {key: value for key, value in bucket.items() if key != "orders"} for bucket in risk["buckets"]]}
    return result
