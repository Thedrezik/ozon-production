import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    NotificationDelivery,
    NotificationPreference,
    TelegramAccount,
    TelegramLink,
)
from app.notifications import emit
from app.telegram import deliver_pending
from tests.test_orders import login, setup_app


def configured_app(tmp_path):
    app = setup_app(tmp_path)
    app.state.settings.telegram_bot_token = "secret-token"
    app.state.settings.telegram_bot_username = "factory_notice_bot"
    app.state.settings.telegram_webhook_secret = "webhook-secret"
    app.state.settings.app_public_url = "https://factory.example"
    return app


def test_secure_one_time_link_flow(tmp_path):
    app = configured_app(tmp_path)
    with TestClient(app) as client:
        headers = login(client)
        assert client.get("/api/telegram/status").json()["linked"] is False
        response = client.post("/api/telegram/link", headers=headers)
        assert response.status_code == 200
        code = response.json()["url"].split("start=")[1]
        with Session(app.state.engine) as db:
            link = db.scalar(select(TelegramLink))
            assert link.code_hash == hashlib.sha256(code.encode()).hexdigest()
            assert code not in link.code_hash
        assert (
            client.post(
                "/api/telegram/webhook",
                json={"message": {"text": f"/start {code}", "chat": {"id": 123, "type": "private"}}},
            ).status_code
            == 403
        )
        result = client.post(
            "/api/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
            json={"message": {"text": f"/start {code}", "chat": {"id": 123, "type": "private"}}},
        )
        assert result.json() == {"ok": True}
        assert client.get("/api/telegram/status").json()["linked"] is True
        with Session(app.state.engine) as db:
            assert db.scalar(select(TelegramLink)) is None
            assert db.scalar(select(TelegramAccount)).chat_id == "123"


def test_existing_queue_preference_failure_and_no_duplicate(tmp_path):
    app = configured_app(tmp_path)
    with Session(app.state.engine) as db:
        db.add(TelegramAccount(user_id=1, chat_id="123"))
        db.add(
            NotificationPreference(
                user_id=1, type="BLOCKER_CREATED", channel="TELEGRAM", enabled=True
            )
        )
        assert (
            emit(
                db,
                type="BLOCKER_CREATED",
                event_key="blocker:7",
                user_ids=[1],
                title="Заказ 123",
                body="Нет кромки",
                url="/manager-tasks/4",
            )
            == 1
        )
        assert (
            emit(
                db,
                type="BLOCKER_CREATED",
                event_key="blocker:7",
                user_ids=[1],
                title="Заказ 123",
                body="Нет кромки",
                url="/manager-tasks/4",
            )
            == 0
        )
        db.commit()
    sent = []
    deliver_pending(
        app.state.engine,
        app.state.settings,
        lambda token, chat, message, _url: sent.append((token, chat, message)),
    )
    deliver_pending(
        app.state.engine,
        app.state.settings,
        lambda token, chat, message, _url: sent.append((token, chat, message)),
    )
    assert len(sent) == 1
    assert (
        sent[0][0] == "secret-token"
        and "https://factory.example/manager-tasks/4" in sent[0][2]
    )
    with Session(app.state.engine) as db:
        delivery = db.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.channel == "TELEGRAM"
            )
        )
        assert delivery.status == "DELIVERED"

    # A pending delivery is suppressed if the user disables its event type before send.
    with Session(app.state.engine) as db:
        emit(
            db,
            type="BLOCKER_CREATED",
            event_key="blocker:8",
            user_ids=[1],
            title="Новый блокер",
            body="Описание",
        )
        db.commit()
        db.scalar(
            select(NotificationPreference).where(
                NotificationPreference.channel == "TELEGRAM"
            )
        ).enabled = False
        db.commit()
    deliver_pending(
        app.state.engine, app.state.settings, lambda *_args: sent.append("unexpected")
    )
    with Session(app.state.engine) as db:
        rows = db.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.channel == "TELEGRAM"
            )
        ).all()
        assert sorted(row.status for row in rows) == ["DELIVERED", "SKIPPED"]


def test_provider_error_is_retried_without_crashing(tmp_path):
    app = configured_app(tmp_path)
    with Session(app.state.engine) as db:
        db.add(TelegramAccount(user_id=1, chat_id="123"))
        db.add(
            NotificationPreference(
                user_id=1, type="READY_TO_SHIP", channel="TELEGRAM", enabled=True
            )
        )
        emit(
            db,
            type="READY_TO_SHIP",
            event_key="order:1",
            user_ids=[1],
            title="Готово",
            body="К отгрузке",
        )
        db.commit()
    deliver_pending(
        app.state.engine,
        app.state.settings,
        lambda *_args: (_ for _ in ()).throw(RuntimeError("private provider payload")),
    )
    with Session(app.state.engine) as db:
        delivery = db.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.channel == "TELEGRAM"
            )
        )
        assert (
            delivery.status == "PENDING"
            and delivery.attempts == 1
            and delivery.next_attempt_at is not None
        )
