import base64
import secrets
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth import Current, Db
from app.models import AuditLog, PushSubscription
from app.notifications import emit
from app.web_push import configured

router = APIRouter(prefix="/api/push")


class EndpointInput(BaseModel):
    endpoint: str = Field(max_length=2048)

    @field_validator("endpoint")
    @classmethod
    def safe_endpoint(cls, value):
        url = urlsplit(value)
        host = url.hostname or ""
        allowed = (host == "fcm.googleapis.com" or host == "updates.push.services.mozilla.com"
                   or host in ("web.push.apple.com", "wns.windows.com")
                   or host.endswith((".push.apple.com", ".wns.windows.com")))
        if (url.scheme != "https" or not allowed or url.port not in (None, 443)
                or url.username or url.password or url.fragment):
            raise ValueError("Unsupported push service")
        return value


class Keys(BaseModel):
    p256dh: str = Field(max_length=120, pattern=r"^[A-Za-z0-9_-]+={0,2}$")
    auth: str = Field(max_length=40, pattern=r"^[A-Za-z0-9_-]+={0,2}$")

    @field_validator("p256dh", "auth")
    @classmethod
    def valid_key(cls, value, info):
        try:
            raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except ValueError:
            raise ValueError("Invalid push key") from None
        if len(raw) != (65 if info.field_name == "p256dh" else 16):
            raise ValueError("Invalid push key length")
        if info.field_name == "p256dh":
            try:
                ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
            except ValueError:
                raise ValueError("Invalid P-256 public key") from None
        return value


class SubscriptionInput(EndpointInput):
    keys: Keys


@router.get("/config")
def config(request: Request, current: Current):
    settings = request.app.state.settings
    return {"enabled": configured(settings), "public_key": settings.vapid_public_key}


@router.post("/subscriptions", status_code=201)
def subscribe(payload: SubscriptionInput, db: Db, current: Current, request: Request):
    if not configured(request.app.state.settings):
        raise HTTPException(503, "Web Push не настроен")
    user, _ = current
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint))
    if row and row.user_id != user.id:
        raise HTTPException(409, "Сначала отключите подписку предыдущего пользователя")
    if row is None:
        if db.scalar(select(func.count(PushSubscription.id)).where(PushSubscription.user_id == user.id)) >= 10:
            raise HTTPException(409, "Достигнут лимит устройств")
        row = PushSubscription(user_id=user.id, endpoint=payload.endpoint)
        db.add(row)
    row.p256dh, row.auth = payload.keys.p256dh, payload.keys.auth
    db.add(AuditLog(actor_user_id=user.id, action="push.subscribed", detail="Device subscription saved"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Подписка уже изменена. Повторите действие.") from None
    return {"id": row.id}


@router.delete("/subscriptions")
def unsubscribe(payload: EndpointInput, db: Db, current: Current):
    user, _ = current
    row = db.scalar(select(PushSubscription).where(
        PushSubscription.endpoint == payload.endpoint, PushSubscription.user_id == user.id))
    if row:
        db.delete(row)
        db.add(AuditLog(actor_user_id=user.id, action="push.unsubscribed", detail="Device subscription removed"))
        db.commit()
    return {"ok": True}


@router.post("/test")
def test_push(db: Db, current: Current):
    user, _ = current
    emit(db, type="NEW_ORDER", event_key=f"push-test:{secrets.token_hex(12)}", user_ids=[user.id],
         title="Тест Web Push", body="Уведомления на этом устройстве работают.", url="/notifications")
    db.commit()
    return {"ok": True}
