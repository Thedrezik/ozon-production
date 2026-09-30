from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InternalStatus, Order, OrderItem, StatusHistory, utc_now

STATUSES = (
    "NEW", "QUEUED", "SENT_TO_PRODUCTION", "IN_PRODUCTION", "BLOCKED",
    "PRODUCED", "QUALITY_CHECK", "PACKING", "READY_TO_SHIP", "HANDED_TO_SHIPPING", "DONE", "CANCELLED",
)
STATUS_LABELS = (
    "Новый", "В очереди", "Передан в производство", "В производстве", "Заблокирован",
    "Произведён", "Проверка качества", "Упаковка", "Готов к отгрузке", "Передан в доставку", "Завершён", "Отменён",
)
TRANSITIONS = {
    "NEW": {"QUEUED", "CANCELLED"},
    "QUEUED": {"SENT_TO_PRODUCTION", "IN_PRODUCTION", "BLOCKED", "CANCELLED"},
    "SENT_TO_PRODUCTION": {"IN_PRODUCTION", "BLOCKED", "CANCELLED"},
    "IN_PRODUCTION": {"PRODUCED", "BLOCKED", "CANCELLED"},
    "BLOCKED": {"QUEUED", "SENT_TO_PRODUCTION", "IN_PRODUCTION", "QUALITY_CHECK", "CANCELLED"},
    "PRODUCED": {"QUALITY_CHECK", "CANCELLED"},
    "QUALITY_CHECK": {"PACKING", "IN_PRODUCTION", "BLOCKED", "CANCELLED"},
    "PACKING": {"READY_TO_SHIP", "CANCELLED"},
    "READY_TO_SHIP": {"HANDED_TO_SHIPPING", "CANCELLED"},
    "HANDED_TO_SHIPPING": {"DONE"},
    "DONE": set(),
    "CANCELLED": set(),
}


def transition(db: Session, order: Order, status: str, actor_id: int) -> None:
    if status not in TRANSITIONS.get(order.internal_status, set()):
        raise ValueError("Invalid status transition")
    old = order.internal_status
    order.internal_status = status
    stamp = {
        "IN_PRODUCTION": "production_started_at", "PRODUCED": "production_completed_at",
        "PACKING": "packing_started_at", "READY_TO_SHIP": "ready_to_ship_at",
        "HANDED_TO_SHIPPING": "handed_to_shipping_at", "DONE": "done_at",
    }.get(status)
    if stamp and getattr(order, stamp) is None:
        setattr(order, stamp, utc_now())
    db.add(StatusHistory(order_id=order.id, old_status=old, new_status=status, changed_by=actor_id))


def seed_mock_orders(db: Session) -> int:
    """Repeatable development data, clearly marked and isolated from real Ozon data."""
    for index, name in enumerate(STATUSES):
        if db.get(InternalStatus, name) is None:
            db.add(InternalStatus(name=name, display_name=STATUS_LABELS[index], sort_order=index))
    now = utc_now()
    samples = (
        ("normal", "Тумба прикроватная", 1, 48, "QUEUED", "awaiting_packaging"),
        ("urgent", "Шкаф распашной", 1, 3, "QUEUED", "awaiting_packaging"),
        ("near-deadline", "Стол письменный", 2, 1, "SENT_TO_PRODUCTION", "awaiting_packaging"),
        ("overdue", "Полка настенная", 3, -4, "IN_PRODUCTION", "awaiting_packaging"),
        ("blocked", "Комод дубовый", 1, 6, "BLOCKED", "awaiting_packaging"),
        ("cancelled", "Стеллаж белый", 1, 12, "CANCELLED", "cancelled"),
        ("ready", "Тумба под ТВ", 1, 5, "READY_TO_SHIP", "awaiting_deliver"),
    )
    created = 0
    for key, product, quantity, hours, status, ozon_status in samples:
        posting = f"MOCK-{key.upper()}"
        if db.scalar(select(Order.id).where(Order.posting_number == posting)) is not None:
            continue
        order = Order(posting_number=posting, ozon_status=ozon_status, internal_status=status,
                      shipment_deadline=now + timedelta(hours=hours), is_mock=True,
                      tariff_deadline=now + timedelta(minutes=75) if key == "near-deadline" else None,
                      tariff_impact=Decimal(640) if key == "near-deadline" else None,
                      order_value=Decimal(12000) if key == "near-deadline" else None,
                      items=[OrderItem(product_name=product, quantity=quantity)])
        db.add(order)
        db.flush()
        db.add(StatusHistory(order_id=order.id, old_status=None, new_status=status, changed_by=None))
        created += 1
    db.commit()
    return created
