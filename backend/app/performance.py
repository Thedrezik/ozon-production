"""Bounded reads for exact read-time projections on the single-worker VPS."""
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Order
from app.ozon_status import OZON_CANCELLED_STATUSES

BATCH_SIZE = 250
MAX_OFFSET = 10_000


def order_batches(db, query):
    """Keyset pagination, without keeping ORM objects from earlier batches."""
    after = 0
    while True:
        rows = db.scalars(query.where(Order.id > after).order_by(Order.id)
                          .options(selectinload(Order.items)).limit(BATCH_SIZE)).all()
        if not rows:
            break
        after = rows[-1].id
        yield rows


def active_orders():
    return select(Order).where(
        Order.internal_status.notin_(("DONE", "CANCELLED", "HANDED_TO_SHIPPING")),
        Order.ozon_status.notin_(OZON_CANCELLED_STATUSES))
