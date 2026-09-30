from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import Db, require
from app.models import AuditLog, ProductProductionProfile, User, utc_now

router = APIRouter(prefix="/api/product-profiles")


class ProfileInput(BaseModel):
    offer_id: str | None = Field(default=None, max_length=160)
    sku: str | None = Field(default=None, max_length=80)
    product_name: str = Field(min_length=1, max_length=240)
    production_minutes: int = Field(ge=0, le=100_000)
    packing_minutes: int = Field(ge=0, le=100_000)
    complexity: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    production_group: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_identifiers(self):
        self.offer_id = self.offer_id.strip() if self.offer_id else None
        self.sku = self.sku.strip() if self.sku else None
        self.product_name = self.product_name.strip()
        self.production_group = self.production_group.strip() if self.production_group else None
        if not self.offer_id and not self.sku:
            raise ValueError("offer_id or sku is required")
        if not self.product_name:
            raise ValueError("product_name cannot be blank")
        return self


def serialize(row: ProductProductionProfile) -> dict:
    return {"id": row.id, "offer_id": row.offer_id, "sku": row.sku,
            "product_name": row.product_name, "production_minutes": row.production_minutes,
            "packing_minutes": row.packing_minutes, "complexity": row.complexity,
            "production_group": row.production_group, "created_at": row.created_at,
            "updated_at": row.updated_at}


@router.get("")
def list_profiles(db: Db, _actor: Annotated[User, Depends(require("product_profiles.manage"))]) -> list[dict]:
    rows = db.scalars(select(ProductProductionProfile).order_by(ProductProductionProfile.product_name)).all()
    return [serialize(row) for row in rows]


@router.post("", status_code=201)
def create_profile(payload: ProfileInput, db: Db,
                   actor: Annotated[User, Depends(require("product_profiles.manage"))]) -> dict:
    row = ProductProductionProfile(**payload.model_dump(), created_at=utc_now(), updated_at=utc_now())
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A profile already uses this offer_id or SKU") from None
    db.add(AuditLog(actor_user_id=actor.id, action="product_profile.created", detail=f"#{row.id}"))
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.put("/{profile_id}")
def update_profile(profile_id: int, payload: ProfileInput, db: Db,
                   actor: Annotated[User, Depends(require("product_profiles.manage"))]) -> dict:
    row = db.get(ProductProductionProfile, profile_id)
    if row is None:
        raise HTTPException(404, "Product profile not found")
    for name, value in payload.model_dump().items():
        setattr(row, name, value)
    row.updated_at = utc_now()
    db.add(AuditLog(actor_user_id=actor.id, action="product_profile.updated", detail=f"#{row.id}"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A profile already uses this offer_id or SKU") from None
    db.refresh(row)
    return serialize(row)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int, db: Db,
                   actor: Annotated[User, Depends(require("product_profiles.manage"))]) -> None:
    row = db.get(ProductProductionProfile, profile_id)
    if row is None:
        raise HTTPException(404, "Product profile not found")
    db.add(AuditLog(actor_user_id=actor.id, action="product_profile.deleted", detail=f"#{row.id}"))
    db.delete(row)
    db.commit()
