import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.auth import COOKIE_NAME, hash_password, verify_password
from app.cli import create_admin
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import AuditLog, User
from app.rbac import seed_rbac


@pytest.fixture
def setup(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'auth.db'}"))
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as db:
        seed_rbac(db)
        db.commit()
        admin = create_admin("admin", "Administrator", "admin-password-123", db)
        admin_id = admin.id
    with TestClient(app) as client:
        yield client, app.state.engine, admin_id


def login(client, username="admin", password="admin-password-123"):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["csrf_token"]


def create_worker(client, csrf, username="worker"):
    response = client.post(
        "/api/users", headers={"X-CSRF-Token": csrf},
        json={"username": username, "display_name": "Worker", "password": "worker-password-123", "roles": ["PRODUCTION_WORKER"]},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_password_hashing_and_admin_creation(setup):
    client, engine, admin_id = setup
    with Session(engine) as db:
        admin = db.get(User, admin_id)
        assert admin.password_hash != "admin-password-123"
        assert admin.password_hash.startswith("scrypt$")
        assert verify_password(admin.password_hash, "admin-password-123")
        assert not verify_password(admin.password_hash, "wrong")
        with pytest.raises(ValueError, match="already exists"):
            create_admin("ADMIN", "Again", "another-password-123", db)
    assert hash_password("some-password-123") != hash_password("some-password-123")
    assert client.get("/api/auth/me").status_code == 401


def test_create_admin_cli_command(tmp_path, monkeypatch, capsys):
    database_url = f"sqlite:///{tmp_path / 'cli.db'}"
    app = create_app(Settings(database_url=database_url))
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as db:
        seed_rbac(db)
        db.commit()
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(database_url=database_url))
    monkeypatch.setattr("sys.argv", ["app.cli", "create-admin", "--username", "first", "--display-name", "First Admin"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "first-password-123")
    assert cli.main() == 0
    assert "first-password-123" not in capsys.readouterr().out
    with Session(app.state.engine) as db:
        assert db.scalar(select(User).where(User.username == "first")) is not None


def test_login_me_logout_and_invalid_login(setup):
    client, engine, admin_id = setup
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    csrf = login(client)
    assert client.cookies.get(COOKIE_NAME)
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == admin_id
    assert "users.manage" in me.json()["permissions"]
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    with Session(engine) as db:
        actions = db.scalars(select(AuditLog.action)).all()
    assert {"login.failure", "login.success", "logout"} <= set(actions)


def test_permissions_role_assignment_and_inactive_user(setup):
    client, engine, _ = setup
    csrf = login(client)
    worker_id = create_worker(client, csrf)
    assert client.put(f"/api/users/{worker_id}/roles", headers={"X-CSRF-Token": csrf}, json={"roles": ["PRODUCTION_WORKER", "VIEWER"]}).status_code == 200
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    worker_csrf = login(client, "worker", "worker-password-123")
    assert client.get("/api/users").status_code == 403
    assert client.post("/api/users", headers={"X-CSRF-Token": worker_csrf}, json={"username": "x", "display_name": "X", "password": "password-123456", "roles": ["ADMIN"]}).status_code == 403
    assert client.get("/api/auth/me").json()["roles"] == ["PRODUCTION_WORKER", "VIEWER"]
    client.post("/api/auth/logout", headers={"X-CSRF-Token": worker_csrf})
    csrf = login(client)
    assert client.post(f"/api/users/{worker_id}/deactivate", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "worker", "password": "worker-password-123"}).status_code == 401
    with Session(engine) as db:
        actions = db.scalars(select(AuditLog.action)).all()
    assert {"user.created", "role.changed", "user.deactivated"} <= set(actions)


def test_role_change_revokes_session_and_last_admin_is_guarded(setup):
    client, _, admin_id = setup
    csrf = login(client)
    assert client.put(f"/api/users/{admin_id}/roles", headers={"X-CSRF-Token": csrf}, json={"roles": ["VIEWER"]}).status_code == 409
    assert client.post(f"/api/users/{admin_id}/deactivate", headers={"X-CSRF-Token": csrf}).status_code == 409
    worker_id = create_worker(client, csrf)
    worker_csrf = login(client, "worker", "worker-password-123")
    assert worker_csrf
    # Authenticate as admin in a separate client so the worker cookie remains intact.
    admin_client = TestClient(client.app)
    admin_csrf = login(admin_client)
    assert admin_client.put(f"/api/users/{worker_id}/roles", headers={"X-CSRF-Token": admin_csrf}, json={"roles": ["VIEWER"]}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_admin_cannot_manage_super_admin_and_deactivation_revokes_session(setup):
    client, _, admin_id = setup
    csrf = login(client)
    worker_id = create_worker(client, csrf)
    response = client.put(f"/api/users/{worker_id}/roles", headers={"X-CSRF-Token": csrf}, json={"roles": ["ADMIN"]})
    assert response.status_code == 200
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    admin_role_csrf = login(client, "worker", "worker-password-123")
    assert client.post(f"/api/users/{admin_id}/deactivate", headers={"X-CSRF-Token": admin_role_csrf}).status_code == 403
    assert client.put(f"/api/users/{admin_id}/roles", headers={"X-CSRF-Token": admin_role_csrf}, json={"roles": ["VIEWER"]}).status_code == 403
    super_client = TestClient(client.app)
    super_csrf = login(super_client)
    assert super_client.post(f"/api/users/{worker_id}/deactivate", headers={"X-CSRF-Token": super_csrf}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_change_and_reset_password(setup):
    client, engine, _ = setup
    csrf = login(client)
    worker_id = create_worker(client, csrf)
    assert client.post("/api/auth/change-password", headers={"X-CSRF-Token": csrf}, json={"current_password": "wrong", "new_password": "new-admin-password-123"}).status_code == 400
    assert client.post("/api/auth/change-password", headers={"X-CSRF-Token": csrf}, json={"current_password": "admin-password-123", "new_password": "new-admin-password-123"}).status_code == 200
    assert client.post(f"/api/users/{worker_id}/reset-password", headers={"X-CSRF-Token": csrf}, json={"new_password": "reset-worker-password-123"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "worker", "password": "worker-password-123"}).status_code == 401
    assert login(client, "worker", "reset-worker-password-123")
    with Session(engine) as db:
        actions = db.scalars(select(AuditLog.action)).all()
    assert {"password.changed", "password.reset"} <= set(actions)


def test_login_rate_limit(setup):
    client, _, _ = setup
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "missing", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "missing", "password": "wrong"}).status_code == 429
