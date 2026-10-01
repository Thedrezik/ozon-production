"""Telegram linking webhook and adapter for the existing delivery queue."""

import asyncio
import hashlib
import logging
import secrets
import urllib.request
from datetime import timedelta, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import Current, Db
from app.models import (
    AuditLog,
    Notification,
    NotificationDelivery,
    NotificationPreference,
    TelegramAccount,
    TelegramLink,
    User,
    utc_now,
)

router = APIRouter(prefix="/api/telegram")


def configured(settings):
    return bool(
        settings.telegram_bot_token
        and settings.telegram_bot_username
        and settings.telegram_webhook_secret
    )


@router.get("/status")
def status(request: Request, current: Current, db: Db):
    user, _ = current
    account = db.scalar(
        select(TelegramAccount).where(TelegramAccount.user_id == user.id)
    )
    return {
        "configured": configured(request.app.state.settings),
        "linked": account is not None,
        "bot_username": request.app.state.settings.telegram_bot_username or None,
    }


@router.post("/link")
def create_link(request: Request, current: Current, db: Db):
    user, _ = current
    settings = request.app.state.settings
    if not configured(settings):
        raise HTTPException(503, "Telegram не настроен на сервере")
    code = secrets.token_urlsafe(24)
    row = db.scalar(select(TelegramLink).where(TelegramLink.user_id == user.id))
    if row is None:
        row = TelegramLink(
            user_id=user.id,
            code_hash=hashlib.sha256(code.encode()).hexdigest(),
            expires_at=utc_now() + timedelta(minutes=10),
        )
        db.add(row)
    else:
        row.code_hash = hashlib.sha256(code.encode()).hexdigest()
        row.expires_at = utc_now() + timedelta(minutes=10)
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="telegram.link.started",
            detail="One-time Telegram link code issued",
        )
    )
    db.commit()
    return {
        "url": f"https://t.me/{settings.telegram_bot_username}?start={code}",
        "expires_in_seconds": 600,
    }


@router.delete("/link")
def unlink(current: Current, db: Db):
    user, _ = current
    account = db.scalar(
        select(TelegramAccount).where(TelegramAccount.user_id == user.id)
    )
    if account:
        db.delete(account)
    link = db.scalar(select(TelegramLink).where(TelegramLink.user_id == user.id))
    if link:
        db.delete(link)
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="telegram.unlinked",
            detail="Telegram account removed",
        )
    )
    db.commit()
    return {"ok": True}


def _telegram_request(token, chat_id, text, url=None):
    markup = {"inline_keyboard": [[{"text": "Открыть", "url": url}]]} if url else None
    import json

    payload = {
        "chat_id": chat_id,
        "text": text[:3500],
        "disable_web_page_preview": True,
    }
    if markup:
        payload["reply_markup"] = markup
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        if response.status != 200 or not json.loads(response.read()).get("ok"):
            raise RuntimeError("Telegram delivery failed")


def deliver_pending(engine, settings, sender=None):
    if not configured(settings):
        return
    sender = sender or _telegram_request
    with Session(engine) as db:
        rows = db.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.channel == "TELEGRAM",
                NotificationDelivery.status == "PENDING",
                or_(
                    NotificationDelivery.next_attempt_at.is_(None),
                    NotificationDelivery.next_attempt_at <= utc_now(),
                ),
            )
            .order_by(NotificationDelivery.id)
            .limit(10)
            .with_for_update(skip_locked=True)
        ).all()
        for delivery in rows:
            notice = db.get(Notification, delivery.notification_id)
            user = db.get(User, notice.user_id) if notice else None
            preference = (
                db.scalar(
                    select(NotificationPreference).where(
                        NotificationPreference.user_id == notice.user_id,
                        NotificationPreference.type == notice.type,
                        NotificationPreference.channel == "TELEGRAM",
                    )
                )
                if notice
                else None
            )
            account = (
                db.scalar(
                    select(TelegramAccount).where(
                        TelegramAccount.user_id == notice.user_id
                    )
                )
                if notice
                else None
            )
            if (
                not user
                or not user.is_active
                or not account
                or not preference
                or not preference.enabled
            ):
                delivery.status = "SKIPPED"
                continue
            safe_url = (
                notice.url
                if notice.url
                and __import__("re").fullmatch(
                    r"/(?:orders/\d+|manager-tasks/\d+|notifications|procurement)",
                    notice.url,
                )
                else None
            )
            text = f"{notice.title}\n\n{notice.body}"
            if safe_url:
                text += f"\n\n{settings.app_public_url.rstrip('/')}{safe_url}"
            try:
                sender(settings.telegram_bot_token, account.chat_id, text, None)
                delivery.status = "DELIVERED"
            except Exception:  # noqa: BLE001 - isolate provider failures; never log token or response
                delivery.attempts += 1
                delivery.status = "FAILED" if delivery.attempts >= 5 else "PENDING"
                delivery.next_attempt_at = utc_now() + timedelta(
                    seconds=min(3600, 30 * 2**delivery.attempts)
                )
        db.commit()


async def delivery_loop(engine, settings, stop):
    while not stop.is_set():
        try:
            await asyncio.to_thread(deliver_pending, engine, settings)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning("Telegram queue processing failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=15)
        except TimeoutError:
            pass


@router.post("/webhook")
async def webhook(
    request: Request,
    db: Db,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    settings = request.app.state.settings
    if not settings.telegram_webhook_secret or not secrets.compare_digest(
        x_telegram_bot_api_secret_token or "", settings.telegram_webhook_secret
    ):
        raise HTTPException(403, "Forbidden")
    try:
        update = await request.json()
        message = update.get("message", {})
        parts = (message.get("text") or "").split()
        if len(parts) != 2 or parts[0] != "/start":
            return {"ok": True}
        if message.get("chat", {}).get("type") != "private":
            return {"ok": True}
        code_hash = hashlib.sha256(parts[1].encode()).hexdigest()
        link = db.scalar(
            select(TelegramLink)
            .where(TelegramLink.code_hash == code_hash)
            .with_for_update()
        )
        now = utc_now()
        if (
            not link
            or (
                link.expires_at.replace(tzinfo=timezone.utc)
                if link.expires_at.tzinfo is None
                else link.expires_at
            )
            <= now
        ):
            return {"ok": True}
        chat_id = str(message.get("chat", {}).get("id", ""))
        if not chat_id or not chat_id.lstrip("-").isdigit():
            return {"ok": True}
        existing = db.scalar(
            select(TelegramAccount).where(TelegramAccount.chat_id == chat_id)
        )
        if existing and existing.user_id != link.user_id:
            return {"ok": True}
        account = db.scalar(
            select(TelegramAccount).where(TelegramAccount.user_id == link.user_id)
        )
        if account is None:
            account = TelegramAccount(user_id=link.user_id, chat_id=chat_id)
            db.add(account)
        else:
            account.chat_id = chat_id
        db.add(
            AuditLog(
                actor_user_id=link.user_id,
                action="telegram.linked",
                detail="Telegram account linked",
            )
        )
        db.delete(link)
        db.commit()
    except Exception:  # noqa: BLE001 - acknowledge malformed provider payload without leaking details
        db.rollback()
    return {"ok": True}
