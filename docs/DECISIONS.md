# Architecture Decisions

## 036 — Small workshop core with preserved extensions

Supersede default UI/notification/processing choices from 006/016–019/023–026/028;
preserve historical decisions and source implementations. Core statuses keep
existing storage codes; atomic claim starts production, shipment comes only from
verified Ozon logistics. Simple blockers retain stage/provenance; no Manager Tasks
in core. Cancellation before start stays in chronological Feed; after start stays
critical until admin disposition, with deduplicated Telegram.

Validated ENABLED_OPTIONAL_FEATURES defaults empty. Gate routers, source task
creation, optional read-time evaluations and Push/key-expiry lifespan loops; lazy
frontend chunks are excluded from core precache. Telegram becomes core with three
events to linked admins, without per-type preferences. No autonomous deadline
alert promise. One SSE and one 60 s fallback; authenticated 20 s stream reconnect
does not independently refresh pages. Reconciliation startup + 900 s; inbox 5 s idle.
SSE epoch/revision checkpoint recovers changes in reconnect gaps/backend restart;
unchanged reconnect does not reload pages. Bounded queue/coalescing and 20 s auth
deadline remain; no replay store or broker is introduced.

Real tariff adapter verified in rendered official Seller v4 docs 2026-10-02:
supplied charge, discount/commission sign, stage end boundaries and explicit next start. No price/rate/
minimum-derived amount. Consistent timeline or explicit current/next pair; unknown
inputs stay unpriced. Backfill missing projection on identical snapshot ingestion.
Verified v3 get: string current/next charge + *_currency_code, versus v4 Money
objects. Accept explicitly priced no_discount zero, not empty charge; use compatible
confirmed steps and prefer explicit next start without breaking chronology.
0024 adds resolution provenance/worker permission/chronological index, no enum
deletion. Release credential-client SELECT connection before external HTTP.

CORE_WORKFLOW.md/OPTIONAL_FEATURES.md document exact new product and extension
dependencies. Preserve old PRODUCT/bootstrap as explicitly archived appendices.
Task 034 pending; no commit/push/production deployment in 036.

## 035 — Pre-deployment review before deferred VPS acceptance

At the user's explicit instruction, complete task 035 as a local PRODUCT/code
review before renting the Linux VPS. Task 034 stays pending; production launch,
PostgreSQL/Caddy/security/capacity/restore/provider/physical-device gates remain
mandatory later. Review completion does not assert full PRODUCT compliance.
Record findings and optional simplification tradeoffs in FINAL_REVIEW.md; leave
feature selection to the user. No new job/service/schema or task 036 is added.

Clarify decision 006 for externally cancelled postings: closing an existing
blocker resolves its source task but must not resume production. Preserve local
BLOCKED until explicit manager disposition, while rejecting new blockers on an
externally cancelled posting. Missing normalized tariffs mean unknown exposure,
not confirmed zero; show this in risk/dashboard without inventing a mapping.

## 034 — Explicit production release and isolated Linux launch gates

Use a standalone production Compose file, fixed project name, private generated
env and immutable paired application image tags. Keep the small-VPS limits and
one worker. Separate private database/proxy networks with operator-reviewed subnets;
fix the Caddy peer address and trust only its exact /32. Dedicated VPS minimum is
1 CPU / 1 GB RAM. Preserve all functions, one worker and pool 2+1; no lightweight
mode/refactor in this task. RAM caps remain 256/384/96 MiB (736 MiB combined), with
explicit RAM+swap ceilings 320/512/128 MiB. Recommend 1 GiB host swap as a bounded
emergency buffer, not added usable RAM. Build images/run browsers off the target;
the native target restore drill can reuse a preloaded immutable backend image.
Do not change firewall automatically; publish only TCP 80/443. Do not add a
CDN/forwarded-IP trust mechanism.
Build away from the small live VPS when possible. Secrets never enter build args
or frontend/Caddy env; extend Docker ignore rules to cover private files/artifacts.

Release operations pause writers before DB/uploads backup, then update/build,
validate settings, migrate, validate Caddy, start, readiness and HTTPS smoke.
Migration failures leave the API stopped. Keep previous ref/env/backup privately;
rollback restores matching code/data rather than automatically downgrading schemas.
pg_restore clean cannot universally remove new-schema objects: failed schema
rollback remains an explicit operator recovery into a separate DB.

The native Linux drill generates synthetic env, resolves/checks all five unique
volumes and mounts before restore/cleanup, verifies changed DB rows/uploads,
real restore, newest retention and preservation of every pre-existing volume.
Existing E2E scenarios gain opt-in isolated PostgreSQL/Caddy local-CA HTTPS mode,
with test-only transport faults/provider fixtures and PostgreSQL/CPU/RSS reports.
Test-mode certificates/source relaxation do not prove production auth/ACME;
retain exact public/production/device/provider gates in DEPLOYMENT.md. Docker/VPS
are unavailable here; task 034 stays pending until the target Linux restore and
all runtime acceptance criteria actually pass. No new production service/broker.

## 033 — Real application E2E with the existing Playwright browser stack

Use Playwright/Chromium (installed Edge on Windows) and a single `npm run test:e2e`
command that builds the production PWA. Six scenarios run sequentially at desktop
and mobile viewports with independent admin/worker/manager contexts. Each scenario
gets a fresh temporary SQLite database/uploads directory, all Alembic migrations,
the existing mock order seed, and the ordinary FastAPI/Uvicorn app. No replacement
backend, test API endpoints, production credentials or deployment reset. Only the
external Ozon adapter uses existing synthetic fixtures with local changes; import,
durable webhook and reconciliation use existing domain code. A static/API streaming
proxy injects transport outage/SSE loss and a competing-write barrier for deterministic
409 coverage. Real SSE delivery and focus fallback are checked separately.

No automatic retries. State-based waits include the existing 30-second offline
recovery budget. Keep screenshots/DOM/traces/logs only for failures in ignored
artifacts; shut down contexts/backend before deleting only the generated directory.
SQLite reloads strip tzinfo: serialize order timestamps explicitly as UTC so a UI
procurement deadline round trip remains valid. A regression test covers that bug.
Docker is unavailable locally; PostgreSQL/Caddy/HTTPS, physical devices/provider
delivery and the mandatory Linux restore drill remain task 034 deployment gates.
See [E2E coverage and runbook](E2E.md).

## 032 — Measured bounds for the single small VPS

Keep one backend worker, the 2+1 DB pool and existing sequential Ozon scheduler/
posting lock. No broker/cache or persisted priority scores. Confirmed dashboard
N+1 (4,039 queries for 2,007 synthetic orders) is fixed by committing before
projection reads, SQL status/workload groups and a shared streamed priority/risk
pass. Keyset batches of 250 with batch-specific profiles bound ORM memory; exact
queue ranking retains only top offset+limit identities and reloads the page.
Summaries retain no risk identities; drill-down remains exact with bounded rows.
Default queue excludes terminal production history; explicit filters/IDs retain
archive access. Timeline pagination happens in SQL before loading display rows.
Overdue procurement sources and their Manager Tasks are prefetched per batch;
repeat manager-page reads preserve deduplication without a per-source SELECT.

Set Compose caps PostgreSQL/backend/Caddy 256/384/96 MiB and PostgreSQL 20
connections, 64MB shared buffers, 2MB work memory, no parallel query workers.
Bound pool wait to 3 seconds, SSE to 100 subscribers/two emissions per second,
and release its DB connection before streaming. Keep uploads serialized; resize
before conversion and JPEG draft decoding. Measured WebP decoder memory requires
a 10 MP WebP cap checked before decoder construction; JPEG/PNG retain 20 MP.
Add six list/history/delivery indexes in migration `0023_performance`.

Application benchmarks are SQLite/Windows comparisons, not VPS guarantees.
Python request memory remains about 3–4 MiB at 10,007 orders; exact complex
priority/tariff evaluation still scales linearly with active orders. Frontend
build uses about 428 MiB; prefer image builds off the running VPS. Container RSS,
PostgreSQL plans, real concurrency/phone images and target startup remain deployment
checks because Docker is unavailable here. See [measurements and runbook](PERFORMANCE.md).

## 031 — Harden the existing session and single-proxy deployment

Keep server-side opaque sessions, per-session CSRF, backend RBAC, encrypted Ozon
credentials, existing file validator and notification queue. No JWT, parallel
auth/limiter, infrastructure or new schema. Production settings fail closed:
real HTTPS origin matching Caddy DOMAIN, explicit Compose APP_ENV,
non-default PostgreSQL credentials, random deployment secret,
valid Fernet master key, mock mode forbidden and complete optional integrations.
Disable production docs and validate Host. Uvicorn ignores forwarded headers;
trust Ozon source headers only from exact configured Caddy addresses. Socket-peer
login budget is aggregate behind Caddy (60/15 minutes); account/peer budget is
5/15 minutes. Atomic limiter reservations and one hash slot bound brute force and
memory. New scrypt uses OWASP's 32 MiB N=32768/r=8/p=3; legacy p=1 hashes upgrade
on login. SSE must reconnect within 20 seconds even under continuous events.
User management locks its target before reading roles; super-admin removal locks
the existing SUPER_ADMIN role before counting survivors, closing promotion/removal
races without a new mechanism. PostgreSQL supplies the production row locks.

Apply same-origin browser mutation policy, generic validation/error responses,
bounded JSON bodies and API security headers; Caddy protects the static PWA with
self-only scripts/workers, no framing/objects, no-referrer and HTTPS-only HSTS.
Inline styles remain allowed for existing UI, inline scripts do not. Disable
transport/access logs that can carry capability URLs; redact secrets in structured
logs/audit text without retaining raw exception bodies. Keep deployment checks
explicit in SECURITY.md, including actual Caddy/PostgreSQL execution, real provider
delivery and the task 034 Linux restore gate. No deployment is implied by local tests.

## 028 — Production analytics from operational tables

Read-only SQL aggregates use existing first-stage timestamps; NEW starts at local
order creation and cycle ends at first READY_TO_SHIP (not Ozon delivery/DONE).
Each interval belongs to the local date of its end; include both dates using UTC
half-open bounds in organization timezone, maximum 366 days. Missing/reversed
intervals are excluded, waiting/blocker time remains included. No event store,
background aggregation, financial snapshot or new database. Existing priority and
Money at Risk projections remain operational, not evidence of prevented loss.

Throughput counts first received/started/produced/ready timestamps in the period.
Overdue uses shipment-deadline cohort: deadline before min(now, period end), no
readiness or readiness after deadline, excluding internal/external cancellations.
Historical deadline/cancellation values are not reconstructed from current data.
Blockers group by creation date and reason; open count reflects current state.
Current assignment workload is explicitly a live snapshot, not historical load.

Employee throughput counts distinct orders per actual status-history actor for
PRODUCED/READY_TO_SHIP in the period; repeated transitions count once per employee.
No retroactive attribution to current assignees and no invented actor for legacy
rows. Analytics permission grants these operational names/counts only, no account
or audit data. SKU/offer pairs count each posting once: elapsed production of the
whole posting, not per-item labor. Existing offer-first/SKU-fallback profile shows
unit normative separately; no substitution for missing actual durations.

Require analytics.view server-side; finance.view additionally exposes only an
unavailable explanation (amount null) for prevented financial risk. Confirmed
counterfactual loss/avoidance methodology is unavailable, so never sum projected
Money at Risk as savings. Reads do not mutate audit/workflow. Grouped SKU, employee
and live workload results are paginated (20, max 100); date cohort indexes in
0021_analytics support bounded queries on the single PostgreSQL instance.


## 027 — Short-lived read-only offline queue

Keep the existing generated Workbox worker: precache the static application shell
and use NetworkOnly for `/api/*`. A worker cache never supplies operational API
data. After a successful authorized queue + blockers read, retain only one display
snapshot of the loaded queue page (including pagination scope and UTC receipt time).
Project posting/product/quantity, separate production/Ozon statuses, shipment
deadline and priority level/label; omit money, priority financial reasons, staff
identity, comments, photos, credentials, CSRF tokens and full API responses.

Use sessionStorage scoped to the current tab, with an in-memory fallback if storage
is disabled. A snapshot expires after one hour, is removed on logout, explicit
offline deletion, authorization rejection or a different authenticated user, and
is never an authenticated session. Offline reload can display this previously
authorized local projection without restoring a User or permissions. Like any
local offline display, server revocation cannot erase a disconnected device until
reconnect; limit exposure through this projection, expiry and tab lifetime.
Closing the tab ends storage; reopening the installed PWA in a new tab still loads
the shell but needs the network for its first queue. No offline login is added.

Show OFFLINE for browser disconnection or failed/timed-out queue requests, including
backend outages while navigator.onLine is true. Show receipt time and explicitly
freeze priority/deadline interpretation at that time. Offline mode exposes only
this page without mutations, filters, detail requests or other operational screens.
Reconnect/30-second recovery polling first validates the server session, then
reopens the queue and requests fresh backend data. Keep a stale warning and disable
queue controls until a full successful read; reconnect itself never makes a snapshot
fresh. Existing SSE open/events, focus and periodic reconciliation continue to
invalidate data online. Ignore superseded/unmounted queue reads.

Do not implement an offline mutation queue for short outages. Reliable deferred
status/assignment changes require server idempotency receipts plus expected-version
checks across status, assignment, blockers and RBAC, beyond current contracts. The
read-only choice avoids ambiguous retries and silent overwrites without introducing
a second workflow. No mutation is replayed automatically; live status/claim/assignment
409 responses show an explicit conflict message and refresh from the server.
An interrupted live mutation may already have committed: inspect refreshed server
state before retrying. Backend transitions, locking, permissions, sessions and CSRF
remain authoritative and unchanged.

Validation: `npm run build`, `npm run test:offline`, existing push-worker checks and
`npm run test:offline:browser`. The browser test needs Playwright with Edge installed;
`PLAYWRIGHT_MODULE` can point to the bundled Playwright `index.mjs`. It serves the
actual production build and generated worker with synthetic local API responses;
checks offline reload, stale/time display, reconnect, no deferred writes, 409,
backend outage, auth revocation, offline deletion and absence of cached API data.

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

## 024 — External cancellation preserves production state

All three ingestion paths (explicit import, push and reconciliation) use the existing
`apply_posting` effects and external-only upsert in their transaction. Keep Ozon
cancellation separate from internal production status: before production the posting
is operationally closed (excluded from the normal queue, P4, no future risk/deadline
alerts), while its local status and relationships remain intact. Explicit cancelled
filters and exact order lookup expose the archive. Claim/production advancement is
rejected; managers can explicitly cancel the internal workflow.

Cancellation after a production timestamp or a started/completed stage creates the
existing source-keyed critical Manager Task and alerts the assigned worker and
managers through the existing Notification Engine. Replays retain staff decisions
and do not duplicate tasks/notices. Never close blockers or remove comments,
assignments, status history, timestamps, overrides or historical Manager Tasks.

Changed external status/substatus and shipment/no-delay/delivery dates append safe
old/new values to audit and readable timeline entries. Identical snapshots and
nonoperational changes do not append duplicate timeline events. Projections remain
read-time calculations, so deadline changes immediately affect priority and the
risk classification of confirmed normalized tariff costs. No tariff dates/costs are
inferred from shipment changes or raw unsigned Ozon discounts. Reconcile existing
deadline notices: retain history, mark obsolete notices read and pending external
deliveries SKIPPED, then emit current deadlines with existing stable keys. Publish
SSE after commit via each existing caller. No migration or parallel subsystem.


## 025 — One encrypted credential source and validated rotation

Keep environment Client ID/API Key as bootstrap configuration only. A singleton
`ozon_credentials` row becomes authoritative after the first verified rotation;
Fernet encrypts Client ID and API Key together using backend-only
`OZON_CREDENTIALS_MASTER_KEY`. Missing/incorrect master keys fail closed rather
than falling back to obsolete environment credentials. Keep the master key
separately from database backups; changing it requires decrypting/re-encrypting
existing data. Apply migration `0019_ozon_credentials` before starting the API.

The lifespan's managed client delegates to the existing OzonClient/mock adapter
and refreshes its pool after committed configuration revisions. Import, push and
reconciliation keep using this same client. A process lock serializes use and
rotation, fitting the existing single-worker deployment. Rotation always checks
the candidate through real OzonClient.check_connection (`/v1/roles`), including
when production remains in Mock Mode; mock success cannot validate a real key.
A roles check proves authentication/connectivity, not every FBS permission.
Neither saved credential is returned, and errors/audit contain safe categories
or configuration metadata only. Frontend uses uncontrolled password inputs,
cleared after submission, without secret React state or browser storage.

One hourly lifespan check emits existing API_KEY_EXPIRING notifications at
configurable 14/7/3/1-day thresholds and at expiry. On startup/downtime recovery,
only the nearest reached threshold is emitted. Revision/expiry/threshold keys
provide existing per-user deduplication; external channels retain preferences.
Within one day, create the existing critical source-keyed Manager Task. Rotation
or expiration changes resolve the previous task and skip obsolete pending
external notices while preserving history. Expiration is manually configurable,
never inferred from key creation time. Admin-only integration status reports
reconciliation freshness, latest accepted data webhook, and sync/webhook errors
over the last 24 hours. No live account calls occur in automated tests.


## 026 — Private compressed photos and internal posting codes

Use a small `Storage` protocol (`put/read/delete`) and a `LocalStorage` adapter;
only opaque server-generated UUID keys are persisted. The existing Compose upload
volume remains `/data/uploads`. Metadata, order/blocker/comment linkage and UTC
creation time live in `photos`. S3-compatible storage can replace the adapter on
application state without changing upload business logic. Physical files and DB
commits cannot be atomic: compensate transaction failures by deleting the file;
a process crash between writing and committing may leave an unreferenced file.
No user-facing deletion is permitted in this task.

Upload raw image bodies, avoiding multipart spooling of large originals. Enforce
10 MiB by streamed byte count (`UPLOAD_MAX_BYTES` configurable), check declared
JPEG/PNG/WebP against decoded format, cap at 20 million pixels, orient using EXIF,
resize to 1600px and re-encode JPEG quality 80 without metadata. Serialize uploads
per API process to bound decoding memory on the small VPS. Original filenames,
EXIF/GPS and original phone files are never retained. Read/list/QR/lookup require
`orders.view`; upload additionally requires `comments.create` or `blockers.create`.
Comment photos require authorship or `comments.delete`. Check every target's order
on the backend. Photo upload appends existing audit/timeline and publishes SSE.

QR payload is `ozon-production:posting:<posting_number>`. The authenticated resolver
matches that payload or a raw barcode posting number exactly in the database,
including cancelled orders; arbitrary URLs are never followed. The PWA uses a
lazy-loaded ZXing browser decoder for camera QR/barcodes, requests the rear camera
only after an explicit action, stops tracks on scan/close/unmount, and offers manual
entry on camera failure. It shows the resolved order through the existing exact-ID
queue filter, clearing other filters and ignoring My Tasks ownership for that lookup.
API/photo responses remain uncached by the PWA. Real phone camera use requires HTTPS.


## 029 — Extend the existing audit table with transactional change snapshots

Keep `audit_log` and all existing semantic action records. An allowlisted SQLAlchemy
flush hook adds structured per-entity create/update/delete snapshots in the same
transaction for production status, assignments, override/pin, blockers, procurement
and links, Manager Tasks (including automatic resolution), users/roles/permissions,
workflow labels/order, priority settings, product profiles and credential metadata.
Existing summary records remain useful for authentication, bulk operations and
integration attempts; bulk records additionally carry selected order IDs/targets.
No timeline/domain event is replaced or consumed by audit. Batch old-value reads by
entity type, skip unchanged snapshots, and clear pending state on rollback. Install
hooks on application database engines; historical Alembic data seeds are excluded
because their schema predates these columns.

Never snapshot request bodies, raw Ozon data, credential ciphertext, passwords,
sessions, CSRF, Telegram or VAPID secrets. Explicit field allowlists and recursive
sensitive-key redaction protect old/new JSON. Free-text edits record field names
without copying descriptions; integration changes expose revision/expiry/check time
only. Hide SQL parameters in database errors. Request context uses the ASGI peer IP
and a bounded User-Agent; background/CLI operations have no request metadata.

Migration `0022_audit` preserves prior rows and adds nullable structured fields and
entity indexes. ORM guards reject edits/deletes, and PostgreSQL rejects UPDATE,
DELETE and TRUNCATE with a trigger. Physical user deletion that would null an audit
actor is therefore rejected; use existing user deactivation. Schema maintenance and
migration downgrade remain privileged operator actions. Existing historical rows
retain unknown entity/old/new values; do not fabricate a backfill.

Expose only paginated GET `/api/audit` with backend `audit.view`, exact user/action/
entity type/ID filters and an inclusive timezone-aware UTC period, ordered by time
and ID descending. The permission-gated mobile UI shows safe snapshots and metadata.
There are no mutation/export endpoints or additional event-store infrastructure.

## 030 — Portable Compose backup bundle and guarded restore

Use the existing Compose `backups` and `uploads` named volumes. One UTC timestamped
archive contains a `pg_dump` custom-format database dump, a gzip tar of the contents
of `/data/uploads`, and a non-secret manifest; `.env` and credentials are excluded.
Stream data from existing containers so no database/upload utilities need to be
installed on the host. Publish atomically through a temporary filename and retain
the newest configurable number of complete bundles (14 by default).

Restore validates both archive layers and the PostgreSQL dump before asking for
explicit confirmation. Short-lived Compose run containers access the existing
backend volumes, allowing the API to remain stopped throughout restore. A database
restore stops the operator from proceeding silently and restores dump objects in
the configured DB using `--single-transaction --clean --if-exists`, without owner/privilege commands. Upload restore replaces contents
of the existing persistent upload directory. Stop the app for either operation.
Keep off-host encrypted copies as a separate deployment responsibility. Runtime
restore validation still needs a Docker-enabled deployment/test host.

For local restore drills, use a separate Compose overlay that explicitly names every
volume with a fresh `DRILL_VOLUME_PREFIX`; a project name alone is insufficient
when a deployment declares fixed volume names. Backup/restore scripts accept an
optional second Compose file through `COMPOSE_OVERRIDE_FILE`. Before restore or
cleanup, inspect resolved Compose volume names and require the drill-specific
PostgreSQL/uploads/backups names. Never restore into the production named volumes.
The Windows PowerShell drill runner manages a unique project, verifies resolved
names before destructive actions, disables Git Bash path conversion, uses synthetic
data, and cleans only the verified drill Compose environment. `restore.sh --yes`
requires the explicit drill marker, overlay, generated volume prefix and matching
project name; ordinary restore remains interactively confirmed.

pg_restore reads the streamed custom dump with no input filename: a literal `-`
is a filename, not stdin. Validation and restore use the same stdin convention.
Do not drop/recreate the DB before restoring: SQL errors roll back one transaction.
Uploads extract into a staging directory on the existing volume and retain old
entries until promotion succeeds, with rollback on command failure. Database and
uploads commits cannot be atomic together; a failure after DB commit requires
rerunning restore while the app remains stopped. Process/power loss can also leave
upload recovery directories requiring operator inspection. Objects absent from
the dump are not removed by pg_restore --clean.

Task 030 verification boundary (2026-10-02): the user's real Windows Docker run
confirmed isolated volumes without production mounts, successful migrations,
PostgreSQL dump and uploads archive creation, bundle publication in /data/backups,
and failure cleanup restricted to drill resources. The Windows harness stopped at
bundle-member checking; full Windows restore is not authoritative because of
PowerShell/Git Bash/MSYS compatibility. Stop further manual Windows workaround
development. Complete task 030's implementation with passing automated checks;
require an actual isolated backup → modify → restore → verify drill on the target
Linux VPS in task 034 before production launch. All DB/upload, retention, cleanup
and production-volume preservation assertions must pass and be documented there.

## 039 — Public IPv4 HTTPS and minimal Ozon runtime access

Use pinned Caddy 2.11.6 with explicit Let's Encrypt ACME shortlived issuer and
single-origin default_sni. CertMagic 0.25.6 supports IP issuance; persistent
Caddy storage provides automatic renewal without another service/timer. Never
use internal CA or disable TLS verification. Actual public issuance/renewal
remains task 034. DOMAIN retains its historical name but accepts public IPv4.

Current runtime reads only roles and FBS list/get; warehouse/tariffs are already
in posting snapshots. Configure push through Seller UI, without requiring a
full-write application key. Official docs do not explicitly settle bare-IP URL
acceptance: require Seller Check; free DNS hostname is a documented alternative,
with unchanged source filters and reconciliation. Do not infer key lifetime:
save valid /v1/roles expires_at on rotation and show core Admin warning via
existing refresh. Optional expiration tasks/loops remain disabled by default.

Bootstrap targets fresh Debian 12 x86_64, preserves SSH/swap, and uses official
Docker apt packages. Build off-host on the 1 GB target; backup before code/image
switch, migration before startup, guarded restore. No deployment/commit/push in 039.
