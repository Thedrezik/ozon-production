from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ValidationError, model_validator
from sqlalchemy import select

from app.auth import Db, require
from app.models import AuditLog, OzonWebhookEvent, User, utc_now
from app.ozon import OzonError
from app.ozon_import import import_fbs, posting_sync_lock, validate_window
from app.ozon_webhook import apply_posting

router = APIRouter(prefix="/api/ozon")


@router.get("/sync-state")
def reconciliation_state(request: Request, db: Db,
                         actor: Annotated[User, Depends(require("orders.view"))]) -> dict:
    from app.ozon_reconciliation import sync_status

    return sync_status(db, request.app.state.settings)


@router.post("/webhook/events/{event_id}/retry")
def retry_webhook(event_id: int, db: Db,
                  actor: Annotated[User, Depends(require("settings.manage"))]) -> dict:
    event = db.scalar(select(OzonWebhookEvent).where(
        OzonWebhookEvent.id == event_id).with_for_update())
    if event is None:
        raise HTTPException(404, "Webhook event not found")
    if event.status in ("FAILED", "RETRY"):
        event.status, event.attempts, event.next_attempt_at = "PENDING", 0, utc_now()
        db.add(AuditLog(actor_user_id=actor.id, action="ozon.webhook.retry", detail=f"event:{event.id}"))
        db.commit()
    return {"status": event.status}


class ImportWindow(BaseModel):
    since: AwareDatetime
    to: AwareDatetime

    @model_validator(mode="after")
    def valid_window(self):
        validate_window(self.since, self.to)
        return self


@router.post("/fbs/import")
def import_postings(payload: ImportWindow, request: Request, db: Db,
                    actor: Annotated[User, Depends(require("settings.manage"))]) -> dict:
    try:
        with posting_sync_lock:
            result = import_fbs(db, request.app.state.ozon_client, payload.since, payload.to,
                                is_mock=request.app.state.settings.ozon_mock_mode, actor_id=actor.id,
                                on_posting=lambda raw: apply_posting(
                                    db, raw, request.app.state.settings, actor_id=actor.id))
            db.commit()
    except OzonError as exc:
        db.rollback()
        raise HTTPException(502, type(exc).__name__) from None
    except (ValidationError, ValueError, TypeError):
        db.rollback()
        raise HTTPException(502, "Invalid Ozon FBS payload") from None
    if result["changed"]:
        request.app.state.order_events.publish(0)
    return result
