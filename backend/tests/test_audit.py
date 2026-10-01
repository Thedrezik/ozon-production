import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import AuditLog, OzonCredentials, Permission, Role, utc_now
from app.orders import seed_mock_orders
from tests.test_orders import login, setup_app


def test_status_assignment_priority_bulk_roles_and_context(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
    with TestClient(app) as client:
        headers = login(client) | {"User-Agent": "audit-test"}
        user = client.post('/api/users', headers=headers, json={"username": "worker", "display_name": "Worker",
            "password": "worker-password-123", "roles": ["PRODUCTION_WORKER"]}).json()
        oid = client.get('/api/orders?status=QUEUED').json()['items'][0]['id']
        assert client.put(f'/api/orders/{oid}/assignment', headers=headers, json={'user_id': user['id']}).status_code == 200
        assert client.put(f'/api/orders/{oid}/priority', headers=headers, json={'level': 'P1', 'pinned': True}).status_code == 200
        assert client.post(f'/api/orders/{oid}/status', headers=headers, json={'status': 'IN_PRODUCTION'}).status_code == 200
        assert client.post('/api/orders/bulk', headers=headers, json={'order_ids': [oid], 'action': 'assign', 'user_id': None}).status_code == 200
        assert client.put(f"/api/users/{user['id']}/roles", headers=headers, json={'roles': ['PACKER']}).status_code == 200
        rows = client.get('/api/audit?limit=100').json()['items']
        status = next(r for r in rows if r['entity_id'] == str(oid) and r['action'] == 'orders.updated' and r['new_value']['internal_status'] == 'IN_PRODUCTION')
        assert status['old_value']['internal_status'] == 'QUEUED'
        assert status['user_id'] == 1 and status['ip'] == 'testclient' and status['user_agent'] == 'audit-test'
        assert any(r['action'] == 'assignments.created' and r['new_value']['user_id'] == user['id'] for r in rows)
        assert any(r['action'] == 'assignments.deleted' and r['old_value']['user_id'] == user['id'] for r in rows)
        assert any(r['action'] == 'orders.updated' and r['new_value']['priority_override'] == 'P1' and r['new_value']['priority_pinned'] for r in rows)
        role = next(r for r in rows if r['action'] == 'users.updated' and r['entity_id'] == str(user['id']))
        assert role['old_value']['roles'] == ['PRODUCTION_WORKER'] and role['new_value']['roles'] == ['PACKER']
        bulk = next(r for r in rows if r['action'] == 'order.bulk_assign')
        assert bulk['new_value']['order_ids'] == [oid]
        assert 'worker-password-123' not in json.dumps(rows)


def test_permissions_integration_and_recursive_secret_exclusion(tmp_path, caplog):
    app = setup_app(tmp_path)
    secret = 'UNIQUE-SECRET-DO-NOT-STORE'
    with Session(app.state.engine) as db:
        role = db.scalar(select(Role).where(Role.name == 'VIEWER'))
        role.permissions.append(db.scalar(select(Permission).where(Permission.name == 'audit.view')))
        db.add(OzonCredentials(id=1, encrypted_credentials=secret, revision=1))
        db.commit()
        row = db.get(OzonCredentials, 1)
        row.revision = 2
        row.expires_at = utc_now() + timedelta(days=10)
        db.add(AuditLog(action='test.safe', old_value={'nested': [{'password': secret, 'api_key': secret}]},
                       new_value={key: secret for key in ['client_secret', 'master_key', 'session_token', 'csrf_token', 'telegram_bot_token', 'vapid_private_key']}))
        db.commit()
        rows = db.scalars(select(AuditLog)).all()
        assert secret not in json.dumps([(r.old_value, r.new_value, r.detail) for r in rows])
        changed = next(r for r in rows if r.action == 'ozon_credentials.updated')
        assert changed.old_value['revision'] == 1 and changed.new_value['revision'] == 2
        permission = next(r for r in rows if r.action == 'roles.updated')
        assert permission.old_value['permissions'] == ['orders.view']
        assert permission.new_value['permissions'] == ['audit.view', 'orders.view']
    assert secret not in caplog.text


def test_filters_pagination_permissions_and_no_mutations(tmp_path):
    app = setup_app(tmp_path)
    with TestClient(app) as client:
        assert client.get('/api/audit').status_code == 401
        headers = login(client)
        user = client.post('/api/users', headers=headers, json={'username': 'viewer', 'display_name': 'Viewer',
             'password': 'viewer-password-123', 'roles': ['VIEWER']}).json()
        rows = client.get('/api/audit?limit=100').json()
        assert rows['total'] > 1
        first = client.get('/api/audit?limit=1').json()
        second = client.get('/api/audit?limit=1&offset=1').json()
        assert first['total'] == second['total'] and first['items'][0]['id'] != second['items'][0]['id']
        row = next(r for r in rows['items'] if r['action'] == 'users.created' and r['entity_id'] == str(user['id']))
        query = {'user_id': 1, 'action': row['action'], 'entity_type': row['entity_type'], 'entity_id': row['entity_id'],
                 'since': (utc_now() - timedelta(minutes=5)).isoformat(), 'until': (utc_now() + timedelta(minutes=5)).isoformat()}
        result = client.get('/api/audit', params=query).json()
        assert result['total'] == 1 and result['items'][0]['id'] == row['id']
        assert client.get('/api/audit?entity_id=missing').json()['total'] == 0
        for query in ['limit=0', 'limit=101', 'offset=-1', 'since=2026-01-01T00:00:00', 'since=2026-02-01T00:00:00Z&until=2026-01-01T00:00:00Z']:
            assert client.get('/api/audit?' + query).status_code == 422
        for method in ['put', 'patch', 'delete', 'post']:
            for url in ['/api/audit', f"/api/audit/{row['id']}"]:
                assert client.request(method, url, headers=headers, json={}).status_code in (404, 405)
        login(client, 'viewer', 'viewer-password-123')
        assert client.get('/api/audit').status_code == 403
        with Session(app.state.engine) as db:
            viewer_role = db.scalar(select(Role).where(Role.name == 'VIEWER'))
            viewer_role.permissions.append(db.scalar(select(Permission).where(Permission.name == 'audit.view')))
            db.commit()
        assert client.get('/api/audit').status_code == 200


def test_immutable_orm_and_transaction_rollback(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        row = db.scalar(select(AuditLog))
        row.action = 'tampered'
        with pytest.raises(RuntimeError, match='immutable'):
            db.commit()
        db.rollback()
        db.delete(db.scalar(select(AuditLog)))
        with pytest.raises(RuntimeError, match='immutable'):
            db.commit()
        db.rollback()
        for statement in [update(AuditLog).values(action='tampered'), delete(AuditLog)]:
            with pytest.raises(RuntimeError, match='immutable'):
                db.execute(statement)
            db.rollback()
        before = db.query(AuditLog).count()
        role = db.scalar(select(Role).where(Role.name == 'VIEWER'))
        role.name = 'TEMP'
        db.flush()
        db.rollback()
        assert db.query(AuditLog).count() == before


def test_integration_api_changes_are_structured_and_safe(tmp_path, monkeypatch, capsys):
    import httpx
    from cryptography.fernet import Fernet

    from app.ozon import OzonClient

    app = setup_app(tmp_path)
    app.state.settings.ozon_credentials_master_key = Fernet.generate_key().decode()
    def factory(config):
        return OzonClient(config, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'roles': []})))
    monkeypatch.setattr('app.api_ozon_credentials.OzonClient', factory)
    with TestClient(app) as client:
        headers = login(client)
        secret = 'UNIQUE-API-SECRET-FOR-AUDIT'
        assert client.put('/api/ozon/integration/credentials', headers=headers,
            json={'client_id': 'private-client-id', 'api_key': secret, 'expires_at': None}).status_code == 200
        expiry = (utc_now() + timedelta(days=20)).isoformat()
        assert client.put('/api/ozon/integration/expiration', headers=headers, json={'expires_at': expiry}).status_code == 200
        rows = client.get('/api/audit?entity_type=ozon_credentials').json()['items']
        updated = next(r for r in rows if r['action'] == 'ozon_credentials.updated')
        assert updated['old_value']['expires_at'] is None and updated['new_value']['expires_at'] == expiry
        assert updated['user_id'] == 1 and updated['ip'] == 'testclient'
        body = client.get('/api/audit?limit=100').text
        assert secret not in body and 'private-client-id' not in body
    captured = capsys.readouterr()
    assert secret not in captured.err + captured.out
    assert app.state.settings.ozon_credentials_master_key not in captured.err + captured.out


def test_postgresql_audit_migration_sql(monkeypatch):
    from io import StringIO
    from pathlib import Path

    from alembic.config import Config

    from alembic import command
    from app.config import get_settings

    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://offline:offline@localhost/offline')
    get_settings.cache_clear()
    output = StringIO()
    root = Path(__file__).parents[1]
    config = Config(output_buffer=output)
    config.set_main_option('script_location', str(root / 'alembic'))
    try:
        command.upgrade(config, '0021_analytics:0022_audit', sql=True)
        sql = output.getvalue()
        assert 'UPDATE OR DELETE OR TRUNCATE' in sql and 'RAISE EXCEPTION' in sql
        assert 'ADD COLUMN old_value JSON' in sql and 'ix_audit_log_entity_id' in sql
        output.truncate(0)
        output.seek(0)
        command.downgrade(config, '0022_audit:0021_analytics', sql=True)
        assert 'DROP TRIGGER audit_immutable' in output.getvalue()
    finally:
        get_settings.cache_clear()


def test_blockers_procurement_manager_resolution_and_workflow_audit(tmp_path):
    from app.models import BlockerType

    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        db.add(BlockerType(code='OTHER', display_name='Other'))
        db.commit()
    with TestClient(app) as client:
        headers = login(client)
        oid = client.get('/api/orders?status=QUEUED').json()['items'][0]['id']
        blocker = client.post('/api/blockers', headers=headers, json={'order_id': oid, 'type_code': 'OTHER', 'description': 'Sensitive free text stays outside audit'}).json()
        task = client.get('/api/manager-tasks?source_type=BLOCKER').json()['items'][0]
        assert client.patch(f"/api/manager-tasks/{task['id']}", headers=headers, json={'status': 'IN_PROGRESS'}).status_code == 200
        purchase = client.post('/api/procurement', headers=headers, json={'material_name': 'Edge', 'quantity': '2.500', 'unit': 'm', 'order_ids': [oid], 'blocker_ids': [blocker['id']]}).json()
        assert client.patch(f"/api/procurement/{purchase['id']}", headers=headers, json={'status': 'ORDERED'}).status_code == 200
        assert client.patch(f"/api/blockers/{blocker['id']}", headers=headers, json={'status': 'RESOLVED'}).status_code == 200
        assert client.put('/api/orders/statuses/QUEUED', headers=headers, json={'display_name': 'New label', 'sort_order': 42}).status_code == 200
        rows = client.get('/api/audit?limit=100').json()['items']
        assert any(r['action'] == 'blockers.updated' and r['new_value']['status'] == 'RESOLVED' for r in rows)
        assert any(r['action'] == 'manager_tasks.updated' and r['old_value']['status'] == 'IN_PROGRESS' and r['new_value']['status'] == 'RESOLVED' for r in rows)
        assert any(r['action'] == 'procurement_tasks.updated' and r['new_value']['status'] == 'ORDERED' for r in rows)
        assert any(r['action'] == 'procurement_order_links.created' and r['new_value']['order_id'] == oid for r in rows)
        assert any(r['action'] == 'internal_statuses.updated' and r['new_value']['sort_order'] == 42 for r in rows)
        assert 'Sensitive free text' not in json.dumps(rows)
