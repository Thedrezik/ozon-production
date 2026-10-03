import json
from datetime import timedelta

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, ManagerTask, Notification, OzonCredentials, utc_now
from app.ozon import OzonClient
from app.ozon_credentials import effective_settings, expiration_alerts
from tests.test_orders import login, setup_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    app = setup_app(tmp_path)
    app.state.settings.ozon_credentials_master_key = Fernet.generate_key().decode()
    app.state.settings.ozon_client_id = 'old-id'
    app.state.settings.ozon_api_key = 'old-secret'
    def factory(config):
        def handle(request):
            if request.headers['Api-Key'] == 'bad-secret':
                return httpx.Response(401, json={'secret': 'bad-secret'})
            return httpx.Response(200, json={'roles': []})
        return OzonClient(config, transport=httpx.MockTransport(handle))
    monkeypatch.setattr('app.api_ozon_credentials.OzonClient', factory)
    return app


def replace(client, headers, key='new-secret', days=14):
    return client.put('/api/ozon/integration/credentials', headers=headers, json={
        'api_key': key, 'client_id': 'new-id',
        'expires_at': (utc_now() + timedelta(days=days)).isoformat()})


def test_success_encrypted_api_audit(app):
    with TestClient(app) as client:
        headers = login(client)
        assert replace(client, headers).status_code == 200
        body = client.get('/api/ozon/integration').text
        assert 'new-secret' not in body and 'new-id' not in body and 'api_key' not in body
        with Session(app.state.engine) as db:
            row = db.get(OzonCredentials, 1)
            assert 'new-secret' not in row.encrypted_credentials
            settings = effective_settings(db, app.state.settings)
            assert settings.ozon_api_key == 'new-secret' and settings.ozon_client_id == 'new-id'
            audit = db.scalars(select(AuditLog).where(AuditLog.action.like('ozon.%'))).all()
            assert any(a.action == 'ozon.credentials.replaced' for a in audit)
            assert all('new-secret' not in a.detail and 'new-id' not in a.detail for a in audit)


def test_failed_replacement_preserves_old_and_environment(app):
    with TestClient(app) as client:
        headers = login(client)
        assert replace(client, headers, 'bad-secret').status_code == 502
        with Session(app.state.engine) as db:
            assert db.get(OzonCredentials, 1) is None
            assert effective_settings(db, app.state.settings).ozon_api_key == 'old-secret'
        assert replace(client, headers).status_code == 200
        with Session(app.state.engine) as db:
            old = db.get(OzonCredentials, 1).encrypted_credentials
        assert replace(client, headers, 'bad-secret').status_code == 502
        with Session(app.state.engine) as db:
            assert db.get(OzonCredentials, 1).encrypted_credentials == old
            assert effective_settings(db, app.state.settings).ozon_api_key == 'new-secret'
            assert 'bad-secret' not in json.dumps([a.detail for a in db.scalars(select(AuditLog))])


@pytest.mark.parametrize('role', ['MANAGER', 'VIEWER', 'PRODUCTION_WORKER'])
def test_non_admin_denied(app, role):
    with TestClient(app) as client:
        headers = login(client)
        assert client.post('/api/users', headers=headers, json={'username': 'staff', 'display_name': 'Staff',
            'password': 'staff-password-123', 'roles': [role]}).status_code == 201
        headers = login(client, 'staff', 'staff-password-123')
        assert client.get('/api/ozon/integration').status_code == 403
        assert replace(client, headers).status_code == 403
        assert client.put('/api/ozon/integration/expiration', headers=headers,
                          json={'expires_at': None}).status_code == 403


def test_expiration_thresholds_dedupe_and_resolution(app):
    with TestClient(app) as client:
        headers = login(client)
        assert replace(client, headers, days=20).status_code == 200
        with Session(app.state.engine) as db:
            from datetime import timezone
            expiry = db.get(OzonCredentials, 1).expires_at.replace(tzinfo=timezone.utc)
            for days in [14, 7, 3, 1, 0]:
                now = expiry - timedelta(days=days)
                assert expiration_alerts(db, app.state.settings, now=now) == 1
                assert expiration_alerts(db, app.state.settings, now=now) == 0
            db.commit()
            assert db.query(Notification).filter_by(type='API_KEY_EXPIRING').count() == 5
            assert db.query(ManagerTask).filter_by(source_type='API_KEY_EXPIRING').count() == 1
        assert replace(client, headers, 'another-secret', days=30).status_code == 200
        with Session(app.state.engine) as db:
            assert db.scalar(select(ManagerTask)).status == 'RESOLVED'


def test_missing_master_and_invalid_input_safe(app):
    with TestClient(app) as client:
        headers = login(client)
        body = client.put('/api/ozon/integration/credentials', headers=headers,
                          json={'api_key': 'sensitive-value', 'expires_at': 'sensitive-value'})
        assert body.status_code == 422 and 'sensitive-value' not in body.text
        app.state.settings.ozon_credentials_master_key = ''
        assert replace(client, headers).status_code == 502
        with Session(app.state.engine) as db:
            assert db.get(OzonCredentials, 1) is None


def test_runtime_rotation_restart_and_wrong_master(app, monkeypatch):
    from app.ozon import OzonConfigurationError
    from app.ozon_credentials import ManagedOzonClient
    seen = []

    class Probe:
        def __init__(self, config):
            self.key = config.ozon_api_key
        def check_connection(self):
            seen.append(self.key)
        def close(self):
            pass

    monkeypatch.setattr("app.ozon_credentials.create_ozon_client", Probe)
    real_config = app.state.settings.model_copy(update={"ozon_mock_mode": False})
    runtime = ManagedOzonClient(app.state.engine, real_config)
    runtime.check_connection()
    with TestClient(app) as client:
        headers = login(client)
        assert replace(client, headers).status_code == 200
        runtime.check_connection()
        assert replace(client, headers, "bad-secret").status_code == 502
        runtime.check_connection()
        assert replace(client, headers, "second-secret", days=30).status_code == 200
        runtime.check_connection()
        restarted = ManagedOzonClient(app.state.engine, real_config)
        restarted.check_connection()
        restarted.close()
        assert seen == ["old-secret", "new-secret", "new-secret", "second-secret", "second-secret"]
        with Session(app.state.engine) as db:
            invalid = real_config.model_copy(update={"ozon_credentials_master_key": Fernet.generate_key().decode()})
            with pytest.raises(OzonConfigurationError):
                effective_settings(db, invalid)
    runtime.close()


def test_expiration_update_retires_pending_and_audits(app):
    from app.models import NotificationDelivery, NotificationPreference, User
    with TestClient(app) as client:
        headers = login(client)
        with Session(app.state.engine) as db:
            user = db.scalar(select(User))
            db.add(NotificationPreference(user_id=user.id, type="API_KEY_EXPIRING", channel="WEB_PUSH", enabled=True))
            db.commit()
        assert replace(client, headers, days=1).status_code == 200
        response = client.put('/api/ozon/integration/expiration', headers=headers,
                              json={"expires_at": (utc_now() + timedelta(days=40)).isoformat()})
        assert response.status_code == 200
        current = client.get("/api/ozon/integration").json()["expires_at"]
        assert client.put("/api/ozon/integration/expiration", headers=headers, json={"expires_at": current}).json()["status"] == "UNCHANGED"
        with Session(app.state.engine) as db:
            assert db.get(OzonCredentials, 1).revision == 2
            assert db.scalar(select(ManagerTask)).status == "RESOLVED"
            assert db.scalar(select(NotificationDelivery).where(NotificationDelivery.channel == "WEB_PUSH")).status == "SKIPPED"
            assert db.scalar(select(AuditLog).where(AuditLog.action == "ozon.expiration.updated"))
        response = client.put('/api/ozon/integration/expiration', headers=headers,
                              json={"expires_at": "secret-value"})
        assert response.status_code == 422 and "secret-value" not in response.text


def test_expiration_normalized_utc(app):
    from datetime import datetime, timezone
    with TestClient(app) as client:
        headers = login(client)
        assert replace(client, headers, days=30).status_code == 200
        assert client.put('/api/ozon/integration/expiration', headers=headers,
                          json={"expires_at": "2026-12-01T12:00:00+03:00"}).status_code == 200
        with Session(app.state.engine) as db:
            assert db.get(OzonCredentials, 1).expires_at.replace(tzinfo=timezone.utc) == datetime(2026, 12, 1, 9, tzinfo=timezone.utc)


@pytest.mark.parametrize('upstream,expected', [
    ('2026-12-01T12:00:00+03:00', '2026-12-01T09:00:00+00:00'),
    (None, None), ('invalid-provider-date', None), ('2026-12-01T09:00:00', None),
])
def test_verified_upstream_expiry_and_core_warning_metadata(app, monkeypatch, upstream, expected):
    app.state.settings.enabled_optional_features = ''
    def factory(config):
        return OzonClient(config, transport=httpx.MockTransport(lambda request:
            httpx.Response(200, json={'roles': [], 'expires_at': upstream})))
    monkeypatch.setattr('app.api_ozon_credentials.OzonClient', factory)
    with TestClient(app) as client:
        headers = login(client)
        assert client.put('/api/ozon/integration/credentials', headers=headers,
            json={'client_id': 'new-id', 'api_key': 'new-secret'}).status_code == 200
        status = client.get('/api/ozon/integration').json()
        assert status['expires_at'] == expected
        assert 'new-secret' not in json.dumps(status)


def test_upstream_expiry_takes_precedence_over_manual_date(app, monkeypatch):
    def factory(config):
        return OzonClient(config, transport=httpx.MockTransport(lambda request:
            httpx.Response(200, json={'roles': [], 'expires_at': '2026-12-01T09:00:00Z'})))
    monkeypatch.setattr('app.api_ozon_credentials.OzonClient', factory)
    with TestClient(app) as client:
        headers = login(client)
        assert replace(client, headers, days=30).status_code == 200
        assert client.get('/api/ozon/integration').json()['expires_at'] == '2026-12-01T09:00:00+00:00'
