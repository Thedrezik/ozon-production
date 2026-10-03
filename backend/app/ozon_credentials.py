"""One credential source for all existing Ozon callers and expiration effects."""
import asyncio
import json
import logging
from datetime import timedelta, timezone
from threading import RLock

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.manager_tasks import ensure_task, resolve_source
from app.models import Notification, NotificationDelivery, OzonCredentials, utc_now
from app.notifications import emit, manager_ids
from app.ozon import OzonConfigurationError, create_ozon_client

rotation_lock = RLock()


def cipher(config):
    try:
        return Fernet(config.ozon_credentials_master_key.encode())
    except (ValueError, TypeError):
        raise OzonConfigurationError() from None


def effective_settings(db, config):
    row = db.get(OzonCredentials, 1)
    if row is None:
        return config
    try:
        values = json.loads(cipher(config).decrypt(row.encrypted_credentials.encode()))
    except (InvalidToken, ValueError, TypeError):
        raise OzonConfigurationError() from None
    return config.model_copy(update=values)


class ManagedOzonClient:
    """Keeps the existing shared pool; rotates lazily after a committed change."""
    def __init__(self, engine, config):
        self.engine, self.config = engine, config
        self.client, self.version = None, None

    def _call(self, method, *args, **kwargs):
        with rotation_lock:
            with Session(self.engine) as db:
                row = db.get(OzonCredentials, 1)
                version = row.revision if row and not self.config.ozon_mock_mode else 0
                if self.client is None or self.version != version:
                    settings = self.config if self.config.ozon_mock_mode else effective_settings(db, self.config)
                    candidate = create_ozon_client(settings)
                    if self.client:
                        self.client.close()
                    self.client, self.version = candidate, version
            # Credential reads release their DB slot before external HTTP.
            return getattr(self.client, method)(*args, **kwargs)

    def check_connection(self):
        return self._call("check_connection")

    def list_fbs(self, *args, **kwargs):
        return self._call("list_fbs", *args, **kwargs)

    def get_fbs(self, *args, **kwargs):
        return self._call("get_fbs", *args, **kwargs)

    def close(self):
        with rotation_lock:
            if self.client:
                self.client.close()


def expiration_alerts(db, config, *, now=None):
    row = db.get(OzonCredentials, 1)
    if row is None:
        return 0
    now = now or utc_now()
    expiry = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at else None
    critical = expiry is not None and expiry <= now + timedelta(days=1)
    task = None
    if critical:
        task = ensure_task(db, source_type="API_KEY_EXPIRING", source_id=row.revision,
                    order_id=None, title="Заменить ключ Ozon",
                    description="Ключ Ozon истекает в течение суток или уже истёк.",
                    severity="CRITICAL", due_at=expiry)
    else:
        resolve_source(db, source_type="API_KEY_EXPIRING", source_id=row.revision)
    if expiry is None:
        return 0
    days = sorted({int(v) for v in config.ozon_key_alert_days.split(",") if v.strip()}, reverse=True)
    if not days or any(day < 1 or day > 365 for day in days):
        raise ValueError("Invalid Ozon alert intervals")
    # Emit the nearest reached threshold only; downtime must not produce four notices at once.
    reached = [day for day in days if expiry <= now + timedelta(days=day)]
    if not reached:
        return 0
    threshold = 0 if expiry <= now else min(reached)
    return emit(db, type="API_KEY_EXPIRING",
                event_key=f"credentials:{row.revision}:{expiry.isoformat()}:{threshold}",
                user_ids=manager_ids(db), title="Срок действия ключа Ozon",
                body=f"Ключ истекает {expiry.isoformat()}. Замените ключ в настройках интеграции.",
                url=f"/manager-tasks/{task.id}" if task else "/notifications")


async def expiration_loop(engine, config, stop):
    def tick():
        with rotation_lock, Session(engine) as db:
            expiration_alerts(db, config)
            db.commit()
    while not stop.is_set():
        try:
            await asyncio.to_thread(tick)
        except Exception:  # noqa: BLE001 - keep the scheduler alive
            logging.getLogger(__name__).error("Ozon expiration worker unavailable")
        try:
            await asyncio.wait_for(stop.wait(), timeout=3600)
        except TimeoutError:
            pass


def retire_alerts(db):
    """Stop obsolete pending alerts while retaining notification/audit history."""
    notices = db.scalars(select(Notification).where(Notification.type == "API_KEY_EXPIRING")).all()
    ids = [notice.id for notice in notices]
    for notice in notices:
        if notice.read_at is None:
            notice.read_at = utc_now()
    for delivery in db.scalars(select(NotificationDelivery).where(
        NotificationDelivery.notification_id.in_(ids), NotificationDelivery.status == "PENDING")):
        delivery.status = "SKIPPED"
