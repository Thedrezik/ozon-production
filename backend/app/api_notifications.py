from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth import Current, Db
from app.models import AuditLog, Notification, NotificationPreference, utc_now
from app.notifications import (
    ADMIN_ROLES,
    CHANNELS,
    MANDATORY_ADMIN,
    TYPES,
    sync_deadline_notifications,
)

router = APIRouter(prefix="/api/notifications")


class PreferenceInput(BaseModel):
    type: str
    channel: str
    enabled: bool


def item(row: Notification) -> dict:
    return {"id": row.id, "type": row.type, "title": row.title,
            "body": row.body, "url": row.url, "created_at": row.created_at,
            "read_at": row.read_at}


@router.get("")
def list_notifications(db: Db, current: Current, request: Request, limit: int = 50, offset: int = 0,
                       unread_only: bool = False) -> dict:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Invalid pagination")
    user, _ = current
    if {role.name for role in user.roles} & set(ADMIN_ROLES):
        sync_deadline_notifications(db, request.app.state.settings.organization_timezone)
        db.commit()
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    rows = db.scalars(query.order_by(Notification.created_at.desc(), Notification.id.desc())
                      .limit(limit).offset(offset)).all()
    unread = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.read_at.is_(None))) or 0
    return {"items": [item(row) for row in rows], "unread": unread}


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, db: Db, current: Current) -> dict:
    user, _ = current
    row = db.scalar(select(Notification).where(Notification.id == notification_id,
                                                Notification.user_id == user.id))
    if row is None:
        raise HTTPException(404, "Notification not found")
    if row.read_at is None:
        row.read_at = utc_now()
        db.commit()
    return item(row)


@router.get("/preferences")
def preferences(db: Db, current: Current) -> dict:
    user, _ = current
    rows = db.scalars(select(NotificationPreference).where(NotificationPreference.user_id == user.id)).all()
    return {"types": TYPES, "channels": CHANNELS,
            "mandatory_admin": sorted(MANDATORY_ADMIN) if {r.name for r in user.roles} & set(ADMIN_ROLES) else [],
            "items": [{"type": row.type, "channel": row.channel, "enabled": row.enabled} for row in rows]}


@router.put("/preferences")
def set_preference(payload: PreferenceInput, db: Db, current: Current) -> dict:
    user, _ = current
    if payload.type not in TYPES or payload.channel not in CHANNELS:
        raise HTTPException(422, "Unknown notification type or channel")
    if (payload.type in MANDATORY_ADMIN and payload.channel == "IN_APP" and not payload.enabled
            and {r.name for r in user.roles} & set(ADMIN_ROLES)):
        raise HTTPException(409, "This admin notification is mandatory")
    row = db.scalar(select(NotificationPreference).where(
        NotificationPreference.user_id == user.id, NotificationPreference.type == payload.type,
        NotificationPreference.channel == payload.channel))
    if row is None:
        row = NotificationPreference(user_id=user.id, type=payload.type,
                                     channel=payload.channel, enabled=payload.enabled)
        db.add(row)
    else:
        row.enabled = payload.enabled
    db.add(AuditLog(actor_user_id=user.id, action="notification.preference.changed",
                    detail=f"{payload.type} {payload.channel} {payload.enabled}"))
    db.commit()
    return {"type": row.type, "channel": row.channel, "enabled": row.enabled}
