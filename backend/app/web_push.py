"""Web Push adapter for the existing notification delivery queue."""

import asyncio
import json
import logging
import re
from datetime import timedelta, timezone

from pywebpush import WebPushException, webpush
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Notification,
    NotificationDelivery,
    NotificationPreference,
    PushReceipt,
    PushSubscription,
    User,
    utc_now,
)


def configured(settings):
    return bool(settings.vapid_public_key and settings.vapid_private_key
                and settings.vapid_subject)


def deliver_pending(engine, settings, sender=None):
    if not configured(settings):
        return
    sender = sender or webpush
    with Session(engine) as db:
        rows = db.scalars(select(NotificationDelivery).where(
            NotificationDelivery.channel == "WEB_PUSH",
            NotificationDelivery.status == "PENDING",
            or_(NotificationDelivery.next_attempt_at.is_(None), NotificationDelivery.next_attempt_at <= utc_now()),
        ).order_by(NotificationDelivery.id).limit(10).with_for_update(skip_locked=True)).all()
        for delivery in rows:
            now = utc_now()
            if delivery.next_attempt_at:
                next_at = delivery.next_attempt_at.replace(tzinfo=timezone.utc)
                if next_at > now:
                    continue
            notice = db.get(Notification, delivery.notification_id)
            user = db.get(User, notice.user_id)
            pref = db.scalar(select(NotificationPreference).where(
                NotificationPreference.user_id == notice.user_id,
                NotificationPreference.type == notice.type,
                NotificationPreference.channel == "WEB_PUSH"))
            if not user or not user.is_active or not pref or not pref.enabled:
                delivery.status = "SKIPPED"
                continue
            subscriptions = db.scalars(select(PushSubscription).where(
                PushSubscription.user_id == user.id,
                PushSubscription.created_at <= notice.created_at).with_for_update()).all()
            failed = False
            accepted = False
            for subscription in subscriptions:
                if db.scalar(select(PushReceipt.id).where(
                    PushReceipt.delivery_id == delivery.id,
                    PushReceipt.subscription_id == subscription.id)):
                    accepted = True
                    continue
                try:
                    sender(subscription_info={"endpoint": subscription.endpoint, "keys": {
                        "p256dh": subscription.p256dh, "auth": subscription.auth}},
                        data=json.dumps({"title": notice.title[:120], "body": notice.body[:500],
                                         "url": notice.url if notice.url and re.fullmatch(
                                             r"/(?:orders/\d+|manager-tasks/\d+|notifications|procurement)",
                                             notice.url) else "/notifications",
                                         "tag": f"notification-{notice.id}"}, ensure_ascii=False),
                        vapid_private_key=settings.vapid_private_key,
                        vapid_claims={"sub": settings.vapid_subject}, timeout=10, ttl=3600)
                    accepted = True
                    db.add(PushReceipt(delivery_id=delivery.id, subscription_id=subscription.id))
                except WebPushException as error:
                    code = error.response.status_code if error.response is not None else None
                    if code in (404, 410):
                        db.add(AuditLog(actor_user_id=user.id, action="push.expired",
                                        detail=f"Subscription {subscription.id}; HTTP {code}"))
                        db.delete(subscription)
                    else:
                        failed = True
                except Exception:  # noqa: BLE001 - isolate transport failures without exposing secrets
                    # Never log exception text: provider errors can contain keys/endpoints.
                    failed = True
            delivery.attempts += 1
            delivery.status = ("FAILED" if delivery.attempts >= 5 else "PENDING") if failed else (
                "DELIVERED" if accepted else "SKIPPED")
            delivery.next_attempt_at = now + timedelta(seconds=min(3600, 30 * 2 ** delivery.attempts))
        db.commit()


async def delivery_loop(engine, settings, stop):
    while not stop.is_set():
        try:
            await asyncio.to_thread(deliver_pending, engine, settings)
        except Exception:  # noqa: BLE001 - isolate transport failures without exposing secrets
            logging.getLogger(__name__).warning("Web Push queue processing failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=15)
        except TimeoutError:
            pass
