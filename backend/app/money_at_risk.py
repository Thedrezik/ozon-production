"""Aggregate confirmed tariff increases into disjoint time and risk groups."""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.tariff import TariffStep
from app.tariff import evaluate as evaluate_tariff

ZERO = Decimal(0)
CATEGORIES = ("CAN_STILL_SAVE", "HIGH_RISK", "BLOCKED_RISK", "ALREADY_DEGRADED")


def bucket_boundaries(now: datetime, timezone_name: str, near_hours: int,
                      cutoffs: tuple[int, ...]) -> list[dict]:
    """Return non-overlapping UTC intervals labelled in organization local time."""
    local = now.astimezone(ZoneInfo(timezone_name))
    today = local.date()
    candidates = [("next_hours", now + timedelta(hours=near_hours), f"Ближайшие {near_hours} ч")]
    for hour in cutoffs:
        candidates.append((f"by_{hour:02d}", datetime.combine(today, time(hour), local.tzinfo),
                           f"До {hour:02d}:00"))
    candidates += [
        ("today", datetime.combine(today + timedelta(days=1), time.min, local.tzinfo), "До конца дня"),
        ("tomorrow", datetime.combine(today + timedelta(days=2), time.min, local.tzinfo), "Завтра"),
    ]
    ends = sorted(((key, end.astimezone(timezone.utc), label) for key, end, label in candidates
                   if end.astimezone(timezone.utc) > now), key=lambda item: item[1])
    result = []
    start = now
    for key, end, label in ends:
        if end <= start:
            continue
        result.append({"key": key, "label": label, "starts_at": start, "ends_at": end})
        start = end
    return result


def _category(priority: dict) -> str:
    if priority["blocked"]:
        return "BLOCKED_RISK"
    if priority["feasible"] is not True or priority["level"] in ("P0", "P1"):
        return "HIGH_RISK"
    return "CAN_STILL_SAVE"


def aggregate(rows: list[tuple[dict, tuple[TariffStep, ...], dict]], now: datetime,
              timezone_name: str, near_hours: int = 2,
              cutoffs: tuple[int, ...] = (12, 16)) -> dict:
    """Rows contain order identity, normalized tariff steps and evaluated priority.

    Each future increase above the previous high-water mark is counted once.
    Unknown/non-RUB costs are excluded; order value never substitutes for cost.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    buckets = [{**boundary, "amount": ZERO, "order_count": 0, "orders": []}
               for boundary in bucket_boundaries(now, timezone_name, near_hours, cutoffs)]
    degraded = {"key": "already_degraded", "label": "Уже ухудшилось", "amount": ZERO,
                "order_count": 0, "orders": []}
    category_amounts = {category: ZERO for category in CATEGORIES}
    unknown_count = 0
    for order, steps, priority in rows:
        if order["internal_status"] in ("DONE", "CANCELLED", "HANDED_TO_SHIPPING") or not steps:
            continue
        tariff = evaluate_tariff(steps, now)
        current = tariff["current"]
        if current is None or current["cost"] is None or current["currency"] != "RUB":
            unknown_count += 1
            continue
        identity = {"id": order["id"], "posting_number": order["posting_number"],
                    "internal_status": order["internal_status"], "priority_level": priority["level"]}
        baseline = steps[0]
        if baseline.cost is not None and baseline.currency == "RUB":
            already = max(ZERO, current["cost"] - baseline.cost)
            if already:
                degraded["orders"].append({**identity, "amount": already,
                                            "at": current["starts_at"]})
                degraded["amount"] += already
                category_amounts["ALREADY_DEGRADED"] += already
        else:
            unknown_count += 1
        high = current["cost"]
        category = _category(priority)
        for step in steps:
            if step.starts_at is None or step.starts_at <= now:
                continue
            if step.cost is None or step.currency != "RUB":
                unknown_count += 1
                break  # Later increases cannot be measured safely across an unknown step.
            increase = max(ZERO, step.cost - high)
            high = max(high, step.cost)
            if not increase:
                continue
            bucket = next((bucket for bucket in buckets
                           if bucket["starts_at"] < step.starts_at <= bucket["ends_at"]), None)
            if bucket is None:
                continue
            bucket["amount"] += increase
            category_amounts[category] += increase
            existing = next((entry for entry in bucket["orders"] if entry["id"] == order["id"]), None)
            if existing:
                existing["amount"] += increase
            else:
                bucket["orders"].append({**identity, "amount": increase, "at": step.starts_at,
                                         "category": category})
    for bucket in [*buckets, degraded]:
        bucket["order_count"] = len(bucket["orders"])
    return {"timezone": timezone_name, "as_of": now, "total": sum((bucket["amount"] for bucket in buckets), ZERO),
            "already_degraded": degraded, "categories": category_amounts, "buckets": buckets,
            "unpriced_count": unknown_count}
