import asyncio
import json
from datetime import timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
)
from sqlalchemy import func, select

from app.auth import Db, require
from app.manager_tasks import resolve_source
from app.models import AuditLog, OzonCredentials, OzonWebhookEvent, User, utc_now
from app.ozon import OzonClient, OzonError
from app.ozon_credentials import (
    cipher,
    effective_settings,
    expiration_alerts,
    retire_alerts,
    rotation_lock,
)
from app.ozon_reconciliation import sync_status

router = APIRouter(prefix="/api/ozon/integration")


def admin(actor: Annotated[User, Depends(require("settings.manage"))]):
    if not any(role.name in ("ADMIN", "SUPER_ADMIN") for role in actor.roles):
        raise HTTPException(403, "Admin required")
    return actor


class Replacement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: SecretStr | None = Field(default=None, min_length=1, max_length=100)
    api_key: SecretStr = Field(min_length=1, max_length=512)
    expires_at: AwareDatetime | None = None


class Expiration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_at: AwareDatetime | None = Field(default=None)


@router.get("")
def status(request: Request, db: Db, actor: Annotated[User, Depends(admin)]):
    config = request.app.state.settings
    row = db.get(OzonCredentials, 1)
    sync = sync_status(db, config)
    recent = utc_now() - timedelta(hours=24)
    webhook = db.scalar(select(func.max(OzonWebhookEvent.received_at)).where(
        OzonWebhookEvent.is_mock == config.ozon_mock_mode))
    webhook_errors = db.scalar(select(func.count()).select_from(OzonWebhookEvent).where(
        OzonWebhookEvent.is_mock == config.ozon_mock_mode,
        OzonWebhookEvent.received_at >= recent, OzonWebhookEvent.error_code.is_not(None)))
    sync_errors = db.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action == "ozon.reconciliation.error", AuditLog.created_at >= recent))
    state = "MOCK" if config.ozon_mock_mode else "VERIFIED" if row else "UNVERIFIED"
    if not config.ozon_mock_mode and not row and not (config.ozon_client_id and config.ozon_api_key):
        state = "NOT_CONFIGURED"
    if not config.ozon_mock_mode and sync["error_code"]:
        state = "ERROR"
    if row and row.expires_at and row.expires_at.replace(tzinfo=timezone.utc) <= utc_now() and not config.ozon_mock_mode:
        state = "EXPIRED"
    return {"connection_state": state, "last_successful_sync": sync["last_successful_sync"],
            "last_webhook": webhook.replace(tzinfo=timezone.utc) if webhook else None,
            "recent_error_count": webhook_errors + sync_errors, "error_window_hours": 24,
            "expires_at": row.expires_at.replace(tzinfo=timezone.utc) if row and row.expires_at else None,
            "checked_at": row.checked_at.replace(tzinfo=timezone.utc) if row else None,
            "rotation_available": bool(config.ozon_credentials_master_key)}


@router.put("/credentials")
async def replace(request: Request, db: Db, actor: Annotated[User, Depends(admin)]):
    # Never echo invalid request inputs (including a secret) in Pydantic error responses.
    try:
        payload = Replacement.model_validate(await request.json())
    except (ValidationError, ValueError):
        raise HTTPException(422, "Invalid credential settings") from None
    return await asyncio.to_thread(rotate, payload, request, db, actor)


def rotate(payload, request, db, actor):
    config = request.app.state.settings
    with rotation_lock:
        try:
            encryptor = cipher(config)
            current = effective_settings(db, config)
            values = {"ozon_client_id": payload.client_id.get_secret_value() if payload.client_id else current.ozon_client_id,
                      "ozon_api_key": payload.api_key.get_secret_value()}
            candidate = config.model_copy(update=values)
            # Always the real client: mock success must never validate a real replacement.
            with OzonClient(candidate) as client:
                connection = client.check_connection()
        except OzonError as exc:
            db.add(AuditLog(actor_user_id=actor.id, action="ozon.credentials.rejected", detail=type(exc).__name__))
            db.commit()
            raise HTTPException(502, type(exc).__name__) from None
        retire_alerts(db)
        row = db.get(OzonCredentials, 1)
        if row is None:
            row = OzonCredentials(id=1, revision=1)
            db.add(row)
        else:
            resolve_source(db, source_type="API_KEY_EXPIRING", source_id=row.revision)
            row.revision += 1
        row.encrypted_credentials = encryptor.encrypt(json.dumps(values).encode()).decode()
        # Use only a verified upstream date or the operator's explicit date.
        # Missing/malformed upstream values never imply a guessed lifetime.
        expiry = payload.expires_at
        if connection.expires_at:
            try:
                expiry = TypeAdapter(AwareDatetime).validate_python(connection.expires_at)
            except ValidationError:
                pass
        row.expires_at = expiry.astimezone(timezone.utc) if expiry else None
        row.checked_at = utc_now()
        db.add(AuditLog(actor_user_id=actor.id, action="ozon.credentials.replaced",
                        detail=f"revision:{row.revision}; expiration:{row.expires_at}"))
        db.flush()
        expiration_alerts(db, config)
        db.commit()
    return {"status": "VERIFIED"}


@router.put("/expiration")
async def update_expiration(request: Request, db: Db,
                      actor: Annotated[User, Depends(admin)]):
    try:
        payload = Expiration.model_validate(await request.json())
    except (ValidationError, ValueError):
        raise HTTPException(422, "Invalid expiration settings") from None
    return await asyncio.to_thread(change_expiration, payload, request, db, actor)


def change_expiration(payload, request, db, actor):
    with rotation_lock:
        row = db.get(OzonCredentials, 1)
        if row is None:
            raise HTTPException(409, "Verify and save credentials first")
        old = row.expires_at
        new_expiry = payload.expires_at.astimezone(timezone.utc) if payload.expires_at else None
        if (old.replace(tzinfo=timezone.utc) if old else None) == new_expiry:
            return {"status": "UNCHANGED"}
        resolve_source(db, source_type="API_KEY_EXPIRING", source_id=row.revision)
        retire_alerts(db)
        row.revision += 1
        row.expires_at = payload.expires_at.astimezone(timezone.utc) if payload.expires_at else None
        db.add(AuditLog(actor_user_id=actor.id, action="ozon.expiration.updated",
                       detail=f"old:{old}; new:{payload.expires_at}"))
        db.flush()
        expiration_alerts(db, request.app.state.settings)
        db.commit()
    return {"status": "UPDATED"}
