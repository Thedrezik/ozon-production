"""Backend-only Seller API boundary. No order import or automatic API calls."""

import logging
import math
import time
from collections.abc import Callable
from threading import Lock
from typing import Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import Settings

logger = logging.getLogger(__name__)
BASE_URL = "https://api-seller.ozon.ru"
ROLES_PATH = "/v1/roles"


class OzonError(Exception):
    """Safe domain error: never retains provider bodies, headers or exceptions."""

    def __init__(self, *, status_code: int | None = None, attempts: int = 0,
                 retry_after: float | None = None):
        self.status_code = status_code
        self.attempts = attempts
        self.retry_after = retry_after
        super().__init__(type(self).__name__)


class OzonConfigurationError(OzonError):
    pass


class OzonAuthenticationError(OzonError):
    pass


class OzonClientError(OzonError):
    pass


class OzonServerError(OzonError):
    pass


class OzonRateLimitError(OzonError):
    pass


class OzonTimeoutError(OzonError):
    pass


class OzonNetworkError(OzonError):
    pass


class OzonResponseError(OzonError):
    pass


class ApiRole(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    name: str
    methods: list[str]


class ConnectionInfo(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    roles: list[ApiRole]
    # Preserve the upstream timestamp; no inferred expiration or task 025 logic.
    expires_at: str | None = None


@runtime_checkable
class OzonClientInterface(Protocol):
    def check_connection(self) -> ConnectionInfo: ...
    def close(self) -> None: ...


class MockOzonClient:
    """Offline adapter; existing seed_mock_orders remains the fixture source."""

    def check_connection(self) -> ConnectionInfo:
        return ConnectionInfo(roles=[ApiRole(name="Mock", methods=[ROLES_PATH])])

    def close(self) -> None:
        pass


class OzonClient:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        if not settings.ozon_client_id.strip() or not settings.ozon_api_key.strip():
            raise OzonConfigurationError()
        if any(not value.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in value)
               for value in (settings.ozon_client_id, settings.ozon_api_key)):
            raise OzonConfigurationError()
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"Client-Id": settings.ozon_client_id, "Api-Key": settings.ozon_api_key},
            timeout=httpx.Timeout(settings.ozon_timeout_seconds),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            follow_redirects=False, trust_env=False, transport=transport,
        )
        self._retries = settings.ozon_max_retries
        self._backoff = settings.ozon_retry_backoff_seconds
        self._max_delay = settings.ozon_retry_max_delay_seconds
        self._sleep, self._clock = sleep, clock
        self._lock = Lock()
        self._next_request = 0.0
        # Local conservative pacing, not a claim about per-method Ozon limits.
        self._interval = 0.025

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def check_connection(self) -> ConnectionInfo:
        """Read API-key roles. Success does not imply permission to import FBS."""
        # Only this verified read-only POST is retryable. Do not expose arbitrary URLs.
        with self._lock:
            return self._check_connection()

    def _check_connection(self) -> ConnectionInfo:
        for attempt in range(1, self._retries + 2):
            wait = self._next_request - self._clock()
            if wait > 0:
                self._sleep(wait)
            started = self._clock()
            self._next_request = started + self._interval
            error: OzonError | None = None
            status = None
            info = None
            try:
                response = self._http.post(ROLES_PATH, json={})
                status = response.status_code
                if status == 429:
                    delay = self._retry_after(response.headers.get("Retry-After"))
                    error = OzonRateLimitError(status_code=status, attempts=attempt,
                                               retry_after=delay)
                elif status in (401, 403):
                    error = OzonAuthenticationError(status_code=status, attempts=attempt)
                elif 400 <= status < 500:
                    error = OzonClientError(status_code=status, attempts=attempt)
                elif 500 <= status < 600:
                    error = OzonServerError(status_code=status, attempts=attempt)
                elif status != 200:
                    error = OzonResponseError(status_code=status, attempts=attempt)
                else:
                    try:
                        info = ConnectionInfo.model_validate(response.json())
                    except (ValueError, ValidationError):
                        error = OzonResponseError(status_code=status, attempts=attempt)
            except httpx.TimeoutException:
                error = OzonTimeoutError(attempts=attempt)
            except httpx.RequestError:
                error = OzonNetworkError(attempts=attempt)

            logger.info("ozon_request", extra={
                "ozon_endpoint": ROLES_PATH, "ozon_attempt": attempt,
                "ozon_status": status, "ozon_error": type(error).__name__ if error else None,
                "ozon_duration_ms": round((self._clock() - started) * 1000),
            })
            if error is None:
                assert info is not None
                return info
            retryable = isinstance(error, (OzonRateLimitError, OzonServerError,
                                            OzonTimeoutError, OzonNetworkError))
            delay = min(self._max_delay, self._backoff * 2 ** (attempt - 1))
            if error.retry_after is not None:
                delay = max(delay, error.retry_after)
                self._next_request = max(self._next_request, self._clock() + error.retry_after)
            # Never shorten Retry-After. Return control for later scheduling if too long.
            if not retryable or attempt > self._retries or delay > self._max_delay:
                raise error from None
            self._sleep(delay)
        raise AssertionError("Unreachable")

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        try:
            delay = float(value) if value is not None else -1
        except ValueError:
            return None
        return delay if math.isfinite(delay) and delay >= 0 else None


def create_ozon_client(settings: Settings, **kwargs) -> OzonClientInterface:
    if settings.ozon_mock_mode:
        return MockOzonClient()
    return OzonClient(settings, **kwargs)
