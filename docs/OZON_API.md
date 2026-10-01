# Seller API boundary — task 020

Official documentation checked on 2026-10-01 in the browser at
[Ozon Seller API](https://docs.ozon.ru/api/seller/). The web reader encountered
a redirect loop, but the browser loaded the official documentation (version 2.1).
No seller account credentials were entered and no live Seller API request was made.

## Verified contract

- Production HTTPS host: `https://api-seller.ozon.ru`.
- Required authentication headers: `Client-Id` and `Api-Key`; JSON requests use
  `Content-Type: application/json`. Credentials remain in backend settings.
- [POST /v1/roles](https://docs.ozon.ru/api/seller/#operation/AccessAPI_RolesByToken)
  reads the roles and methods attached to the key, with no documented request body
  parameters. The client sends an empty JSON object. The response has a `roles`
  array (`name`, `methods`) and `expires_at` string. Unknown fields are ignored;
  malformed roles fail the connection check. Key-expiry automation belongs to task 025.
- [POST /v2/warehouse/list](https://docs.ozon.ru/api/seller/#operation/WarehouseListV2)
  is the current FBS/rFBS warehouse list: required `limit` (maximum 200), optional
  `cursor` and `warehouse_ids`; response `warehouses`, `cursor`, `has_next`.
  This method is documented here but is not implemented or called in task 020.
  `/v1/warehouse/list` is deprecated with a documented shutdown date of 2026-04-07.
  Its old once-per-minute restriction must not be assumed for v2.
- The official Limits section documents HTTP 429, `Ratelimit-Remaining` and
  `Retry-After` in seconds. The general ceiling is 50 requests per second per
  Client ID, with method-specific limits taking precedence.
- Seller API is backend-to-backend; the official documentation says browser calls
  have been prohibited since 2025-05-16. Seller API dates use UTC.

## Implementation and operation

`app.ozon.OzonClientInterface` exposes `check_connection()` and `close()`.
`create_ozon_client(settings)` selects `MockOzonClient` with `OZON_MOCK_MODE=true`
or `OzonClient` otherwise. The application lifespan owns one client on
`app.state.ozon_client`, closes its HTTP pool on shutdown and makes no startup
requests. The existing `seed_mock_orders` fixtures and CLI remain unchanged.
There is no new public API endpoint, frontend integration, scheduler or order importer.

Connection checking explicitly invokes the read-only `/v1/roles` method. A valid
response, including empty roles, confirms connectivity/authentication, not FBS
permission or access to every method. Callers receive typed errors on failure.
The synchronous client is intended for a synchronous FastAPI handler or a worker
thread; an async caller must offload it, for example with `asyncio.to_thread`.

Requests have a 10-second timeout per connect/read/write/pool operation by default,
two retries (three attempts total), and exponential delays of 1 and 2 seconds.
Settings constrain timeout to 60 seconds and retries to five. Backoff is capped
at `OZON_RETRY_MAX_DELAY_SECONDS` (default 30). These are local policy values,
not Ozon API limits. A lock serializes requests on this client's small connection
pool and spaces attempts by at least 25 ms. This pacing is per instance, not a
distributed or account-wide limiter; other applications using the same Client ID
share Ozon's quota.

Only the verified read-only POST is retryable. Timeout, network errors, 5xx and 429
can retry; other 4xx, authentication/permission errors, redirects and malformed
successful responses fail immediately. The final domain error retains the failure
category, status, attempt count and numeric retry delay. There is no arbitrary-URL
request API and redirects are disabled to keep credentials on the official host.
Environment proxy discovery is disabled; TLS verification remains enabled.

For 429, the wait is at least the greater of backoff and a valid numeric
`Retry-After`. Invalid/missing headers fall back to backoff. A delay above the local
cap ends the current operation with `OzonRateLimitError` rather than retrying early.
The cooldown still applies to a subsequent call on that instance. The caller can
schedule a later check using `retry_after`. Provider error bodies and exception
messages are never copied into domain errors or logs.

Structured request logs contain only the fixed endpoint, attempt number, HTTP
status, error category and elapsed milliseconds. Credentials, headers, bodies,
roles and raw network exceptions are excluded. No database mutation occurs, so
this boundary introduces no migration or business audit event.

Tests inject `httpx.MockTransport` and a virtual clock; they make no live Ozon calls.
Real account validation remains a deployment check with configured backend keys.
