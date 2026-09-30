from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InternalStatus, Order, OrderItem, StatusHistory, utc_now

STATUSES = (
    "NEW", "QUEUED", "SENT_TO_PRODUCTION", "IN_PRODUCTION", "BLOCKED",
    "PRODUCED", "PACKING", "READY_TO_SHIP", "DONE", "CANCELLED",
)
TRANSITIONS = {
    "NEW": {"QUEUED", "CANCELLED"},
    "QUEUED": {"SENT_TO_PRODUCTION", "IN_PRODUCTION", "BLOCKED", "CANCELLED"},
    "SENT_TO_PRODUCTION": {"IN_PRODUCTION", "BLOCKED", "CANCELLED"},
    "IN_PRODUCTION": {"PRODUCED", "BLOCKED", "CANCELLED"},
    "BLOCKED": {"QUEUED", "SENT_TO_PRODUCTION", "IN_PRODUCTION", "CANCELLED"},
    "PRODUCED": {"PACKING", "CANCELLED"},
    "PACKING": {"READY_TO_SHIP", "CANCELLED"},
    "READY_TO_SHIP": {"DONE", "CANCELLED"},
    "DONE": set(),
    "CANCELLED": set(),
}


def transition(db: Session, order: Order, status: str, actor_id: int) -> None:
    if status not in TRANSITIONS.get(order.internal_status, set()):
        raise ValueError("Invalid status transition")
    old = order.internal_status
    order.internal_status = status
    db.add(StatusHistory(order_id=order.id, old_status=old, new_status=status, changed_by=actor_id))


def seed_mock_orders(db: Session) -> int:
    """Repeatable development data, clearly marked and isolated from real Ozon data."""
    for name in STATUSES:
        if db.get(InternalStatus, name) is None:
            db.add(InternalStatus(name=name))
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
                      items=[OrderItem(product_name=product, quantity=quantity)])
        db.add(order)
        db.flush()
        db.add(StatusHistory(order_id=order.id, old_status=None, new_status=status, changed_by=None))
        created += 1
    db.commit()
    return created
