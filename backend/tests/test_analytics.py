from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_orders import login, setup_app

from app.models import (
    Assignment,
    Blocker,
    Order,
    OrderItem,
    Permission,
    Role,
    StatusHistory,
    User,
)
from app.orders import seed_mock_orders


@pytest.fixture
def fixture(tmp_path):
    app = setup_app(tmp_path)
    t = datetime(2026, 1, 2, 0, tzinfo=timezone.utc)
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        for order in db.scalars(select(Order)):
            order.created_at = t - timedelta(days=20)
            order.shipment_deadline = t - timedelta(days=20)
        order = db.scalars(select(Order).order_by(Order.id)).first()
        order.created_at = t - timedelta(hours=1)
        order.production_started_at = t
        order.production_completed_at = t + timedelta(hours=2)
        order.ready_to_ship_at = t + timedelta(hours=3)
        order.shipment_deadline = t + timedelta(hours=1)
        admin = db.scalar(select(User).where(User.username == 'admin'))
        for status in ('PRODUCED', 'READY_TO_SHIP', 'PRODUCED'):
            db.add(StatusHistory(order_id=order.id, new_status=status, changed_by=admin.id,
                                 changed_at=t + timedelta(hours=2)))
        db.add(Assignment(order_id=order.id, user_id=admin.id))
        db.add_all([OrderItem(order_id=order.id, sku='SKU-A', offer_id='A', product_name='A', quantity=2),
                    OrderItem(order_id=order.id, sku='SKU-A', offer_id='A', product_name='A', quantity=1)])
        from app.models import BlockerType
        db.add(BlockerType(code='TEST', display_name='Test reason'))
        db.flush()
        code = 'TEST'
        for status in ('OPEN', 'RESOLVED'):
            db.add(Blocker(order_id=order.id, type_code=code, description='test', severity='LOW',
                           status=status, created_at=t))
        db.commit()
    return app


def test_metrics(fixture):
    with TestClient(fixture) as client:
        login(client)
        data = client.get('/api/analytics?start=2026-01-02&end=2026-01-02').json()
        for name, expected in [('new_to_production', 60), ('production', 120),
                               ('produced_to_ready', 60), ('cycle', 240)]:
            assert data['intervals'][name] == {'count': 1, 'average_minutes': expected}
        assert data['throughput'] == {'received': 1, 'started': 1, 'produced': 1, 'ready': 1, 'overdue': 1}
        assert data['blockers'][0]['count'] == 2
        assert data['blockers'][0]['currently_open'] == 1
        sku = next(row for row in data['sku']['items'] if row['sku'] == 'SKU-A')
        assert sku['orders'] == 1
        assert sku['average_minutes'] == pytest.approx(120, abs=0.001)
        assert data['employees']['items'][0]['processed_orders'] == 1
        assert data['current_workload']['items'][0]['active_orders'] == 1
        assert data['prevented_financial_risk']['amount'] is None
        assert client.get('/api/analytics?start=2026-01-02&end=2026-01-02&page_size=1').json()['sku']['total'] >= 2


def test_boundaries_and_empty(fixture):
    with Session(fixture.state.engine) as db:
        order = db.scalars(select(Order).order_by(Order.id)).first()
        # Moscow Jan 2 starts at Jan 1 21:00 UTC, and ends Jan 2 21:00 UTC exclusive.
        order.production_started_at = datetime(2026, 1, 1, 21, tzinfo=timezone.utc)
        order.created_at = order.production_started_at - timedelta(minutes=30)
        order.production_completed_at = datetime(2026, 1, 2, 21, tzinfo=timezone.utc)
        db.commit()
    with TestClient(fixture) as client:
        login(client)
        data = client.get('/api/analytics?start=2026-01-02&end=2026-01-02').json()
        assert data['intervals']['new_to_production']['count'] == 1
        assert data['intervals']['production']['count'] == 0
        assert client.get('/api/analytics?start=2026-01-03&end=2026-01-03').json()['intervals']['production']['count'] == 1
        empty = client.get('/api/analytics?start=2025-01-01&end=2025-01-01').json()
        assert all(value == {'count': 0, 'average_minutes': None} for value in empty['intervals'].values())
        assert empty['sku']['items'] == empty['employees']['items'] == empty['blockers'] == []
        assert all(value == 0 for value in empty['throughput'].values())
        for query in ('start=2026-01-03&end=2026-01-02', 'start=2020-01-01&end=2026-01-02',
                      'start=2026-01-02&end=2026-01-02&page=0'):
            assert client.get('/api/analytics?' + query).status_code == 422


def test_permissions(fixture):
    with TestClient(fixture) as client:
        assert client.get('/api/analytics?start=2026-01-02&end=2026-01-02').status_code == 401
        headers = login(client)
        client.post('/api/users', headers=headers, json={'username': 'viewer', 'display_name': 'Viewer',
                    'password': 'viewer-password-123', 'roles': ['VIEWER']})
    with TestClient(fixture) as client:
        login(client, 'viewer', 'viewer-password-123')
        assert client.get('/api/analytics?start=2026-01-02&end=2026-01-02').status_code == 403
    with Session(fixture.state.engine) as db:
        role = db.scalar(select(Role).where(Role.name == 'VIEWER'))
        role.permissions.append(db.scalar(select(Permission).where(Permission.name == 'analytics.view')))
        db.commit()
    with TestClient(fixture) as client:
        login(client, 'viewer', 'viewer-password-123')
        data = client.get('/api/analytics?start=2026-01-02&end=2026-01-02').json()
        assert 'prevented_financial_risk' not in data
        assert 'money_at_risk' not in data



def test_invalid_intervals_and_profile(fixture):
    from app.models import ProductProductionProfile
    with Session(fixture.state.engine) as db:
        order = db.scalars(select(Order).order_by(Order.id)).first()
        order.production_started_at = order.production_completed_at + timedelta(minutes=5)
        db.add(ProductProductionProfile(sku='SKU-A', offer_id='A', product_name='A',
               production_minutes=45, packing_minutes=10, complexity='LOW'))
        db.commit()
    with TestClient(fixture) as client:
        login(client)
        data = client.get('/api/analytics?start=2026-01-02&end=2026-01-02').json()
        assert data['intervals']['production'] == {'count': 0, 'average_minutes': None}
        assert data['sku']['items'] == []
    with Session(fixture.state.engine) as db:
        order = db.scalars(select(Order).order_by(Order.id)).first()
        order.production_started_at = order.production_completed_at - timedelta(minutes=90)
        db.commit()
    with TestClient(fixture) as client:
        login(client)
        data = client.get('/api/analytics?start=2026-01-02&end=2026-01-02').json()
        row = next(row for row in data['sku']['items'] if row['sku'] == 'SKU-A')
        assert row['normative_minutes_per_unit'] == 45
        assert row['average_minutes'] == pytest.approx(90, abs=.001)
