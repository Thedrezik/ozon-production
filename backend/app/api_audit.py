from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.auth import Db, require
from app.models import AuditLog, User

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(db: Db, _actor: Annotated[User, Depends(require("audit.view"))],
               user_id: int | None = None, action: str | None = None,
               entity_type: str | None = None, entity_id: str | None = None,
               since: datetime | None = None, until: datetime | None = None,
               limit: Annotated[int, Query(ge=1, le=100)] = 50,
               offset: Annotated[int, Query(ge=0)] = 0):
    for timestamp in (since, until):
        if timestamp is not None and timestamp.utcoffset() is None:
            raise HTTPException(422, "Timezone required")
    if since and until and since > until:
        raise HTTPException(422, "Invalid period")
    filters = []
    for column, item in ((AuditLog.actor_user_id, user_id), (AuditLog.action, action),
                         (AuditLog.entity_type, entity_type), (AuditLog.entity_id, entity_id)):
        if item is not None:
            filters.append(column == item)
    if since:
        filters.append(AuditLog.created_at >= since.astimezone(timezone.utc))
    if until:
        filters.append(AuditLog.created_at <= until.astimezone(timezone.utc))
    rows = db.scalars(select(AuditLog).where(*filters).order_by(
        AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)).all()
    return {"total": db.scalar(select(func.count()).select_from(AuditLog).where(*filters)),
            "items": [{"id": row.id, "user_id": row.actor_user_id, "action": row.action,
                       "entity_type": row.entity_type, "entity_id": row.entity_id,
                       "old_value": row.old_value, "new_value": row.new_value,
                       "timestamp": row.created_at.replace(tzinfo=timezone.utc).isoformat(),
                       "ip": row.ip, "user_agent": row.user_agent} for row in rows]}
