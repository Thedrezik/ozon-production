"""Finance-only snapshot and paginated order drill-down."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api_orders import priority_for, priority_settings, production_profiles
from app.auth import Db, require
from app.models import Order, User, utc_now
from app.money_at_risk import aggregate
from app.performance import MAX_OFFSET, active_orders, order_batches
from app.tariff import parse_normalized_steps

router = APIRouter(prefix="/api/money-at-risk")


def _snapshot(db: Db, request: Request, as_of: datetime | None = None, *,
              include_orders: bool = False, order_limit: int | None = None,
              category_filter: str | None = None, source_rows=None) -> dict:
    config = request.app.state.settings
    cutoffs = tuple(sorted({int(hour) for hour in config.money_risk_cutoff_hours.split(",") if hour}))
    if any(hour < 1 or hour > 23 for hour in cutoffs):
        raise ValueError("Money risk cutoff hours must be between 1 and 23")
    now = as_of or utc_now()
    if now.tzinfo is None or now > utc_now():
        raise HTTPException(422, "Invalid snapshot time")
    def rows():
        settings = priority_settings(db)
        for batch in order_batches(db, active_orders().where(Order.tariff_steps.is_not(None))):
            profiles = production_profiles(db, batch)
            for order in batch:
                yield ({"id": order.id, "posting_number": order.posting_number,
                        "internal_status": order.internal_status},
                       parse_normalized_steps(order.tariff_steps), priority_for(order, profiles, settings, now))
    return aggregate(source_rows if source_rows is not None else rows(), now,
                     config.organization_timezone, config.money_risk_near_hours, cutoffs,
                     include_orders=include_orders, order_limit=order_limit, category_filter=category_filter)


@router.get("")
def summary(db: Db, request: Request,
            _actor: Annotated[User, Depends(require("finance.view"))]) -> dict:
    snapshot = _snapshot(db, request)
    return {**snapshot, "buckets": [{key: value for key, value in bucket.items() if key != "orders"}
                                    for bucket in snapshot["buckets"]],
            "already_degraded": {key: value for key, value in snapshot["already_degraded"].items()
                                 if key != "orders"}}


@router.get("/orders")
def bucket_orders(db: Db, request: Request,
                  _actor: Annotated[User, Depends(require("finance.view"))],
                  bucket: str, category: str | None = None, as_of: datetime | None = None,
                  limit: int = 20, offset: int = 0) -> dict:
    if not 1 <= limit <= 100 or not 0 <= offset <= MAX_OFFSET:
        raise HTTPException(422, "Invalid pagination")
    snapshot = _snapshot(db, request, as_of, include_orders=True, order_limit=offset + limit,
                         category_filter=category)
    selected = next((item for item in [*snapshot["buckets"], snapshot["already_degraded"]]
                     if item["key"] == bucket), None)
    if selected is None:
        raise HTTPException(422, "Unknown bucket")
    if category is not None and category not in snapshot["categories"]:
        raise HTTPException(422, "Unknown category")
    rows = [row for row in selected["orders"]
            if category is None or ("ALREADY_DEGRADED" if bucket == "already_degraded" else row["category"]) == category]
    return {"items": rows[offset:offset + limit], "total": selected["order_count"],
            "amount": selected["amount"], "as_of": snapshot["as_of"]}
