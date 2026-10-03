"""Single-process, sequential reconciliation over the shared FBS importer."""

import asyncio
import logging
from datetime import timedelta, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.manager_tasks import ensure_task, resolve_source
from app.models import AuditLog, Order, OzonPostingData, OzonSyncState, utc_now
from app.notifications import emit, manager_ids
from app.ozon import OzonError
from app.ozon_import import import_fbs, posting_sync_lock
from app.ozon_status import OZON_CANCELLED_STATUSES
from app.ozon_webhook import apply_posting

logger = logging.getLogger(__name__)


def state_for(db: Session, config) -> OzonSyncState:
    key = 2 if config.ozon_mock_mode else 1
    state = db.get(OzonSyncState, key)
    if state is None:
        state = OzonSyncState(id=key, status="NEVER", error_episode=0)
        db.add(state)
        db.flush()
    return state


def sync_status(db: Session, config, *, now=None) -> dict:
    now = now or utc_now()
    state = db.get(OzonSyncState, 2 if config.ozon_mock_mode else 1)
    success = state.last_successful_sync if state else None
    age = max(0, int((now - success.replace(tzinfo=timezone.utc)).total_seconds())) if success else None
    return {
        "enabled": config.ozon_reconciliation_enabled,
        "interval_seconds": config.ozon_reconciliation_interval_seconds,
        "status": state.status if state else "NEVER",
        "error_code": state.error_code if state else None,
        "last_attempt_at": state.last_attempt_at.replace(tzinfo=timezone.utc) if state and state.last_attempt_at else None,
        "last_successful_sync": success.replace(tzinfo=timezone.utc) if success else None,
        "age_seconds": age,
        "stale": age is None or age >= config.ozon_stale_after_seconds,
    }


def reconcile(engine, client, config, events) -> dict:
    with posting_sync_lock:
        return _reconcile(engine, client, config, events)


def _reconcile(engine, client, config, events) -> dict:
    """Persist attempt first; all pages, domain effects and success commit together.

    Never infer deletion/cancellation from absence in a list. Known nonterminal
    postings missing from the window are fetched with the existing get adapter.
    One lifespan loop owns scheduling; it never overlaps itself.
    """
    attempted_at = utc_now()
    with Session(engine) as db:
        state = state_for(db, config)
        previous_success = state.last_successful_sync
        state.last_attempt_at, state.status = attempted_at, "RUNNING"
        db.commit()
    try:
        with Session(engine) as db:
            db.info["settings"] = config
            state = state_for(db, config)
            since = attempted_at - timedelta(days=config.ozon_reconciliation_lookback_days)
            if previous_success:
                # Widen after an outage, with overlap, within the verified API limit.
                since = min(since, previous_success.replace(tzinfo=timezone.utc) - timedelta(days=1))
            to = attempted_at + timedelta(days=1)
            since = max(since, to - timedelta(days=365))
            seen = set()

            def receive(raw):
                seen.add(raw["posting_number"])
                return apply_posting(db, raw, config)

            result = import_fbs(db, client, since, to, is_mock=config.ozon_mock_mode,
                                actor_id=None, on_posting=receive)
            # Keyset batches bound memory; terminal logistics statuses stop polling.
            after_id = 0
            result["checked_missing"] = 0
            while True:
                query = select(Order.id, Order.posting_number).where(
                    Order.id > after_id, Order.is_mock == config.ozon_mock_mode,
                    Order.ozon_status.not_in((*OZON_CANCELLED_STATUSES, "delivered")),
                )
                if config.ozon_mock_mode:
                    # Local production seed scenarios are not Seller API fixtures.
                    query = query.join(OzonPostingData, OzonPostingData.order_id == Order.id)
                known = db.execute(query.order_by(Order.id).limit(100)).all()
                if not known:
                    break
                for order_id, number in known:
                    if number in seen:
                        continue
                    raw = client.get_fbs(number)
                    if raw.get("posting_number") != number:
                        raise ValueError("Posting mismatch")
                    result["changed"] += apply_posting(db, raw, config, from_get=True)
                    result["checked_missing"] += 1
                after_id = known[-1][0]
            state.last_successful_sync = utc_now()
            state.status, state.error_code = "SUCCESS", None
            resolve_source(db, source_type="OZON_RECONCILIATION_ERROR", source_id=state.id)
            db.add(AuditLog(action="ozon.reconciliation.success",
                            detail=f"received:{result['received']} changed:{result['changed']}"))
            db.commit()
    except Exception as exc:  # noqa: BLE001 - isolate upstream failures from production work
        safe_code = type(exc).__name__ if isinstance(exc, (OzonError, ValidationError)) else "SYNC_ERROR"
        logger.error("Ozon reconciliation failed code=%s", safe_code)
        with Session(engine) as db:
            db.info["settings"] = config
            state = state_for(db, config)
            new_episode = state.error_code is None
            if new_episode:
                state.error_episode += 1
            state.status, state.error_code = "ERROR", safe_code
            task = ensure_task(db, source_type="OZON_RECONCILIATION_ERROR", source_id=state.id,
                               order_id=None, title="Ошибка синхронизации Ozon",
                               description=f"Данные Ozon не обновлены. Код: {safe_code}", severity="HIGH")
            # A new outage reopens the same source task; retries do not undo staff actions.
            if new_episode and task:
                task.status, task.resolved_at = "OPEN", None
            emit(db, type="OZON_SYNC_ERROR",
                 event_key=f"reconciliation:{state.id}:{state.error_episode}",
                 user_ids=manager_ids(db), title="Ошибка синхронизации Ozon",
                 body=f"Данные Ozon не обновлены. Код: {safe_code}. Производство доступно.",
                 url=f"/manager-tasks/{task.id}" if task else "/ozon-integration")
            db.add(AuditLog(action="ozon.reconciliation.error", detail=safe_code))
            db.commit()
        result = {"error_code": safe_code}
    # Also publish unchanged successful runs: freshness and recovery changed.
    try:
        events.publish(0)
    except RuntimeError:
        logger.error("Ozon reconciliation realtime publication unavailable")
    return result


async def reconciliation_loop(engine, client, config, events, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.to_thread(reconcile, engine, client, config, events)
        except Exception:  # noqa: BLE001 - database outage must not kill the scheduler
            logger.error("Ozon reconciliation worker unavailable")
        try:
            await asyncio.wait_for(stop.wait(), timeout=config.ozon_reconciliation_interval_seconds)
        except TimeoutError:
            pass
