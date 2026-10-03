"""Verified Seller v4 tariff adapter (docs checked 2026-10-02).

Charge is the supplied discount/surcharge, never price * rate or min_charge.
Step deadlines end stages; explicit next_tariff_starts_at takes precedence.
Unknown types/malformed money retain timing with an unknown monetary effect.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def stamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (AttributeError, ValueError, OverflowError):
        return None


def step(raw, starts_at=None, prefix=""):
    kind = raw.get(f"{prefix}tariff_type") or "unknown"
    if not isinstance(kind, str):
        kind = "unknown"
    money = raw.get(f"{prefix}tariff_charge")
    # v3 get supplies a decimal string + separate currency; v4 list uses Money.
    if prefix and not isinstance(money, dict):
        money = {"amount": money, "currency": raw.get(f"{prefix}tariff_charge_currency_code")}
    cost, currency = None, None
    if isinstance(money, dict):
        currency = money.get("currency")
        try:
            amount = money.get("amount")
            if isinstance(amount, (bool, float)) or not isinstance(amount, (str, int, Decimal)):
                raise TypeError
            amount = Decimal(str(amount))
            if not amount.is_finite() or amount < 0 or not isinstance(currency, str) or not currency:
                raise ValueError
            if kind in ("discount", "commission"):
                cost = str(-amount if kind == "discount" else amount)
            elif kind == "no_discount" and amount == 0:
                cost = str(amount)  # Only an explicitly supplied zero, never inferred.
        except (InvalidOperation, ValueError, TypeError):
            pass
    rate = raw.get(f"{prefix}tariff_rate")
    try:
        rate = Decimal(str(rate)) if rate is not None else None
        rate = str(rate) if rate is not None and rate.is_finite() else None
    except InvalidOperation:
        rate = None
    return {"starts_at": starts_at.isoformat() if starts_at else None,
            "tariff_type": kind, "rate_percent": rate, "cost": cost,
            "currency": currency if isinstance(currency, str) and currency else None}


def normalize(raw: dict, now: datetime) -> list[dict] | None:
    current = raw.get("tariffication")
    source = raw.get("tariffication_steps")
    steps = []
    previous_end = None
    if isinstance(source, list) and source:
        for entry in source:
            if not isinstance(entry, dict):
                steps = []
                break
            end = stamp(entry.get("tariff_deadline_at"))
            if end is None or (previous_end is not None and end <= previous_end):
                steps = []
                break
            steps.append(step(entry, previous_end))
            previous_end = end
        # No contract supplies the tariff after the last end. Stop pricing there.
        if steps and previous_end.year < 9999:
            steps.append(step({}, previous_end))
    if not isinstance(current, dict) or not current:
        return steps or None
    baseline = step(current, prefix="current_")
    next_at = stamp(current.get("next_tariff_starts_at"))
    following = step(current, next_at, "next_") if next_at else None
    # Prefer the complete sequence only if it agrees with the explicit snapshot.
    active = next((s for s in reversed(steps) if s["starts_at"] is None or stamp(s["starts_at"]) <= now), None)
    upcoming = next((s for s in steps if s["starts_at"] and stamp(s["starts_at"]) > now), None)
    def same(left, right):
        return (left is not None and right is not None and left["tariff_type"] == right["tariff_type"]
                and (right["currency"] is None or left["currency"] == right["currency"])
                and (right["cost"] is None or (left["cost"] is not None and Decimal(left["cost"]) == Decimal(right["cost"]))))
    matches_current = same(active, baseline)
    matches_next = following is None or same(upcoming, following)
    if matches_current and matches_next and following:
        index = steps.index(upcoming)
        after = steps[index + 1] if index + 1 < len(steps) else None
        # The explicit snapshot start can differ from an end boundary (e.g. +1s).
        # Keep the full timeline only when this correction remains chronological.
        if next_at <= now or (after and next_at >= stamp(after["starts_at"])):
            matches_next = False
        else:
            upcoming["starts_at"] = following["starts_at"]
    if matches_current and matches_next:
        return steps
    # Inconsistent/incomplete step history: use only the authoritative current/next pair.
    # Do not reconstruct historical savings or extend a known amount indefinitely.
    result = [baseline]
    if matches_current and baseline["cost"] is None:
        # Empty v3 snapshot charge is not a contradiction of an explicitly priced step.
        baseline["cost"], baseline["currency"] = active["cost"], active["currency"]
    if following and next_at > now:
        result.append(following)
    return result
