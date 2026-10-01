# Architecture Decisions

## 022 — Verified Ozon push contract and durable inbox

Official [push notifications](https://docs.ozon.ru/api/seller/#tag/push_types),
[connection and TYPE_PING](https://docs.ozon.ru/api/seller/#tag/push_start), and
[redelivery](https://docs.ozon.ru/api/seller/#tag/push_resending) were read in the
official browser documentation on 2026-10-01, before implementation. Supported
FBS/rFBS events: `TYPE_NEW_POSTING`, `TYPE_STATE_CHANGED`, `TYPE_POSTING_CANCELLED`,
`TYPE_CUTOFF_DATE_CHANGED`, `TYPE_DELIVERY_DATE_CHANGED`. FBO/order/product/chat
types are outside this FBS task and are recorded as ignored. Ordinary successful
receipt, including duplicates, returns HTTP 200 and `{"result":true}`. TYPE_PING
returns HTTP 200 with `version`, `name`, and processing-start UTC `time`. Errors
use the documented `error.code/message/details` envelope. The documentation
defines no signature/header secret verification; none is invented.

Ozon publishes source networks `195.34.21.0/24`, `185.73.192.0/22`,
`91.223.93.0/24`. Caddy restricts the public receiver to these networks and
overwrites `X-Ozon-Source-IP` from its actual remote socket. The backend accepts
that header only from explicitly configured trusted proxy peers and additionally
checks `seller_id` against the configured Client ID. Direct requests must come
from the Ozon networks. Mock mode accepts only local/test clients; the receiver
is disabled by default. This is IP-based ingress control, not cryptographic
authentication. Do not put an unconfigured CDN/proxy in front of Caddy.

`POST /api/ozon/webhook` commits a bounded, validated private inbox entry before
acknowledging receipt. Unique SHA-256 of canonical JSON provides FBS idempotency
(FBS payloads have no documented event UUID); JSON whitespace/key order does not
affect identity. Duplicate reception does not reset processing/retry state. A
single lifespan worker consumes pending rows, resumes on restart, and atomically
commits the existing posting upsert, notifications/tasks and completion marker.
PostgreSQL row locks/skip-locked and existing source/recipient unique keys guard
replay. No in-memory-only background task, broker or periodic order reconciliation.

The existing OzonClient fetches the current posting with the documented, current
`POST /v3/posting/fbs/get` (the deprecated v3 *list* does not imply deprecated
*get*). Adapt its product `price` string plus `currency_code` to task 021's shared
mapper; retain original source JSON/tariff data. Fetch current data for every
actionable event so delayed pushes do not restore stale statuses/dates, and avoid
guessing the ambiguous push-to-Seller status mapping. Empty date intervals and
cutoff events after Ozon assembly are ignored as documented. Delivery intervals
come from the current get response's analytics data. Internal production fields
remain independent. Full external cancellation after production start uses the
existing `OZON_CANCELLED_AFTER_START` task rule; partial cancellations use current
products/status without incorrectly cancelling the entire production order.

Priority/Tariff/Money at Risk remain read-time projections over existing inputs;
refresh them and the shared deadline Notification Engine on changed data, then
publish SSE only after commit. External cancelled postings leave future shipment
risk/deadline notifications even while their production status awaits a manager.
No unverified conversion of raw Ozon tariff amounts to a signed normalized cost
timeline is added; task 021's conservative unknown-money behavior remains.

Worker failures store only safe error codes, create deduplicated existing manager
tasks/in-app alerts, and retry five times with local backoff; success closes the
error task. This local policy is separate from Ozon's redelivery policy. Exhausted
events stay diagnosable; authenticated `settings.manage` plus CSRF can requeue via
`POST /api/ozon/webhook/events/{id}/retry`. The receiver contains no Seller API
calls and targets the documented 1500 ms availability threshold. See
[operational contract](OZON_API.md#pushwebhook--task-022).

## 021 — Read-only FBS v4 import and production isolation

Official [FBS list](https://docs.ozon.ru/api/seller/#operation/PostingFbsList) checked
in the browser on 2026-10-01: `POST /v4/posting/fbs/list`, cursor pagination, limit
1–100, top-level `postings/has_next/cursor`, product `price.amount/currency`.
V3 is deprecated (official shutdown date 2026-08-31). Confirmed source fields and
operation details are recorded in [OZON_API.md](OZON_API.md#fbs-import--task-021).

Extend task 020's client and shared retry implementation, never create another
Ozon HTTP client. Import is an explicit admin action guarded by `settings.manage`
and CSRF, with no startup calls, webhook or periodic worker. Unique posting-number
insert plus PostgreSQL row locking serializes upserts; all pages form one transaction.
Update only an external field allowlist and items. Internal status, assignments,
blockers, comments, timeline, manager tasks, production timestamps and priority
overrides are untouched, including first sync of an existing production order.
Store one latest canonical raw posting in a separate diagnostic table, with exact
Decimal numeric tokens and no public raw-data endpoint. Mock/real collisions fail.

Keep Ozon tariff objects/steps separately from task 011's signed normalized timeline:
`tariff_deadline_at` is not a verified start time, and a discount amount is not an
explicitly signed cost. No inferred risk amount or tariff conversion is introduced.
`shipment_date` populates the existing deadline as the upstream recommended time;
it is not treated as an automatic cancellation deadline. Money is Decimal/NUMERIC,
UTC timestamps remain separate from local production creation/stage times.

## 020 — Backend Seller API client boundary

Use a lifespan-owned synchronous httpx client behind an `OzonClientInterface` and a settings-selected offline adapter. Preserve `seed_mock_orders`; real order import is task 021. Only the officially verified read-only `POST /v1/roles` is implemented for explicit connection checks, with bounded retries for 429/5xx/timeout/network errors and no retries for other 4xx or invalid responses. Honor numeric Retry-After without shortening it; a delay above the local retry cap returns a typed rate-limit error for later scheduling. Credentials never leave backend settings/HTTPS headers; redirects and environment proxies are disabled. Log only allowlisted request metadata, not provider bodies or raw exceptions. No public route, startup API call or database write is introduced.

Official Ozon documentation was checked in the browser on 2026-10-01: `/v1/roles`, auth headers, host and rate-limit headers confirmed; `/v1/warehouse/list` is deprecated in favor of `/v2/warehouse/list`. See [verified contracts and operational constraints](OZON_API.md) for official links and local retry policy. No FBS endpoint or webhook contract is assumed by task 020.

## 001 — Single VPS bootstrap

Use Docker Compose with one FastAPI worker, a small SQLAlchemy pool, PostgreSQL, and Caddy serving a static PWA. This fits the initial 1 CPU / 1 GB RAM target and avoids a broker or extra worker service. Migrations run explicitly, not concurrently at every API start. The bootstrap has no business tables or real Ozon integration; later tasks add these behind an Ozon client boundary.

## 002 — Server-side sessions and RBAC

Store random session token digests in PostgreSQL and send the token only in a Strict SameSite, HttpOnly cookie (`Secure` in production). Mutations require a per-session CSRF token. Recheck active status and permissions against the database on every request; role changes and deactivation revoke sessions. Use scrypt password hashing from Python's standard library, with a unique salt and fixed memory cost, as the secure Argon2id alternative. The single API worker applies an in-memory login limiter. A migration seeds the initial role and permission matrix; the first super admin is created interactively by CLI.

## 003 — Mock production queue and live refresh

Store logistics status and internal production status separately. Keep internal statuses in a lookup table and record every transition with actor and time. Serialize claim and assignment mutations by locking the order row in PostgreSQL. A guarded, repeatable CLI seed creates clearly marked mock postings. The single API worker broadcasts order changes through in-process SSE; clients reconnect regularly to recheck session and permissions. This uses no broker and requires one API instance.

## 004 — Fixed workflow codes, configurable presentation

System status codes and allowed transitions stay in backend code so display settings cannot change production rules. Administrators may edit only the label and sort order stored in the status table. Orders retain first-entry UTC timestamps for key stages; the append-only history records every transition, including returns to earlier stages, for later cycle-time calculations.

## 006 — Blocker lifecycle and order restoration

Blockers are separate records with fixed lifecycle states. The first blocker stores the order's prior production status and moves it to BLOCKED. Closing the last active blocker restores that status; concurrent changes lock the order row. Each blocker creates one linked manager task, closed automatically with the blocker. The blocker API reserves an empty `photos` collection until validated file storage is implemented.

## 007 — One manager task queue and source keyed rules

Keep the manager task table created in task 006. A stable `(source_type, source_id)` key prevents duplicate tasks; rule callers synchronize active and resolved causes in their own database transaction. Blocker resolution closes its task, while managers cannot mark a blocker task resolved without closing the blocker. Manager task order links are optional for integration-wide causes. Dedicated backend permissions protect the manager queue and updates. Additional sources use this boundary when their underlying data and integrations arrive; no periodic worker is introduced for task 007.

## 008 — Procurement links and overdue escalation

Keep procurement tasks separate from blockers, with many-to-many links to orders and blockers. Delivery does not resolve blockers: staff confirm each underlying problem independently. Record procurement status and assignment changes in an append-only history and order timeline. High and critical overdue purchases use the existing manager-task source key `PROCUREMENT_OVERDUE` with the procurement task ID. The procurement and manager queues evaluate this rule on reads, and writes resolve it when delivery or cancellation removes the cause; no extra worker or manager-task table is needed.

## 009 — Product production profiles

Store one normative profile per `offer_id` and/or SKU, with unique identifiers and `offer_id` taking precedence when matching an order item. Profiles are administered through a dedicated backend permission and audited. Order item identifiers remain nullable so orders without catalog identifiers or a configured profile continue to work; no scheduler or separate MES is introduced. Existing order stage timestamps remain the source for later actual-time comparisons.

## 010 — Calculated production priority

Calculate priority on queue reads in a pure service from one captured UTC time, confirmed order dates and money values, remaining profile norms, blocked state, and manual override. Store only source inputs and override, so the queue updates as deadlines approach without a scheduler or stale score column. Weights and value thresholds live in one audited settings row. An order value influences ordering modestly but is never reported as potential loss; tariff impact is shown only when a confirmed amount exists. The current in-process ranker evaluates filtered orders before pagination to keep global ordering exact; revisit SQL-side ranking if the queue grows beyond the small-VPS working set.

## 011 — Normalized tariff timeline

Store the supplied tariff steps as JSON source data and calculate the current/next step at read time from one UTC instant. A separate parser accepts a normalized mock/integration format; it does not interpret an Ozon response. The future Ozon adapter must verify the official field semantics and provide an explicitly signed total cost per step. Rates and tariff types alone never produce ruble amounts. Compare costs only when both steps have costs in the same currency. `delta_to_next_tariff = next_cost - current_cost`; positive delta is the saving from shipping before the next step, while negative delta is the loss from shipping before a cheaper next step. Expose these magnitudes as `potential_saving` and `potential_loss` respectively. The frontend displays type/rate without money when costs are unavailable; backend `finance.view` controls cost visibility. No background scheduler or cached tariff score is needed.

## 012 — Money at Risk as a read-time tariff projection

Calculate the dashboard from the normalized tariff timeline and existing priority evaluation at one UTC snapshot time. Future risk is only each positive increase above the previous confirmed cost maximum, allocated to the step's single local-time bucket; this prevents counting the same loss twice when a tariff falls and later rises. An unknown or non-RUB future cost stops that order's projection. Already degraded compares current confirmed RUB cost with the confirmed baseline and stays outside the preventable total. Use organization timezone for configurable bucket boundaries; return UTC timestamps and Decimal amounts. Finance-only summary and paginated drill-down recompute from source data without a scheduler, cache, or new table. A drill-down can pass the summary's `as_of` time to keep bucket boundaries aligned. Current order changes may still alter a later drill-down, so the UI offers refresh.

## 013 — Queue search and transactional bulk actions

Keep queue search and filters on the existing orders endpoint, calculate priority via the existing Priority Engine before pagination, and use the existing status transition service for bulk status changes. Bulk mutations validate every selected order before applying any change, enforce existing RBAC permissions, write per-order timeline/history where applicable, and add one audit record per bulk operation. Store nullable Ozon order number and warehouse identifiers for filtering when integration data becomes available; do not infer them from unrelated fields.

## 016 — Shared SSE invalidation and API refresh

Reuse the single-worker in-process order event bus as an invalidation signal for all active operational screens. Publish after commit so another browser reads committed data. The browser owns one EventSource per signed-in session; its automatic reconnect triggers an API refresh, as do focus, online and a 60-second timer. SSE carries no authoritative state or replay log. This fits the single-instance deployment and recovers missed events through normal API reads without Redis or a new table.

## 017 — Transactional notification fan-out

Create recipient notifications in the same transaction as existing blocker, procurement and status actions. A unique `(user_id, dedupe_key)` constraint makes replay safe; the key combines notification type and stable source identity. Store per-channel delivery rows with IN_APP delivered immediately and opted-in WEB_PUSH/TELEGRAM pending future adapters. Manager notification reads reconcile time-based order and tariff deadlines from the existing Priority Engine and Money at Risk data, without another event bus or broker. Mandatory in-app admin alerts override preferences; external channels remain optional.


## 018 — Web Push consumes the existing delivery queue

Keep task 017's Notification, NotificationPreference and NotificationDelivery as the only notification engine and queue. One lifespan-managed background loop in the single API process sends opted-in WEB_PUSH deliveries with pywebpush/VAPID, bounded batches/timeouts and five attempts with backoff. Recheck active users and preferences at send time; new devices do not receive earlier queued events. Subscription endpoints are unique, owned by the authenticated user, validated against supported HTTPS push providers, and never included in audit logs. HTTP 404/410 deletes expired subscriptions. Per-subscription receipts and database row locks prevent normal retry/replay duplicates; stable browser notification tags also coalesce repeated notices. Provider acceptance and the DB commit cannot be atomic, so a crash between them can still cause redelivery.

Extend the existing generated PWA worker with push/click handlers via importScripts; keep API caching NetworkOnly. Existing order/task lists accept exact IDs for authenticated deep links, including after login. A blocker-created notification links to its existing Manager Task. Browser permission is requested only on the explicit enable action; each notification type still needs the user's external-channel preference. Empty VAPID configuration leaves in-app delivery intact. Private key generation writes only an ignored file, and real-device verification remains a deployment check requiring HTTPS and configured keys.

## 019 — Telegram consumes the existing delivery queue

Telegram remains an optional adapter over Notification, NotificationPreference and NotificationDelivery. Users link a private chat with a single-use ten-minute random code delivered through a Telegram deep link; only its SHA-256 digest is stored, and the webhook requires Telegram's configured secret token. A lightweight lifespan loop sends opted-in pending rows with bounded requests and retries. The bot token, webhook secret and public application URL stay in backend settings. Provider acceptance cannot be atomic with the database commit, so a process crash after acceptance can cause a retry.

## 023 — Reconciliation shares import and push effects

One opt-in lifespan loop in the single API process runs immediately and then waits 240 seconds (configurable) after completion. It offloads synchronous HTTP/SQL work to a thread. Reuse task 021's v4 cursor importer/upsert and task 022's posting effects; a shared process lock serializes snapshots and commits across push, reconciliation and explicit import. Do not run multiple API workers/scheduler replicas.

Persist attempt, last full success, safe error category and outage episode separately for mock/real mode. All posting changes and effects commit together; a failed run rolls back them and persists its error in a separate transaction. Emit one existing OZON_SYNC_ERROR notification per recipient/outage episode. Use the separate Manager Task source OZON_RECONCILIATION_ERROR with the mode's state ID to avoid collision with webhook event IDs; resolve on recovery and reopen that same task only for a new outage.

List a rolling 30-day window with overlap, widened after outages up to the verified 365-day API limit. Check known nonterminal postings absent from the list through the existing get adapter in keyset batches. Never infer deletion or cancellation from absence. Local mock production seeds are excluded from get backfill unless they have an API snapshot. Unknown postings older than the configured initial window require the existing explicit historical import; outages beyond a year also require historical backfill. Store confirmed tariff source data without inventing signed normalized costs. Engines continue to calculate projections on reads, and publish SSE after commits, including unchanged success/recovery. Expose sync freshness via authenticated orders.view API and refresh the banner through existing SSE/focus/60-second polling.
