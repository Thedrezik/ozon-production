"""Read-only, SQL aggregated production analytics; no parallel event store."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, distinct, extract, func, select

from app.auth import Db, require
from app.models import (
    Assignment,
    Blocker,
    BlockerType,
    Order,
    OrderItem,
    ProductProductionProfile,
    StatusHistory,
    User,
    utc_now,
)
from app.ozon_status import OZON_CANCELLED_STATUSES
from app.rbac import user_permissions

router = APIRouter(prefix="/api/analytics")


@router.get("")
def analytics(db: Db, request: Request, actor: Annotated[User, Depends(require("analytics.view"))],
              start: date, end: date, page: Annotated[int, Query(ge=1)] = 1,
              page_size: Annotated[int, Query(ge=1, le=100)] = 20) -> dict:
    if end < start or (end - start).days > 365:
        raise HTTPException(422, "Период должен быть от 1 до 366 дней")
    zone = ZoneInfo(request.app.state.settings.organization_timezone)
    lower = datetime.combine(start, time.min, zone).astimezone(timezone.utc)
    upper = datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(timezone.utc)

    def period(column):
        return (column >= lower, column < upper)

    def minutes(begin, finish):
        if db.bind.dialect.name == "sqlite":
            return (func.julianday(finish) - func.julianday(begin)) * 1440
        return extract("epoch", finish - begin) / 60

    intervals = {}
    for name, begin, finish in (
        ("new_to_production", Order.created_at, Order.production_started_at),
        ("production", Order.production_started_at, Order.production_completed_at),
        ("produced_to_ready", Order.production_completed_at, Order.ready_to_ship_at),
        ("cycle", Order.created_at, Order.ready_to_ship_at),
    ):
        count, average = db.execute(select(func.count(), func.avg(minutes(begin, finish))).where(
            *period(finish), begin.is_not(None), finish >= begin)).one()
        intervals[name] = {"count": count, "average_minutes": round(average, 2) if average is not None else None}

    counts = {name: db.scalar(select(func.count()).select_from(Order).where(*period(column))) or 0
              for name, column in (("received", Order.created_at), ("started", Order.production_started_at),
                                   ("produced", Order.production_completed_at), ("ready", Order.ready_to_ship_at))}
    # Deadline cohort: still unready at the earlier of now and the end of the period,
    # or first readiness after the confirmed shipment deadline.
    cutoff = min(utc_now(), upper)
    counts["overdue"] = db.scalar(select(func.count()).select_from(Order).where(
        *period(Order.shipment_deadline), Order.shipment_deadline < cutoff,
        Order.internal_status != "CANCELLED", Order.ozon_status.notin_(OZON_CANCELLED_STATUSES),
        (Order.ready_to_ship_at > Order.shipment_deadline) | Order.ready_to_ship_at.is_(None))) or 0
    blockers = [dict(row._mapping) for row in db.execute(select(
        Blocker.type_code, BlockerType.display_name.label("name"), func.count().label("count"),
        func.sum(case((Blocker.status.in_(("OPEN", "IN_PROGRESS")), 1), else_=0)).label("currently_open")
    ).join(BlockerType, Blocker.type_code == BlockerType.code).where(*period(Blocker.created_at))
        .group_by(Blocker.type_code, BlockerType.display_name).order_by(Blocker.type_code))]
    # Each posting contributes once per SKU/offer pair, regardless of duplicate item rows/quantity.
    products = select(OrderItem.order_id, OrderItem.sku, OrderItem.offer_id).join(
        Order, Order.id == OrderItem.order_id).where(
        *period(Order.production_completed_at), Order.production_started_at.is_not(None),
        Order.production_completed_at >= Order.production_started_at).distinct().subquery()
    profile_minutes = func.coalesce(
        select(ProductProductionProfile.production_minutes).where(
            ProductProductionProfile.offer_id == products.c.offer_id).scalar_subquery(),
        select(ProductProductionProfile.production_minutes).where(
            ProductProductionProfile.sku == products.c.sku).scalar_subquery())
    sku_query = select(products.c.sku, products.c.offer_id, func.max(profile_minutes).label("normative_minutes_per_unit"),
                       func.count().label("orders"),
                       func.avg(minutes(Order.production_started_at, Order.production_completed_at))
                       .label("average_minutes")).join(Order, Order.id == products.c.order_id).where(
        *period(Order.production_completed_at), Order.production_started_at.is_not(None),
        Order.production_completed_at >= Order.production_started_at).group_by(products.c.sku, products.c.offer_id)
    # Attribution comes from actual stage actors, never the mutable current assignment.
    employees = select(StatusHistory.changed_by.label("user_id"),
                       func.count(distinct(StatusHistory.order_id)).label("processed_orders")).where(
        *period(StatusHistory.changed_at), StatusHistory.new_status.in_(("PRODUCED", "READY_TO_SHIP")),
        StatusHistory.changed_by.is_not(None)).group_by(StatusHistory.changed_by).subquery()
    employee_query = select(employees.c.user_id, User.display_name.label("name"), employees.c.processed_orders
                            ).join(User, User.id == employees.c.user_id)

    def paginated(query, ordering):
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = [dict(row._mapping) for row in db.execute(query.order_by(*ordering)
                .offset((page - 1) * page_size).limit(page_size))]
        return {"items": rows, "total": total, "page": page, "page_size": page_size}

    active = select(Assignment.user_id, func.count().label("active_orders")).join(
        Order, Order.id == Assignment.order_id).where(
        Order.internal_status.notin_(("DONE", "CANCELLED", "HANDED_TO_SHIPPING")),
        Order.ozon_status.notin_(OZON_CANCELLED_STATUSES)).group_by(Assignment.user_id).subquery()
    workload = select(active.c.user_id, User.display_name.label("name"), active.c.active_orders
                      ).join(User, User.id == active.c.user_id)
    result = {"start": start, "end": end, "timezone": str(zone), "as_of": utc_now(),
              "intervals": intervals, "throughput": counts, "blockers": blockers,
              "sku": paginated(sku_query, (products.c.sku, products.c.offer_id)),
              "employees": paginated(employee_query, (employees.c.user_id,)),
              "current_workload": paginated(workload, (active.c.user_id,))}
    if "finance.view" in user_permissions(actor):
        result["prevented_financial_risk"] = {
            "amount": None, "reason": "Нет подтверждённых исторических потерь и однозначного сценария предотвращения. Money at Risk — прогноз, а не доказанная экономия."}
    return result
