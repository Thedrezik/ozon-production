"""Transactional notification fan-out from existing domain actions."""

from datetime import timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Notification,
    NotificationDelivery,
    NotificationPreference,
    Order,
    Role,
    User,
    utc_now,
)

TYPES = (
    "NEW_ORDER", "ORDER_CANCELLED", "TARIFF_DEADLINE", "SHIPMENT_DEADLINE",
    "ORDER_OVERDUE", "BLOCKER_CREATED", "BLOCKER_RESOLVED", "PROCUREMENT_CREATED",
    "READY_TO_SHIP", "OZON_SYNC_ERROR", "API_KEY_EXPIRING",
)
CHANNELS = ("IN_APP", "WEB_PUSH", "TELEGRAM")
ADMIN_ROLES = ("SUPER_ADMIN", "ADMIN", "MANAGER")
MANDATORY_ADMIN = frozenset({"ORDER_CANCELLED", "ORDER_OVERDUE", "BLOCKER_CREATED",
                             "OZON_SYNC_ERROR", "API_KEY_EXPIRING"})


def manager_ids(db: Session) -> list[int]:
    return list(db.scalars(select(User.id).join(User.roles).where(
        User.is_active.is_(True), Role.name.in_(ADMIN_ROLES)
    ).distinct()))


def emit(db: Session, *, type: str, event_key: str, user_ids: list[int],
         title: str, body: str, url: str | None = None) -> int:
    """Create one notification per recipient and source event in the caller's transaction.

    The database unique key is the final concurrency guard. Callers should emit only
    for real state changes; repeated calls are safe even after a retry.
    """
    if type not in TYPES or not event_key or len(event_key) > 200:
        raise ValueError("Invalid notification event")
    recipients = db.scalars(select(User).where(User.id.in_(set(user_ids)), User.is_active.is_(True))).all()
    ids = [user.id for user in recipients]
    prefs = db.scalars(select(NotificationPreference).where(
        NotificationPreference.user_id.in_(ids), NotificationPreference.type == type
    )).all()
    enabled = {(p.user_id, p.channel): p.enabled for p in prefs}
    admin_ids = set(manager_ids(db)) if type in MANDATORY_ADMIN else set()
    created = 0
    for user in recipients:
        mandatory = user.id in admin_ids
        # IN_APP is on by default. External transports require explicit opt-in
        # until their delivery adapters are installed.
        channels = [channel for channel in CHANNELS if
                    (mandatory and channel == "IN_APP") or
                    enabled.get((user.id, channel), channel == "IN_APP")]
        if not channels:
            continue
        key = f"{type}:{event_key}"
        if db.scalar(select(Notification.id).where(
            Notification.user_id == user.id, Notification.dedupe_key == key
        )) is not None:
            continue
        # Nested transaction preserves other changes if concurrent delivery won.
        from sqlalchemy.exc import IntegrityError

        try:
            with db.begin_nested():
                row = Notification(user_id=user.id, type=type, dedupe_key=key,
                                   title=title, body=body, url=url)
                db.add(row)
                db.flush()
                for channel in channels:
                    db.add(NotificationDelivery(notification_id=row.id, channel=channel,
                                                status="DELIVERED" if channel == "IN_APP" else "PENDING"))
                db.flush()
        except IntegrityError:
            continue
        created += 1
    return created


def sync_deadline_notifications(db: Session, timezone_name: str) -> int:
    """Reconcile time-based notices when a manager opens the center.

    No broker or dedicated scheduler is needed yet; stable source keys make
    repeated reads harmless. The order and tariff services own calculations.
    """
    from app.api_orders import (
        priority_for,
        priority_settings,
        production_profiles,
        tariff_for,
    )
    from app.money_at_risk import aggregate
    from app.tariff import parse_normalized_steps

    now = utc_now()
    recipients = manager_ids(db)
    if not recipients:
        return 0
    orders = db.scalars(select(Order).where(Order.internal_status.not_in(
        ("DONE", "CANCELLED", "HANDED_TO_SHIPPING")), Order.ozon_status != "cancelled")).all()
    profiles, settings = production_profiles(db), priority_settings(db)
    count = 0
    for order in orders:
        deadline = order.shipment_deadline.replace(tzinfo=timezone.utc) if order.shipment_deadline.tzinfo is None else order.shipment_deadline
        if deadline <= now:
            kind = "ORDER_OVERDUE"
        elif deadline <= now + timedelta(hours=2):
            kind = "SHIPMENT_DEADLINE"
        else:
            kind = None
        if kind:
            count += emit(db, type=kind, event_key=f"order:{order.id}:{deadline.isoformat()}",
                          user_ids=recipients, title=f"Заказ {order.posting_number}",
                          body="Срок отгрузки прошёл" if kind == "ORDER_OVERDUE" else
                          f"До отгрузки {int((deadline - now).total_seconds() // 60)} мин",
                          url=f"/orders/{order.id}")
        tariff = tariff_for(order, now)
        next_step = tariff["next"] if tariff else None
        if next_step and next_step["starts_at"] <= now + timedelta(hours=2):
            priority = priority_for(order, profiles, settings, now)
            risk = aggregate([({"id": order.id, "posting_number": order.posting_number,
                                "internal_status": order.internal_status},
                               parse_normalized_steps(order.tariff_steps), priority)], now, timezone_name)
            amount = next((entry["amount"] for bucket in risk["buckets"] for entry in bucket["orders"]
                           if entry["at"] == next_step["starts_at"]), None)
            detail = f"Подтверждённый риск: {amount:.2f} ₽" if amount is not None else "Денежный эффект не подтверждён"
            count += emit(db, type="TARIFF_DEADLINE",
                          event_key=f"order:{order.id}:{next_step['starts_at'].isoformat()}",
                          user_ids=recipients, title=f"Тариф заказа {order.posting_number}",
                          body=f"Следующая ступень через {int((next_step['starts_at'] - now).total_seconds() // 60)} мин. {detail}",
                          url=f"/orders/{order.id}")
    return count
