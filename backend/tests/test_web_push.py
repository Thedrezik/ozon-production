import base64
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from pywebpush import WebPushException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    NotificationDelivery,
    NotificationPreference,
    PushSubscription,
    utc_now,
)
from app.notifications import emit
from app.web_push import deliver_pending
from tests.test_orders import login, setup_app


def payload(suffix="one"):
    key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint)
    return {"endpoint": f"https://fcm.googleapis.com/fcm/send/{suffix}", "keys": {
        "p256dh": base64.urlsafe_b64encode(key).decode().rstrip("="),
        "auth": base64.urlsafe_b64encode(b"a" * 16).decode().rstrip("=")}}


def prepare(tmp_path):
    app = setup_app(tmp_path)
    app.state.settings.vapid_public_key = "public"
    app.state.settings.vapid_private_key = "private"
    app.state.settings.vapid_subject = "mailto:admin@example.com"
    return app


def queue(app):
    with Session(app.state.engine) as db:
        db.add(NotificationPreference(user_id=1, type="NEW_ORDER", channel="WEB_PUSH", enabled=True))
        assert emit(db, type="NEW_ORDER", event_key="one", user_ids=[1], title="Заказ", body="Новый",
                    url="/orders/1") == 1
        assert emit(db, type="NEW_ORDER", event_key="one", user_ids=[1], title="Заказ", body="Новый") == 0
        db.commit()


def subscribe(app, value=None):
    # No configured background worker in this test; manually run the real adapter.
    app.state.settings.vapid_private_key = ""
    with TestClient(app) as client:
        headers = login(client)
        app.state.settings.vapid_private_key = "private"
        result = client.post("/api/push/subscriptions", headers=headers, json=value or payload())
        assert result.status_code == 201
        saved = result.json()
    return saved


def test_subscription_create_delete_auth_csrf_and_validation(tmp_path):
    app = setup_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/push/config").status_code == 401
        headers = login(client)
        value = payload()
        assert client.post("/api/push/subscriptions", headers=headers, json=value).status_code == 503
        app.state.settings.vapid_public_key = "public"
        app.state.settings.vapid_private_key = "private"
        app.state.settings.vapid_subject = "mailto:admin@example.com"
        assert "private" not in client.get("/api/push/config").text
        assert client.post("/api/push/subscriptions", json=value).status_code == 403
        first = client.post("/api/push/subscriptions", headers=headers, json=value)
        assert first.status_code == 201
        assert client.post("/api/push/subscriptions", headers=headers, json=value).json() == first.json()
        assert client.post("/api/push/subscriptions", headers=headers,
                           json={**value, "endpoint": "https://127.0.0.1/internal"}).status_code == 422
        assert client.post("/api/push/subscriptions", headers=headers,
                           json={**value, "keys": {"p256dh": "x", "auth": "x"}}).status_code == 422
        assert client.delete("/api/push/subscriptions", headers=headers).status_code == 422
        assert client.request("DELETE", "/api/push/subscriptions", headers=headers,
                              json={"endpoint": value["endpoint"]}).status_code == 200
        with Session(app.state.engine) as db:
            assert db.scalar(select(PushSubscription)) is None


def test_existing_queue_delivery_and_no_duplicate(tmp_path):
    app = prepare(tmp_path)
    subscribe(app)
    queue(app)
    sent = []
    deliver_pending(app.state.engine, app.state.settings, lambda **kwargs: sent.append(kwargs))
    deliver_pending(app.state.engine, app.state.settings, lambda **kwargs: sent.append(kwargs))
    assert len(sent) == 1
    assert json.loads(sent[0]["data"])["url"] == "/orders/1"
    with Session(app.state.engine) as db:
        assert db.scalar(select(NotificationDelivery).where(
            NotificationDelivery.channel == "WEB_PUSH")).status == "DELIVERED"


@pytest.mark.parametrize("code", [404, 410])
def test_invalid_expired_subscription_removed(tmp_path, code):
    app = prepare(tmp_path)
    subscribe(app)
    queue(app)
    def expired(**kwargs):
        raise WebPushException("expired", response=SimpleNamespace(status_code=code))
    deliver_pending(app.state.engine, app.state.settings, expired)
    with Session(app.state.engine) as db:
        assert db.scalar(select(PushSubscription)) is None


def test_disabled_preference_suppresses_pending_delivery(tmp_path):
    app = prepare(tmp_path)
    subscribe(app)
    queue(app)
    with Session(app.state.engine) as db:
        db.scalar(select(NotificationPreference)).enabled = False
        db.commit()
        assert emit(db, type="NEW_ORDER", event_key="two", user_ids=[1], title="New", body="New") == 1
        db.commit()
        assert len(db.scalars(select(NotificationDelivery).where(
            NotificationDelivery.channel == "WEB_PUSH")).all()) == 1
    sent = []
    deliver_pending(app.state.engine, app.state.settings, lambda **kwargs: sent.append(kwargs))
    assert not sent


def test_retry_does_not_repeat_successful_device(tmp_path):
    app = prepare(tmp_path)
    subscribe(app, payload("one"))
    subscribe(app, payload("two"))
    queue(app)
    sent = []
    def partial(**kwargs):
        endpoint = kwargs["subscription_info"]["endpoint"]
        if endpoint.endswith("two"):
            raise WebPushException("temporary", response=SimpleNamespace(status_code=503))
        sent.append(endpoint)
    deliver_pending(app.state.engine, app.state.settings, partial)
    with Session(app.state.engine) as db:
        delivery = db.scalar(select(NotificationDelivery).where(NotificationDelivery.channel == "WEB_PUSH"))
        assert delivery.status == "PENDING"
        delivery.next_attempt_at = utc_now() - timedelta(seconds=1)
        db.commit()
    deliver_pending(app.state.engine, app.state.settings,
                    lambda **kwargs: sent.append(kwargs["subscription_info"]["endpoint"]))
    assert len(sent) == 2 and sent[0] != sent[1]


def test_real_transport_encrypts_with_generated_vapid_keys(tmp_path, monkeypatch):
    import requests

    from app.push_keys import generate
    from app.web_push import webpush

    path = tmp_path / ".env.vapid"
    generate(path)
    settings = dict(line.split("=", 1) for line in path.read_text().splitlines())
    calls = []
    def accepted(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=201, text="", headers={})
    monkeypatch.setattr(requests, "post", accepted)
    webpush(subscription_info=payload(), data='{"title":"Test"}',
            vapid_private_key=settings["VAPID_PRIVATE_KEY"],
            vapid_claims={"sub": settings["VAPID_SUBJECT"]}, timeout=10, ttl=3600)
    assert len(calls) == 1
    assert calls[0][1]["data"] != b'{"title":"Test"}'
    assert calls[0][1]["headers"]["authorization"].startswith("vapid ")


def test_retry_limit_and_no_replay_to_later_subscription(tmp_path):
    app = prepare(tmp_path)
    queue(app)
    subscribe(app)
    sent = []
    deliver_pending(app.state.engine, app.state.settings, lambda **kwargs: sent.append(kwargs))
    assert not sent  # A new device cannot receive earlier queued notifications.
    with Session(app.state.engine) as db:
        emit(db, type="NEW_ORDER", event_key="later", user_ids=[1], title="New", body="New")
        db.commit()
    def unavailable(**kwargs):
        raise WebPushException("temporary", response=SimpleNamespace(status_code=503))
    for _ in range(5):
        with Session(app.state.engine) as db:
            delivery = db.scalars(select(NotificationDelivery).where(
                NotificationDelivery.channel == "WEB_PUSH").order_by(NotificationDelivery.id.desc())).first()
            delivery_id = delivery.id
            delivery.next_attempt_at = utc_now() - timedelta(seconds=1)
            db.commit()
        deliver_pending(app.state.engine, app.state.settings, unavailable)
    with Session(app.state.engine) as db:
        assert db.get(NotificationDelivery, delivery_id).status == "FAILED"


def test_background_worker_consumes_existing_delivery_queue(tmp_path, monkeypatch):
    import threading


    app = prepare(tmp_path)
    subscribe(app)
    queue(app)
    accepted = threading.Event()
    sent = []
    def sender(**kwargs):
        sent.append(kwargs)
        accepted.set()
    monkeypatch.setattr("app.web_push.webpush", sender)
    with TestClient(app):
        assert accepted.wait(timeout=5)
    assert len(sent) == 1
    with Session(app.state.engine) as db:
        assert db.scalar(select(NotificationDelivery).where(
            NotificationDelivery.channel == "WEB_PUSH")).status == "DELIVERED"


def test_subscription_belongs_to_current_user(tmp_path):
    app = prepare(tmp_path)
    value = payload()
    subscribe(app, value)
    app.state.settings.vapid_private_key = ""
    with TestClient(app) as client:
        headers = login(client)
        response = client.post("/api/users", headers=headers, json={
            "username": "push-viewer", "display_name": "Viewer", "password": "viewer-password-123", "roles": ["VIEWER"]})
        assert response.status_code == 201
        headers = login(client, "push-viewer", "viewer-password-123")
        app.state.settings.vapid_private_key = "private"
        assert client.post("/api/push/subscriptions", headers=headers, json=value).status_code == 409
        assert client.request("DELETE", "/api/push/subscriptions", headers=headers,
                              json={"endpoint": value["endpoint"]}).status_code == 200
    with Session(app.state.engine) as db:
        assert db.scalar(select(PushSubscription)).user_id == 1


def test_test_notice_uses_same_queue_and_preference(tmp_path):
    app = prepare(tmp_path)
    subscribe(app)
    app.state.settings.vapid_private_key = ""
    with TestClient(app) as client:
        headers = login(client)
        assert client.put("/api/notifications/preferences", headers=headers,
                          json={"type": "NEW_ORDER", "channel": "WEB_PUSH", "enabled": True}).status_code == 200
        assert client.post("/api/push/test", headers=headers).status_code == 200
    app.state.settings.vapid_private_key = "private"
    sent = []
    deliver_pending(app.state.engine, app.state.settings, lambda **kwargs: sent.append(kwargs))
    assert len(sent) == 1 and json.loads(sent[0]["data"])["title"] == "Тест Web Push"
