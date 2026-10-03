"""External cancellation facts, separate from internal production stages."""

OZON_CANCELLED_STATUSES = ("cancelled", "cancelled_from_split_pending")


def is_cancelled(status: str | None) -> bool:
    return status in OZON_CANCELLED_STATUSES
