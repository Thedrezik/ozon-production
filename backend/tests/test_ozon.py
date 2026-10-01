import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.logging import JsonFormatter
from app.ozon import (
    BASE_URL,
    ROLES_PATH,
    MockOzonClient,
    OzonAuthenticationError,
    OzonClient,
    OzonClientError,
    OzonClientInterface,
    OzonConfigurationError,
    OzonNetworkError,
    OzonRateLimitError,
    OzonResponseError,
    OzonServerError,
    OzonTimeoutError,
    create_ozon_client,
)
from tests.test_orders import setup_app

SUCCESS = {"roles": [{"name": "Posting FBS", "methods": ["/v1/posting"]}],
           "expires_at": "2026-12-01T00:00:00Z"}


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.waits = []

    def __call__(self):
        return self.now

    def sleep(self, delay):
        self.waits.append(delay)
        self.now += delay


def client_for(responses, **overrides):
    requests = []
    clock = FakeClock()

    def handler(request):
        requests.append(request)
        result = responses[len(requests) - 1]
        if isinstance(result, Exception):
            raise result
        return result

    settings = Settings(_env_file=None, ozon_mock_mode=False,
                        ozon_client_id="private-client-id", ozon_api_key="private-api-key",
                        **overrides)
    client = OzonClient(settings, transport=httpx.MockTransport(handler),
                        sleep=clock.sleep, clock=clock)
    return client, requests, clock


def test_success_headers_timeout_and_connection_contract():
    client, requests, _ = client_for([httpx.Response(200, json=SUCCESS)])
    with client:
        info = client.check_connection()
        assert isinstance(client, OzonClientInterface)
        assert info.roles[0].methods == ["/v1/posting"]
        assert info.expires_at == SUCCESS["expires_at"]
    request = requests[0]
    assert str(request.url) == BASE_URL + ROLES_PATH
    assert request.method == "POST"
    assert json.loads(request.content) == {}
    assert request.headers["Client-Id"] == "private-client-id"
    assert request.headers["Api-Key"] == "private-api-key"
    assert request.headers["Content-Type"] == "application/json"
    assert request.extensions["timeout"] == dict.fromkeys(["connect", "read", "write", "pool"], 10)
    assert client._http.is_closed


@pytest.mark.parametrize("status,error", [
    (400, OzonClientError), (401, OzonAuthenticationError), (403, OzonAuthenticationError),
    (404, OzonClientError), (409, OzonClientError), (422, OzonClientError),
    (302, OzonResponseError),
])
def test_permanent_errors_do_not_retry(status, error):
    client, requests, clock = client_for([httpx.Response(status, text="private-api-key",
                                                        headers={"Location": "https://evil.example"})])
    with client, pytest.raises(error) as caught:
        client.check_connection()
    assert len(requests) == 1
    assert not clock.waits
    assert caught.value.status_code == status
    assert caught.value.attempts == 1
    assert "private-api-key" not in str(caught.value)


@pytest.mark.parametrize("response,error", [
    (httpx.Response(500), OzonServerError), (httpx.Response(503), OzonServerError),
    (httpx.ReadTimeout("private-api-key"), OzonTimeoutError),
    (httpx.ConnectTimeout("private-api-key"), OzonTimeoutError),
    (httpx.ConnectError("private-api-key"), OzonNetworkError),
    (httpx.RemoteProtocolError("private-api-key"), OzonNetworkError),
    (httpx.Response(429), OzonRateLimitError),
])
def test_retry_exhaustion_preserves_category(response, error):
    client, requests, clock = client_for([response] * 3)
    with client, pytest.raises(error) as caught:
        client.check_connection()
    assert len(requests) == 3
    assert clock.waits == [1, 2]
    assert caught.value.attempts == 3
    assert caught.value.__cause__ is None


def test_retry_recovers_and_backoff_is_capped():
    client, requests, clock = client_for([
        httpx.Response(500), httpx.Response(503), httpx.Response(200, json=SUCCESS),
    ], ozon_retry_backoff_seconds=2, ozon_retry_max_delay_seconds=3)
    with client:
        assert client.check_connection().roles
    assert len(requests) == 3
    assert clock.waits == [2, 3]


def test_retry_can_be_disabled():
    client, requests, clock = client_for([httpx.Response(500)], ozon_max_retries=0)
    with client, pytest.raises(OzonServerError):
        client.check_connection()
    assert len(requests) == 1
    assert not clock.waits


def test_rate_limit_retry_after():
    client, requests, clock = client_for([
        httpx.Response(429, headers={"Retry-After": "7", "Ratelimit-Remaining": "0"}),
        httpx.Response(200, json=SUCCESS),
    ])
    with client:
        client.check_connection()
    assert len(requests) == 2
    assert clock.waits == [7]


def test_long_retry_after_is_not_shortened_and_applies_to_next_call():
    client, requests, clock = client_for([
        httpx.Response(429, headers={"Retry-After": "90"}),
        httpx.Response(200, json=SUCCESS),
    ])
    with client:
        with pytest.raises(OzonRateLimitError) as caught:
            client.check_connection()
        assert caught.value.retry_after == 90
        assert not clock.waits
        client.check_connection()
    assert len(requests) == 2
    assert clock.waits == [90]


@pytest.mark.parametrize("header", ["invalid", "-1", "NaN", "inf", ""])
def test_bad_retry_after_uses_backoff(header):
    client, _, clock = client_for([
        httpx.Response(429, headers={"Retry-After": header}), httpx.Response(200, json=SUCCESS),
    ])
    with client:
        client.check_connection()
    assert clock.waits == [1]


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="not JSON"), httpx.Response(200, json={}),
    httpx.Response(200, json={"roles": "wrong"}),
    httpx.Response(200, json={"roles": [{"name": "test", "methods": [42]}]}),
])
def test_invalid_connection_response(response):
    client, requests, _ = client_for([response])
    with client, pytest.raises(OzonResponseError):
        client.check_connection()
    assert len(requests) == 1


def test_safe_structured_logs_and_errors(caplog):
    caplog.set_level(logging.DEBUG)
    client, _, _ = client_for([
        httpx.ConnectError("private-api-key private-client-id"),
        httpx.Response(403, json={"message": "private-api-key private-client-id"}),
    ])
    with client, pytest.raises(OzonAuthenticationError) as caught:
        client.check_connection()
    records = [r for r in caplog.records if r.name == "app.ozon"]
    assert len(records) == 2
    formatted = "\n".join(JsonFormatter().format(r) for r in caplog.records)
    for secret in ("private-api-key", "private-client-id"):
        assert secret not in formatted + caplog.text + str(caught.value) + repr(client)
    record = json.loads(JsonFormatter().format(records[-1]))
    assert record["ozon_endpoint"] == ROLES_PATH
    assert record["ozon_status"] == 403
    assert record["ozon_error"] == "OzonAuthenticationError"
    assert record["ozon_attempt"] == 2


def test_factory_and_mock_compatibility(tmp_path):
    def forbidden(_request):
        pytest.fail("Mock mode must not use HTTP")

    settings = Settings(_env_file=None, ozon_mock_mode=True)
    mock = create_ozon_client(settings, transport=httpx.MockTransport(forbidden))
    assert isinstance(mock, MockOzonClient)
    assert isinstance(mock, OzonClientInterface)
    assert mock.check_connection().roles[0].name == "Mock"
    mock.close()
    app = setup_app(tmp_path)
    with TestClient(app) as http:
        assert app.state.ozon_client.check_connection().roles[0].name == "Mock"
        assert http.get("/api/health").status_code == 200
        assert http.get("/api/health/ready").status_code == 200
        # Existing seeded mock production queue is untouched.
        from sqlalchemy import func, select
        from sqlalchemy.orm import Session

        from app.models import Order
        from app.orders import seed_mock_orders

        with Session(app.state.engine) as db:
            assert seed_mock_orders(db) == 7
            assert seed_mock_orders(db) == 0
            assert db.scalar(select(func.count()).select_from(Order).where(Order.is_mock)) == 7


def test_real_factory_and_missing_credentials():
    with pytest.raises(OzonConfigurationError):
        create_ozon_client(Settings(_env_file=None, ozon_mock_mode=False,
                                    ozon_client_id="", ozon_api_key=""))
    settings = Settings(_env_file=None, ozon_mock_mode=False,
                        ozon_client_id="test", ozon_api_key="secret")
    client = create_ozon_client(settings, transport=httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"roles": []})))
    assert isinstance(client, OzonClientInterface)
    try:
        assert client.check_connection().roles == []
    finally:
        client.close()


@pytest.mark.parametrize("field,value", [
    ("ozon_max_retries", -1), ("ozon_max_retries", 6), ("ozon_timeout_seconds", 0),
    ("ozon_timeout_seconds", float("inf")), ("ozon_retry_backoff_seconds", 0),
    ("ozon_retry_max_delay_seconds", 121),
])
def test_bounded_settings(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


@pytest.mark.parametrize("key", ["", "   ", "secret\r\nInjected: header", "ключ"])
def test_invalid_credentials_are_safe_domain_errors(key):
    with pytest.raises(OzonConfigurationError) as caught:
        OzonClient(Settings(_env_file=None, ozon_client_id="test", ozon_api_key=key))
    assert str(caught.value) == "OzonConfigurationError"


def test_lifespan_real_client_is_lazy_and_closes(tmp_path, monkeypatch):
    client, requests, _ = client_for([httpx.Response(200, json=SUCCESS)])
    app = setup_app(tmp_path)
    monkeypatch.setattr("app.ozon_credentials.create_ozon_client", lambda _settings: client)
    with TestClient(app):
        assert app.state.ozon_client.client is None
        assert not requests
        app.state.ozon_client.check_connection()
    assert len(requests) == 1
    assert client._http.is_closed
