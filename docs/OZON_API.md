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

## Push/webhook — task 022

Verified directly in the rendered official Seller API documentation on 2026-10-01:
[connection](https://docs.ozon.ru/api/seller/#tag/push_start),
[types and responses](https://docs.ozon.ru/api/seller/#tag/push_types),
[redelivery](https://docs.ozon.ru/api/seller/#tag/push_resending).
No account credentials or production API requests were used.

Confirmed payload contracts (top-level JSON objects, without an invented wrapper):

| Type | Data used/validated |
| --- | --- |
| `TYPE_PING` | `message_type`, UTC `time`; initial connection and periodic checks |
| `TYPE_NEW_POSTING` | `posting_number`, `products` (`sku`, `offer_id`, `quantity`), `in_process_at`, `shipment_date`, `warehouse_id`, `seller_id`; Ozon also documents delivery/tracking/integration fields |
| `TYPE_STATE_CHANGED` | `posting_number`, `new_state`, UTC `changed_state_date`, `warehouse_id`, `seller_id` |
| `TYPE_POSTING_CANCELLED` | Same status fields, `old_state`, `products` (`sku`, `quantity`), `reason.id/message` |
| `TYPE_CUTOFF_DATE_CHANGED` | `posting_number`, `new_cutoff_date`, `old_cutoff_date`, `warehouse_id`, `seller_id` |
| `TYPE_DELIVERY_DATE_CHANGED` | `posting_number`, `new_delivery_date_begin/end`, `old_delivery_date_begin/end`, `warehouse_id`, `seller_id` |

These five posting events concern FBS/rFBS. FBO, order-level and other types are
stored as `IGNORED`, with a success acknowledgement and no production mutation.
Unknown types are handled the same way. Unsupported types should not be subscribed.
No signature verification or shared-secret header is specified by these sections.
Source networks: `195.34.21.0/24`, `185.73.192.0/22`, `91.223.93.0/24`.

Successful ordinary receipt: HTTP 200, application/json, `{"result":true}`.
TYPE_PING: HTTP 200, `{"version":"1.0","name":"Ozon Production","time":"<UTC>"}`;
time is when processing starts, rather than an echo of the request. Errors: 4xx/5xx
with `{"error":{"code":"ERROR_UNKNOWN","message":"...","details":null}}`;
invalid/missing values use documented `ERROR_PARAMETER_VALUE_MISSED`.
`ERROR_REQUEST_DUPLICATED` is documented, but already received events here are
acknowledged with success because the durable receipt already exists.

Ozon retries failed deliveries after a few seconds with increasing intervals;
after reaching ten minutes it makes five further attempts at ten-minute intervals.
The page also lists suspension for unavailability, errors for 24 hours, fewer than
half HTTP 200 responses, or processing over five seconds. Its current availability
monitor considers under 1500 ms available, 1500–2500 ms unstable, and from 2500 ms
unavailable; three consecutive unavailable days cause automatic disconnection.
The receiver acknowledges after DB commit without waiting for Ozon HTTP enrichment.

Cutoff-change events are documented as test-mode: verify via get; an empty new
date means wait for a new interval, and events after assembly must be ignored.
Delivery-change fields may likewise be empty. Late payment may leave
`in_process_at` empty. Push status `posting_created` maps to several API statuses,
so do not invent a one-to-one mapping.

Current enrichment: `POST /v3/posting/fbs/get`, request `posting_number` and
`with.analytics_data=true`, `with.financial_data=true`; response `result` is a
single posting. The current get section has no deprecation notice. Product prices
are strings plus `currency_code`, unlike v4 list money objects. Normalize only
this verified difference for the existing upsert; raw get JSON stays original.
Delivery interval uses `analytics_data.delivery_date_begin/end`, not
`delivering_date` (which is the handover-to-delivery timestamp). The shared client
retains bounded HTTP retries and no credential/body logging.

Local operation:

- Apply `0017_ozon_webhook` with `alembic upgrade head` before enabling the receiver.
- Set `OZON_WEBHOOK_ENABLED=true`; real mode also needs existing Seller API credentials.
- Behind Compose Caddy, set `OZON_WEBHOOK_TRUSTED_PROXIES` to its actual peer IP/CIDR,
  preferably its exact `/32`, and update that setting if Docker changes the peer.
  Only Caddy is publicly exposed; it overwrites the source header and filters IPs.
  Untrusted forwarded headers cannot grant ingress. A CDN needs a separately
  reviewed trusted-proxy configuration; the current config fails closed.
- Register `https://<domain>/api/ozon/webhook` in Ozon Settings → Push notifications,
  run Ozon's connection check, then subscribe to the five supported posting types.
- In mock mode the backend accepts local requests only. Caddy's public Ozon IP
  filter remains active. `MockOzonClient.get_fbs` uses the synthetic task 021 fixture.
- Inbox stores canonical payload, receipt/processing times, mode, status, attempts,
  next retry time and safe error code. Malformed bounded bodies are private rejected
  diagnostics; denied/oversized requests are not retained. No public payload endpoint.
- Unique canonical-payload hash prevents duplicate processing. Semantic redeliveries
  with different content still fetch latest state; shared snapshot/upsert, notification
  keys and manager-task source keys prevent repeated domain side effects.
- Local retries: five total attempts, delays 10/20/40/80 seconds between failures.
  `FAILED` rows stay stored; admin/CSRF replay is
  `POST /api/ozon/webhook/events/{id}/retry`. Successful recovery resolves its error task.
- One API worker owns the DB-inbox loop. It resumes pending/retry rows on restart;
  it never periodically lists orders. Reconciliation remains task 023.
- Priority, tariff projections and Money at Risk use existing engines. Raw source
  tariffs are refreshed but their unverified signed-cost mapping remains unknown;
  no ruble risk is inferred from product prices or unsigned discounts.

Automated coverage uses synthetic payloads, fixtures and mock HTTP only. Real Ozon
handshake/delivery, Caddy runtime and PostgreSQL checks remain deployment checks
when Docker is unavailable locally.

## Reconciliation — task 023

After `alembic upgrade head` (migration `0018_ozon_reconciliation`), set
`OZON_RECONCILIATION_ENABLED=true` and restart the backend. Earlier descriptions
of no startup/periodic requests apply with this setting disabled, its default.
The lifespan owns one sequential loop: run immediately, then wait
`OZON_RECONCILIATION_INTERVAL_SECONDS=240` after completion. Deploy one API worker.
No Redis, broker or new import mechanism is introduced.

`OZON_RECONCILIATION_LOOKBACK_DAYS=30` controls discovery, with a one-day overlap
on recovery and an end date one day ahead. A long outage widens the window, capped
at 365 days. Use the existing explicit importer for initial older history or
outages exceeding that limit. Known nonterminal postings absent from the v4 list
are refreshed through existing v3 get, never deleted or cancelled merely because
they are absent. Terminal `cancelled`/`delivered` postings stop get backfill.
Local mock seed scenarios without Ozon snapshots stay independent of API fixtures.

The shared upsert only changes external fields and item data; production status,
assignment, blockers, comments, Manager Tasks and manual priority remain local.
Posting notifications/cancellation tasks use the same keys as webhook processing.
Updates include status/substatus, shipment dates, delivery intervals and confirmed
raw tariff data. The conservative normalized tariff mapping limitation from task
021 still applies; Priority/Tariff/Money at Risk use their existing read-time logic.

`GET /api/ozon/sync-state` requires `orders.view`, returns `last_attempt_at`,
`last_successful_sync`, status, safe error code, age in seconds and staleness.
`OZON_STALE_AFTER_SECONDS=600` controls the threshold; no full successful run means
unknown age and stale data. Mock and real freshness are isolated. Failed pages
roll back domain writes, preserve the previous success and persist the error.
One `OZON_SYNC_ERROR` notification is emitted per recipient/outage, with no retry
spam. A source-keyed Manager Task closes on success and reopens on a later outage.
The signed-in UI shows freshness and errors via existing SSE and periodic refresh.

The task adds no new upstream contract. It reuses the official contracts verified
for tasks 021/022 on 2026-10-01 above. This session's web reader encountered the
same redirect loop and browser access timed out; no new API fields were inferred.
All automated verification uses fixtures/mock HTTP, never a production account.


## Credential management — task 025

The existing verified `/v1/roles` check is reused without a new Seller API method.
The official web reader still returned a redirect loop on 2026-10-01; this task
uses the existing verified client contract above. Runtime credentials now resolve
from the encrypted authoritative singleton, with environment bootstrap only.
Configure a Fernet `OZON_CREDENTIALS_MASTER_KEY` in backend environment before
rotation; retain it securely outside database backups. `OZON_KEY_ALERT_DAYS`
defaults to `14,7,3,1`. Saved credentials are never returned by integration APIs.
See decision 025 for lifecycle, Mock Mode, alert and master-key recovery rules.
