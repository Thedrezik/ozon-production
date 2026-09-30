"""Pure, deterministic production priority calculation.

Money is used only when a confirmed tariff effect is available. Order value is
context, never treated as a loss estimate.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

LEVELS = ("P0", "P1", "P2", "P3", "P4")
LABELS = {"P0": "Критический", "P1": "Срочный", "P2": "Сегодня", "P3": "Плановый", "P4": "Позже"}


@dataclass(frozen=True)
class PriorityWeights:
    deadline: int = 40
    tariff: int = 25
    finance: int = 20
    feasibility: int = 15
    high_impact_rub: Decimal = Decimal(1000)
    high_value_rub: Decimal = Decimal(10000)


@dataclass(frozen=True)
class PriorityInput:
    shipment_deadline: datetime
    internal_status: str
    shipment_date_without_delay: datetime | None = None
    tariff_deadline: datetime | None = None
    tariff_impact: Decimal | None = None
    order_value: Decimal | None = None
    remaining_minutes: int | None = None
    blocked: bool = False
    override: str | None = None
    pinned: bool = False


def _minutes(moment: datetime, now: datetime) -> int:
    return int((moment.astimezone(timezone.utc) - now.astimezone(timezone.utc)).total_seconds() // 60)


def _time_text(minutes: int) -> str:
    if minutes < 0:
        return f"просрочен на {abs(minutes) // 60} ч {abs(minutes) % 60} мин"
    return f"через {minutes // 60} ч {minutes % 60} мин"


DEFAULT_WEIGHTS = PriorityWeights()


def evaluate(data: PriorityInput, now: datetime, weights: PriorityWeights = DEFAULT_WEIGHTS) -> dict:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if any(moment is not None and moment.tzinfo is None for moment in (
        data.shipment_deadline, data.shipment_date_without_delay, data.tariff_deadline
    )):
        raise ValueError("priority deadlines must be timezone-aware")
    if data.internal_status in ("DONE", "CANCELLED", "HANDED_TO_SHIPPING"):
        return {"level": "P4", "label": LABELS["P4"], "score": 0, "reasons": ["Заказ вышел из производственной очереди"],
                "blocked": False, "feasible": None, "remaining_minutes": 0, "next_deadline": None,
                "financial_impact": None, "pinned": False, "manual_override": data.override}

    reasons: list[str] = []
    deadlines = [("Отгрузка", data.shipment_deadline)]
    if data.shipment_date_without_delay:
        deadlines.append(("Отгрузка без задержки", data.shipment_date_without_delay))
    if data.tariff_deadline:
        deadlines.append(("Ухудшение тарифа", data.tariff_deadline))
    name, next_deadline = min(deadlines, key=lambda pair: pair[1])
    next_minutes = _minutes(next_deadline, now)
    shipment_minutes = _minutes(data.shipment_deadline, now)
    reasons.append(f"{name}: {_time_text(next_minutes)}")

    def urgency(minutes: int) -> int:
        if minutes <= 0:
            return 100
        if minutes <= 120:
            return 90
        if minutes <= 480:
            return 70
        if minutes <= 1440:
            return 45
        if minutes <= 2880:
            return 20
        return 0

    deadline_urgency = max(urgency(shipment_minutes), urgency(_minutes(data.shipment_date_without_delay, now))
                           if data.shipment_date_without_delay else 0)
    tariff_urgency = urgency(_minutes(data.tariff_deadline, now)) if data.tariff_deadline else 0
    impact = data.tariff_impact if data.tariff_impact is not None and data.tariff_impact > 0 else None
    if data.tariff_deadline and impact is not None:
        reasons.append(f"Подтверждённый эффект тарифа: {impact:.2f} ₽")
    elif data.tariff_deadline:
        reasons.append("Денежный эффект тарифа неизвестен")
    if data.order_value is not None:
        reasons.append(f"Стоимость заказа: {data.order_value:.2f} ₽")
    impact_urgency = min(100, int(impact * 100 / weights.high_impact_rub)) if impact else 0
    value_urgency = min(25, int(data.order_value * 25 / weights.high_value_rub)) if data.order_value else 0
    finance_urgency = max(impact_urgency, value_urgency)

    feasible: bool | None = None
    feasibility_urgency = 0
    if data.remaining_minutes is not None:
        reasons.append(f"Осталось производство и упаковка: ~{data.remaining_minutes} мин")
        slack = min(_minutes(moment, now) for _, moment in deadlines) - data.remaining_minutes
        feasible = slack >= 0 and not data.blocked
        if slack < 0:
            reasons.append(f"Невозможно успеть при текущем нормативе: не хватает {abs(slack)} мин")
            feasibility_urgency = 100
        elif slack <= 60:
            reasons.append(f"Запас времени после производства: {slack} мин")
            feasibility_urgency = 80
        elif slack <= 240:
            feasibility_urgency = 40
    else:
        reasons.append("Норматив производства неизвестен — возможность успеть не оценена")
    if data.blocked:
        reasons.append("Есть активная проблема: требуется вмешательство руководителя")
        feasible = False

    score = (deadline_urgency * weights.deadline + tariff_urgency * weights.tariff
             + finance_urgency * weights.finance + feasibility_urgency * weights.feasibility) // 100
    level = "P0" if score >= 80 else "P1" if score >= 60 else "P2" if score >= 35 else "P3" if score >= 15 else "P4"
    if next_minutes <= 0 or (feasible is False and not data.blocked and next_minutes <= 120):
        level = min(level, "P0")
    elif next_minutes <= 480:
        level = min(level, "P1")
    if data.blocked and (next_minutes <= 480 or score >= 60):
        level = min(level, "P1")
    if data.override:
        level = data.override
        reasons.insert(0, f"Ручной приоритет: {LABELS[level]}")
    if data.pinned:
        reasons.insert(0, "Закреплено вручную")
    return {"level": level, "label": LABELS[level], "score": score, "reasons": reasons,
            "blocked": data.blocked, "feasible": feasible, "remaining_minutes": data.remaining_minutes,
            "next_deadline": next_deadline, "financial_impact": impact if data.tariff_deadline else None,
            "pinned": data.pinned, "manual_override": data.override}


def sort_key(priority: dict, order_id: int) -> tuple:
    deadline = priority["next_deadline"]
    return (LEVELS.index(priority["level"]), not priority["pinned"], -priority["score"],
            deadline or datetime.max.replace(tzinfo=timezone.utc), order_id)
