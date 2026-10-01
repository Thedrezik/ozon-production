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
Task 021 adds the explicit, authenticated FBS importer described below; no scheduler or webhook is introduced.

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

Only the verified read-only roles and FBS list POST methods are retryable. Timeout, network errors, 5xx and 429
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

## FBS import — task 021

Rechecked the official documentation in the browser on 2026-10-01. The web reader
still encountered a redirect loop; the browser loaded the official operation and
its request/response examples. No account credentials or live API requests were used.

- [POST /v4/posting/fbs/list](https://docs.ozon.ru/api/seller/#operation/PostingFbsList)
  is current. The official v3 section marks `/v3/posting/fbs/list` deprecated with
  shutdown on 2026-08-31. No v3 fallback is implemented.
- Request: `filter.since`, `filter.to`, `limit` 1–100, `cursor`, `sort_dir` ASC/DESC,
  `with.analytics_data`, `with.financial_data`. Date window must not exceed one year;
  the importer conservatively limits it to 365 days and requires aware dates.
- Response is top-level `postings`, `has_next`, `cursor`, without a `result` wrapper.
  Follow returned cursors until `has_next=false`; missing/repeated cursors fail safely.
- Posting: `posting_number`, `order_number`, `order_id`, `status`, `substatus`,
  `in_process_at`, `shipment_date`, `shipment_date_without_delay`, `delivering_date`.
  `shipment_date` is the recommended assembly/shipping time: it populates the existing
  `shipment_deadline` field, and is not an inferred automatic cancellation date.
  Internal `created_at` remains the local creation time; `in_process_at` has its own column.
- Products: `name`, `sku`, `offer_id`, `quantity`, `price.amount`, `price.currency`.
  V4 prices are money objects, unlike v3 price strings. Price uses Decimal/NUMERIC(18,4).
  RUB-only order value is the sum of available unit prices times quantities, rounded
  to cents. Missing price, empty items, mixed/non-RUB currency or an out-of-range total
  leaves order value unknown; it never becomes an inferred loss.
- Warehouse: `delivery_method.warehouse_id`, `delivery_method.warehouse`. Do not mix
  these identifiers with analytics warehouse values or delivery method IDs.
- Available tariff source: `tariffication` includes current/next money objects,
  min charges, types, rates and `next_tariff_starts_at`; `tariffication_steps` includes
  `min_charge`, `tariff_charge` money objects, `tariff_rate`, `tariff_type` and
  `tariff_deadline_at`. Store these separately without claiming that an end deadline
  is a start time or that unsigned discount amounts are signed production costs.
  Mapping into task 011's normalized timeline remains unimplemented; Money at Risk
  must not invent amounts from rates or order prices.

`POST /api/ozon/fbs/import` accepts `{"since":"2026-10-01T00:00:00Z",
"to":"2026-10-04T00:00:00Z"}`. It requires a session, CSRF token and backend
`settings.manage` permission (ADMIN/SUPER_ADMIN). It uses the lifespan-owned
OzonClient, shared HTTP pool/retries and read-only upstream method. Nothing runs
on startup or periodically. Mock mode reads synthetic `app/fixtures/fbs_v4.json`
using the same mapping; it filters the requested window and never calls Ozon.

Migration `0016_ozon_fbs_import` adds nullable external columns, item money and
`ozon_posting_data`. PostgreSQL uses `INSERT ... ON CONFLICT DO NOTHING RETURNING id`
on the existing unique posting number, then a row lock and explicit external-field
updates. SQLite uses the equivalent insert for offline tests. All pages commit in
one transaction, or roll back together. Identical canonical payloads are no-ops;
changed item lists are replaced while the order ID and all production relationships
remain intact. Mock/real posting collisions are rejected. Audit entries contain
only local order IDs; SSE invalidation is published after commit.

`ozon_posting_data.raw_json` retains the latest full posting as canonical JSON,
including unknown fields and exact Decimal number tokens, rather than original
whitespace/key order. Tariff JSON columns use decimal strings where necessary;
raw JSON retains their numeric types. Snapshots are backend diagnostics, absent
from ordinary order responses and logs. They may contain customer data and belong
to the same private database/backup boundary. No unbounded snapshot history is added.
Optional external fields can be absent/null; unknown fields and new statuses/substatuses
are accepted within existing storage limits. Malformed core data aborts the import
with a safe error without returning provider content.
