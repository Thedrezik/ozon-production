from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.main import create_app


def test_health_reports_mock_mode() -> None:
    app = create_app(Settings(database_url="sqlite:///:memory:", ozon_mock_mode=True))
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mock_mode": True}


def test_readiness_checks_database() -> None:
    app = create_app(Settings(database_url="sqlite:///:memory:"))
    with TestClient(app) as client:
        response = client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_returns_503_when_database_fails(monkeypatch) -> None:
    app = create_app(Settings(database_url="sqlite:///:memory:"))

    def fail(_engine) -> bool:
        raise OperationalError("SELECT 1", {}, Exception("offline"))

    monkeypatch.setattr("app.main.database_is_ready", fail)
    with TestClient(app) as client:
        response = client.get("/api/health/ready")
    assert response.status_code == 503


def test_config_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("OZON_MOCK_MODE", "false")
    monkeypatch.setenv("ORGANIZATION_TIMEZONE", "UTC")
    settings = Settings()
    assert settings.ozon_mock_mode is False
    assert settings.organization_timezone == "UTC"
