from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ValidationError, model_validator

from app.auth import Db, require
from app.models import User
from app.ozon import OzonError
from app.ozon_import import import_fbs, validate_window

router = APIRouter(prefix="/api/ozon")


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
        result = import_fbs(db, request.app.state.ozon_client, payload.since, payload.to,
                            is_mock=request.app.state.settings.ozon_mock_mode, actor_id=actor.id)
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
