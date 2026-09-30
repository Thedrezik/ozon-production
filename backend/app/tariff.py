"""Tariff timeline over explicitly normalized, signed costs.

The adapter supplying these values must establish the meaning of each cost.
Ozon rate/type alone never imply a ruble amount or a sign here.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class TariffStep:
    starts_at: datetime | None
    tariff_type: str
    rate_percent: Decimal | None
    cost: Decimal | None
    currency: str | None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise TypeError("Money and rates must be decimal strings, integers or Decimal")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal value") from exc
    if not result.is_finite():
        raise ValueError("Non-finite decimal value")
    return result


def parse_normalized_steps(payload: list[dict[str, Any]]) -> tuple[TariffStep, ...]:
    """Parse our mock/integration boundary format, not an Ozon API response."""
    if not payload:
        return ()
    steps = []
    for index, raw in enumerate(payload):
        stamp = raw.get("starts_at")
        if index == 0 and stamp is not None or index > 0 and stamp is None:
            raise ValueError("Only the baseline step may omit starts_at")
        if stamp is not None:
            try:
                moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except (AttributeError, ValueError) as exc:
                raise ValueError("Invalid tariff timestamp") from exc
            if moment.tzinfo is None:
                raise ValueError("Tariff timestamp must include a timezone")
            moment = moment.astimezone(timezone.utc)
        else:
            moment = None
        tariff_type = raw.get("tariff_type")
        if not isinstance(tariff_type, str) or not tariff_type:
            raise ValueError("Tariff type is required")
        cost = _decimal(raw.get("cost"))
        currency = raw.get("currency")
        if cost is not None and (not isinstance(currency, str) or not currency):
            raise ValueError("Cost requires a currency")
        if currency is not None and (not isinstance(currency, str) or not currency):
            raise ValueError("Invalid currency")
        if steps and steps[-1].starts_at is not None and moment <= steps[-1].starts_at:
            raise ValueError("Tariff steps must be strictly chronological")
        steps.append(TariffStep(moment, tariff_type, _decimal(raw.get("rate_percent")), cost, currency))
    return tuple(steps)


def evaluate(steps: tuple[TariffStep, ...], now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("Current time must include a timezone")
    now = now.astimezone(timezone.utc)
    current = next((step for step in reversed(steps) if step.starts_at is None or step.starts_at <= now), None)
    upcoming = next((step for step in steps if step.starts_at is not None and step.starts_at > now), None)

    def describe(step: TariffStep | None) -> dict | None:
        if step is None:
            return None
        return {"starts_at": step.starts_at, "tariff_type": step.tariff_type,
                "rate_percent": step.rate_percent, "cost": step.cost, "currency": step.currency}

    comparable = (current is not None and upcoming is not None and current.cost is not None
                  and upcoming.cost is not None and current.currency == upcoming.currency)
    delta = upcoming.cost - current.cost if comparable else None
    return {"current": describe(current), "next": describe(upcoming),
            "timeline": [describe(step) for step in steps],
            "current_tariff_cost": current.cost if current else None,
            "next_tariff_cost": upcoming.cost if upcoming else None,
            "delta_to_next_tariff": delta,
            "potential_saving": max(delta, Decimal(0)) if delta is not None else None,
            "potential_loss": max(-delta, Decimal(0)) if delta is not None else None}
