from io import BytesIO
from typing import Annotated

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.auth import Db, require
from app.models import (
    AuditLog,
    Blocker,
    Comment,
    Order,
    OrderTimelineEvent,
    Photo,
    User,
)
from app.photos import TYPES, compress_image
from app.rbac import user_permissions
from app.storage import Storage

router = APIRouter(prefix="/api/files")


async def upload_slot(request: Request):
    # Bound image decode memory on the single small VPS worker.
    async with request.app.state.upload_slot:
        yield


Viewer = Annotated[User, Depends(require("orders.view"))]


def metadata(row: Photo) -> dict:
    return {"id": row.id, "order_id": row.order_id, "blocker_id": row.blocker_id,
            "comment_id": row.comment_id, "uploader_id": row.uploader_id,
            "mime_type": row.mime_type, "size_bytes": row.size_bytes,
            "width": row.width, "height": row.height, "created_at": row.created_at,
            "url": f"/api/files/photos/{row.id}"}


@router.post("/orders/{order_id}/photos", status_code=201)
async def upload(order_id: int, request: Request, db: Db, actor: Viewer,
                 blocker_id: int | None = None, comment_id: int | None = None,
                 _slot: None = Depends(upload_slot)):
    permissions = user_permissions(actor)
    needed = "blockers.create" if blocker_id is not None else "comments.create"
    if needed not in permissions:
        raise HTTPException(403, "Permission denied")
    if blocker_id is not None and comment_id is not None:
        raise HTTPException(422, "Choose one photo target")
    if db.get(Order, order_id) is None:
        raise HTTPException(404, "Order not found")
    for model, target in ((Blocker, blocker_id), (Comment, comment_id)):
        if target is not None:
            row = db.get(model, target)
            if row is None or row.order_id != order_id:
                raise HTTPException(404, "Photo target not found")
            if model is Comment and row.author_user_id != actor.id and "comments.delete" not in permissions:
                raise HTTPException(403, "Permission denied")
    mime = request.headers.get("content-type", "").split(";")[0].lower()
    if mime not in TYPES:
        raise HTTPException(415, "Supported types: JPEG, PNG, WebP")
    limit = request.app.state.settings.upload_max_bytes
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > limit:
            raise HTTPException(413, "Image exceeds upload limit")
        content.extend(chunk)
    try:
        compressed, width, height = await run_in_threadpool(compress_image, bytes(content), mime)
    except ValueError as error:
        raise HTTPException(415, str(error)) from None
    storage: Storage = request.app.state.storage
    key = await run_in_threadpool(storage.put, compressed)
    try:
        photo = Photo(order_id=order_id, blocker_id=blocker_id, comment_id=comment_id,
                      uploader_id=actor.id, storage_key=key, mime_type="image/jpeg",
                      size_bytes=len(compressed), width=width, height=height)
        db.add(photo)
        db.flush()
        db.add(AuditLog(actor_user_id=actor.id, action="photo.uploaded",
                        detail=f"order:{order_id} photo:{photo.id} blocker:{blocker_id} comment:{comment_id}"))
        db.add(OrderTimelineEvent(order_id=order_id, actor_user_id=actor.id,
                                  event_type="photo_uploaded", description=f"Добавлено фото #{photo.id}"))
        db.commit()
    except Exception:
        db.rollback()
        await run_in_threadpool(storage.delete, key)
        raise
    request.app.state.order_events.publish(order_id)
    return metadata(photo)


@router.get("/orders/{order_id}/photos")
def list_photos(order_id: int, db: Db, actor: Viewer,
                limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                target_only: bool = False, blocker_id: int | None = None,
                comment_id: int | None = None):
    if db.get(Order, order_id) is None:
        raise HTTPException(404, "Order not found")
    query = select(Photo).where(Photo.order_id == order_id)
    if target_only:
        query = query.where(Photo.blocker_id == blocker_id, Photo.comment_id == comment_id)
    rows = db.scalars(query.order_by(Photo.id.desc()).limit(limit + 1).offset(offset)).all()
    return {"items": [metadata(row) for row in rows[:limit]], "has_more": len(rows) > limit}


@router.get("/photos/{photo_id}")
def download(photo_id: int, request: Request, db: Db, actor: Viewer):
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    try:
        content = request.app.state.storage.read(photo.storage_key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Photo not found") from None
    return Response(content, media_type="image/jpeg", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/resolve")
def resolve(db: Db, actor: Viewer, payload: str = Query(min_length=1, max_length=160)):
    posting = payload.removeprefix("ozon-production:posting:")
    order = db.scalar(select(Order).where(Order.posting_number == posting))
    if order is None:
        raise HTTPException(404, "Order not found")
    return {"order_id": order.id, "posting_number": order.posting_number, "url": f"/orders/{order.id}"}


@router.get("/orders/{order_id}/qr")
def qr(order_id: int, db: Db, actor: Viewer):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    output = BytesIO()
    qrcode.make(f"ozon-production:posting:{order.posting_number}").save(output, format="PNG")
    return Response(output.getvalue(), media_type="image/png", headers={"Cache-Control": "private, no-store"})
