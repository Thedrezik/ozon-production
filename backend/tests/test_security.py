import asyncio
import hashlib
import json
import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME, LoginLimiter, hash_password, verify_password
from app.config import Settings
from app.logging import JsonFormatter, configure_logging
from app.main import create_app
from app.models import AuditLog, TelegramAccount, User, utc_now
from app.models import Session as LoginSession
from app.orders import seed_mock_orders
from app.security import SECURITY_HEADERS
from tests.test_orders import login, setup_app


@pytest.fixture
def context(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
    with TestClient(app) as client:
        yield app, client


def production_settings(**changes):
    values = {"_env_file": None, "app_env": "production", "ozon_mock_mode": False,
              "domain": "factory.example.org",
              "app_public_url": "https://factory.example.org", "app_secret": "s" * 40,
              "database_url": "postgresql+psycopg://ozon:random-long-db-password@postgres/ozon",
              "ozon_credentials_master_key": Fernet.generate_key().decode()}
    return Settings(**(values | changes))


@pytest.mark.parametrize("changes", [
    {"ozon_mock_mode": True}, {"app_secret": "replace-with-a-long-random-secret"},
    {"database_url": "postgresql+psycopg://ozon:ozon@postgres/ozon"},
    {"database_url": "sqlite:///production.db"}, {"app_public_url": "http://factory.example.org"},
    {"app_public_url": "https://example.com"}, {"ozon_credentials_master_key": ""},
    {"telegram_bot_token": "configured-but-incomplete"}, {"vapid_private_key": "incomplete"},
    {"ozon_webhook_trusted_proxies": "0.0.0.0/0"}, {"app_env": "Production"},
    {"domain": ":80"}, {"domain": "other.example.org"},
])
def test_production_fails_closed(changes):
    with pytest.raises(ValidationError):
        production_settings(**changes)


def test_startup_validation_does_not_echo_secrets():
    secret = "private-startup-secret-sentinel"
    with pytest.raises(ValidationError) as error:
        production_settings(ozon_api_key=secret, ozon_mock_mode=True)
    assert secret not in str(error.value)


def test_production_headers_docs_host_and_cookie(context):
    app, _ = context
    production = create_app(production_settings())
    # Use a migrated synthetic database; no production database or Ozon request.
    production.state.engine.dispose()
    production.state.engine = app.state.engine
    with TestClient(production, base_url="https://factory.example.org") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
        response = client.post("/api/auth/login", json={"username": "admin", "password": "admin-password-123"})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert all(flag in cookie for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/api"))
        assert "Domain=" not in cookie
        assert response.headers["strict-transport-security"] == "max-age=31536000"
        for key, value in SECURITY_HEADERS.items():
            assert response.headers[key] == value
        logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": response.json()["csrf_token"]})
        assert logout.status_code == 200
        assert all(flag in logout.headers["set-cookie"] for flag in ("HttpOnly", "Secure", "SameSite=strict"))
        assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400


@pytest.mark.parametrize("path", ["/api/users", "/api/audit", "/api/ozon/integration", "/api/product-profiles",
                                       "/api/orders", "/api/push/config", "/api/telegram/status"])
def test_sensitive_reads_require_auth(context, path):
    _, client = context
    assert client.get(path).status_code == 401


def test_worker_forbidden_admin_and_audit_paths(context):
    _, client = context
    headers = login(client)
    worker = client.post("/api/users", headers=headers, json={"username": "worker", "display_name": "Worker",
                        "password": "worker-password-123", "roles": ["PRODUCTION_WORKER"]}).json()
    headers = login(client, "worker", "worker-password-123")
    for path in ("/api/audit", "/api/ozon/integration", "/api/product-profiles"):
        assert client.get(path).status_code == 403
    for method, path, body in (
        ("PUT", f"/api/users/{worker['id']}/roles", {"roles": ["SUPER_ADMIN"]}),
        ("POST", "/api/users/1/reset-password", {"new_password": "attacker-password-123"}),
        ("POST", "/api/users/1/deactivate", {}),
        ("PUT", "/api/ozon/integration/credentials", {"api_key": "malicious"}),
        ("POST", "/api/ozon/webhook/events/1/retry", {}),
    ):
        assert client.request(method, path, headers=headers, json=body).status_code == 403


def test_admin_target_and_super_admin_removal_are_locked():
    from app.api_auth import ensure_super_admin_remains, managed_user

    statements = []
    target = SimpleNamespace(id=7, roles=[SimpleNamespace(name="SUPER_ADMIN")], is_active=True)

    def scalar(statement):
        statements.append(statement)
        return target if len(statements) <= 2 else 0

    db = SimpleNamespace(scalar=scalar)
    assert managed_user(db, 7) is target
    assert statements[0]._for_update_arg is not None
    with pytest.raises(Exception) as error:
        ensure_super_admin_remains(db, target)
    assert error.value.status_code == 409
    assert statements[1]._for_update_arg is not None
    assert statements[1].column_descriptions[0]["entity"].__name__ == "Role"


def test_origin_csrf_cors_and_error_headers(context):
    _, client = context
    headers = login(client)
    for other in ({}, {"X-CSRF-Token": "forged"}, {**headers, "Origin": "https://evil.example"},
                  {**headers, "Origin": "https://testserver"}, {**headers, "Sec-Fetch-Site": "cross-site"}):
        assert client.post("/api/auth/logout", headers=other).status_code == 403
    assert client.post("/api/auth/login", headers={"Origin": "https://evil.example"},
                       json={"username": "admin", "password": "admin-password-123"}).status_code == 403
    response = client.options("/api/users", headers={"Origin": "https://evil.example",
                              "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in response.headers
    for key, value in SECURITY_HEADERS.items():
        assert response.headers[key] == value


def test_large_json_rejected_before_parsing(context):
    _, client = context
    response = client.post("/api/auth/login", content=b"x" * (256 * 1024 + 1),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_password_reset_revokes_all_sessions(context):
    app, client = context
    headers = login(client)
    worker = client.post("/api/users", headers=headers, json={"username": "worker", "display_name": "Worker",
                        "password": "worker-password-123", "roles": ["PRODUCTION_WORKER"]}).json()
    with TestClient(app) as other:
        login(other, "worker", "worker-password-123")
        assert client.post(f"/api/users/{worker['id']}/reset-password", headers=headers,
                           json={"new_password": "new-worker-password-123"}).status_code == 200
        assert other.get("/api/auth/me").status_code == 401


def test_change_password_guessing_is_limited(context):
    _, client = context
    headers = login(client)
    for _ in range(5):
        assert client.post("/api/auth/change-password", headers=headers,
                           json={"current_password": "wrong", "new_password": "strong-new-password-123"}).status_code == 400
    assert client.post("/api/auth/change-password", headers=headers,
                       json={"current_password": "wrong", "new_password": "strong-new-password-123"}).status_code == 429


def test_cookie_replay_expiry_and_non_ascii(context):
    app, client = context
    headers = login(client)
    token = client.cookies.get(COOKIE_NAME)
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    client.cookies.set(COOKIE_NAME, token)
    assert client.get("/api/auth/me").status_code == 401
    login(client)
    with Session(app.state.engine) as db:
        for row in db.scalars(select(LoginSession)):
            row.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    assert client.get("/api/auth/me", headers={"cookie": f'{COOKIE_NAME}="\\351"'}).status_code == 401


def test_legacy_hash_upgrades_on_login(context):
    app, client = context
    salt = b"1" * 16
    digest = hashlib.scrypt(b"admin-password-123", salt=salt, n=32768, r=8, p=1, maxmem=64*1024*1024)
    legacy = f"scrypt$32768$8$1${salt.hex()}${digest.hex()}"
    assert verify_password(legacy, "admin-password-123")
    with Session(app.state.engine) as db:
        db.scalar(select(User).where(User.username == "admin")).password_hash = legacy
        db.commit()
    login(client)
    with Session(app.state.engine) as db:
        assert db.scalar(select(User).where(User.username == "admin")).password_hash.startswith("scrypt$32768$8$3$")
    assert hash_password("strong-password-123").startswith("scrypt$32768$8$3$")


def test_limiter_reserves_concurrent_attempts_and_rotating_usernames(context):
    app, client = context
    limiter = LoginLimiter()
    for _ in range(5):
        limiter.check("same", reserve=True)
    with pytest.raises(Exception) as error:
        limiter.check("same", reserve=True)
    assert error.value.status_code == 429
    # Prime the shared peer budget; changing username/forwarded IP cannot bypass it.
    for _ in range(60):
        app.state.login_limiter.check("ip:testclient", limit=60, reserve=True)
    response = client.post("/api/auth/login", headers={"X-Forwarded-For": "8.8.8.8"},
                           json={"username": "rotating", "password": "wrong"})
    assert response.status_code == 429


def test_secrets_not_in_validation_audit_or_logs(context):
    app, client = context
    secret = "do-not-echo-this-password"
    response = client.post("/api/auth/login", json={"username": "x", "password": {"secret": secret}})
    assert response.status_code == 422 and secret not in response.text
    login(client)
    with Session(app.state.engine) as db:
        db.add(AuditLog(action="security.test", detail=f"password={secret}",
                        new_value={"nested": [{"api_key": secret}]}, user_agent=f"token={secret}"))
        db.commit()
        row = db.scalar(select(AuditLog).where(AuditLog.action == "security.test"))
        assert secret not in json.dumps([row.detail, row.new_value, row.user_agent])
    record = logging.LogRecord("test", logging.WARNING, "", 1,
                               f"https://api.telegram.org/bot{secret}/sendMessage password={secret}", (), None)
    assert secret not in JsonFormatter().format(record)


@pytest.mark.parametrize("message", [
    'Authorization: Bearer private-secret-value',
    'Authorization=Basic private-secret-value',
    '{"api_key":"private-secret-value"}',
    '{"password_hash":"private-secret-value"}',
    'Cookie: ozon_session=private-secret-value',
])
def test_sensitive_text_redaction(message):
    record = logging.LogRecord("test", logging.WARNING, "", 1, message, (), None)
    assert "private-secret-value" not in JsonFormatter().format(record)


def test_uvicorn_errors_use_safe_formatter():
    logger = logging.getLogger("uvicorn.error")
    logger.addHandler(logging.StreamHandler())
    configure_logging(Settings(_env_file=None))
    assert not logger.handlers and logger.propagate
    assert not logging.getLogger("uvicorn").handlers
    root = logging.getLogger()
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
    try:
        raise RuntimeError("unlabelled-private-exception-secret")
    except RuntimeError:
        import sys

        record = logging.LogRecord("uvicorn.error", logging.ERROR, "", 1, "Exception in ASGI application", (), sys.exc_info())
    assert "unlabelled-private-exception-secret" not in JsonFormatter().format(record)


def test_sql_injection_and_xss_are_inert_data(context):
    app, client = context
    assert client.post("/api/auth/login", json={"username": "admin' OR 1=1 --", "password": "wrong"}).status_code == 401
    headers = login(client)
    assert client.get("/api/files/resolve", params={"payload": "' OR 1=1 --"}).status_code == 404
    assert client.get("/api/orders", params={"q": "' OR 1=1 --"}).json()["total"] == 0
    order = client.get("/api/orders").json()["items"][0]
    payload = '<img src=x onerror="alert(document.cookie)"><script>alert(1)</script>'
    response = client.post(f"/api/orders/{order['id']}/comments", headers=headers, json={"body": payload})
    assert response.status_code == 201 and response.json()["body"] == payload
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-content-type-options"] == "nosniff"
    with Session(app.state.engine) as db:
        assert db.scalar(select(User).where(User.username == "admin")) is not None


def test_unexpected_errors_do_not_leak(context):
    app, _ = context

    @app.get("/api/test-failure")
    def failure():
        raise RuntimeError("password=secret-test-database-dsn")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/test-failure")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["x-frame-options"] == "DENY"


def test_telegram_oversize_and_deactivated_link(context):
    app, client = context
    app.state.settings.telegram_bot_token = "fake-token"
    app.state.settings.telegram_bot_username = "fake_bot"
    app.state.settings.telegram_webhook_secret = "fake-secret"
    headers = login(client)
    url = client.post("/api/telegram/link", headers=headers).json()["url"]
    code = url.split("start=")[1]
    with Session(app.state.engine) as db:
        db.scalar(select(User).where(User.username == "admin")).is_active = False
        db.commit()
    webhook_headers = {"X-Telegram-Bot-Api-Secret-Token": "fake-secret"}
    assert client.post("/api/telegram/webhook", headers=webhook_headers, content=b"x" * 65537).status_code == 413
    response = client.post("/api/telegram/webhook", headers=webhook_headers,
                           json={"message": {"text": f"/start {code}", "chat": {"id": 123, "type": "private"}}})
    assert response.status_code == 200
    with Session(app.state.engine) as db:
        assert db.scalar(select(TelegramAccount)) is None


def test_sse_reauth_deadline_cannot_be_extended_by_events(monkeypatch):
    from app import api_orders

    async def scenario():
        queue = asyncio.Queue()
        queue.put_nowait(42)
        released = []
        bus = SimpleNamespace(subscribe=lambda: queue, unsubscribe=lambda item: released.append(item), checkpoint=lambda: "test:1")

        async def connected():
            return False

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(order_events=bus)), is_disconnected=connected)
        monkeypatch.setattr(api_orders, "user_permissions", lambda _: {"orders.view"})
        clock = iter([0, 0, 21, 21])
        monkeypatch.setattr(asyncio, "get_running_loop", lambda: SimpleNamespace(time=lambda: next(clock)))
        closed = []
        async def pause(_seconds):
            pass
        monkeypatch.setattr(asyncio, "sleep", pause)
        response = await api_orders.events(request, SimpleNamespace(close=lambda: closed.append(True)), (None, None))
        output = [item async for item in response.body_iterator]
        assert output == [": connected\n\n", "event: ready\ndata: test:1\n\n", "id: test:1\nevent: orders\ndata: 42\n\n"]
        assert released == [queue]
        assert closed == [True]

    asyncio.run(scenario())
