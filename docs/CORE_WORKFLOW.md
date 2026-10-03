# Current product — task 036, 2026-10-02

About ten Ozon FBS postings/day, small furniture workshop. The app answers what
to do next, why it is urgent, where a problem is, who owns it and how much confirmed
money may be lost. Extended historical requirements are inactive unless enabled
explicitly; see OPTIONAL_FEATURES.md. Do not delete legacy data/decisions.

## Users and screens

Two principal roles: ADMIN (multiple administrators allowed; deputy is another
ADMIN) and PRODUCTION_WORKER. SUPER_ADMIN remains for bootstrap/maintenance;
legacy roles and assignments are retained. Workers see operational orders/all
active problems, claim work, advance allowed own-order stages, comment and resolve
problems. No admin credentials/settings/audit. Every permission is backend enforced.
Prices are operational order data under orders.view; risk money requires finance.view.

Home shows ranked orders/reasons, deadlines/countdown, critical problems,
readiness/overdue and critical cancellation. Admin Money at Risk has clickable
time buckets and category drill-down. No employee/historical analytics by default.
Queue is active Priority ranking/search/pagination; My Tasks limits assignments.
Feed is all arrivals, including cancellations/shipped, sorted strictly ascending by
Ozon in_process_at (fallback local created_at), then ID for ties, using SQL pages.
It shows date, posting/order number, offer_id/SKU, available name, quantity, price/
currency or unknown price, external status, red cancellation. No read/acknowledge.
Problems lists every order with OPEN/IN_PROGRESS blockers, including archive;
navigation badge counts all active problems independently of page limits.
Administrator tools are secondary, not the worker's workflow.

## Workflow and history

**New → In progress → Produced → Packed → Shipped.** Storage codes remain
NEW → IN_PRODUCTION → PRODUCED → READY_TO_SHIP → HANDED_TO_SHIPPING.
Legacy QUEUED/SENT_TO_PRODUCTION display as New; QUALITY_CHECK/PACKING as Produced;
DONE as Shipped. No destructive enum migration.

Claim atomically locks Order, checks assignment/stage, assigns current employee,
starts IN_PRODUCTION and records history/human timeline/audit. A competing claim
returns 409; UI explains and reloads server state.
Legacy initial-stage assignments can be claimed by the same assignee to start
production atomically; other assignees still get 409. No duplicate assignment.
Worker advances own order to PRODUCED, then READY_TO_SHIP. No human shipment transition, including administrators.
Verified external Ozon delivering/driver_pickup/delivered confirms handover once.
Existing active problems do not erase an actual external shipment fact.

Problem action requires only reason text. It stores author/time, saves previous
stage, marks BLOCKED/red, enters Problems, updates badge/timeline/audit and queues
Telegram for administrators. No separate Manager Task in core. New/produced/packed
orders may also have problems. Lifecycle Active → Resolved, with resolved actor,
time and optional comment. Last closure restores prior stage, except external
cancellation, which must not resume production. Workers have blockers.resolve.

Simple comments retain author/text/UTC timestamp. Lazy paginated chronological
timeline shows order received, claim, stages, comments, problem create/resolve,
Ozon cancellation, logistics/date changes. Backend audit is a separate admin tool.

## Ozon, cancellation and tariff

Webhook is primary: validated durable inbox, existing get adapter, shared idempotent
upsert/effects, commit, SSE. Reconciliation uses existing v4 cursor import plus
known-posting get backfill; starts at startup, then waits 900 seconds after completion.
Stale threshold is 1800 seconds. Missing list entries never imply cancellation.
Older history outside the rolling discovery window requires admin backfill.

Before-start cancellation remains red in Feed, leaves active queue and does not
send critical production Telegram. After-start cancellation preserves local stage/
assignment/history, stays critical in Queue/Home/Feed, prohibits ordinary changes
and sends one admin alert with posting, article, stage and assignee. Administrator
explicitly closes local production. Replay does not duplicate notices/deliveries.
Closing local production does not generate another cancellation Telegram alert.
Both documented cancelled and cancelled_from_split_pending (split parent)
follow these rules and are excluded from financial risk. Closing local production
removes the needs-intervention marker; the cancelled history stays red.

Real adapter app.ozon_tariff is connected to import/webhook/reconciliation upsert.
Rendered official Seller v4 schema was verified 2026-10-02. Supplied tariff_charge
is discount/surcharge, not price × rate; min_charge is not added. Discount has
negative cost, commission positive. v3 get current/next charges are decimal strings
with separate currency codes; v4 list uses Money objects. Explicit no_discount
zero is priced, but empty strings never imply zero; confirmed steps can price it.
A step's tariff_deadline_at ends that stage; the preceding end supplies the next
boundary, overridden by explicit next_tariff_starts_at when available. Finite final end gets unknown successor,
not invented future cost. Sentinel year 9999 is not a new stage.

Unknown type/money or malformed boundaries retain safe unknown money. Inconsistent
full history falls back to explicit current/next snapshot. Old identical snapshots
receive missing adapter projection on ingestion, without duplicate orders.
Money uses Decimal. Priority retains deadline/tariff/finance/normative/feasibility/
blocker/override reasons. Risk counts confirmed RUB high-water increments without
double counting, splits feasibility/high-risk/blocked/already-degraded and unknown.
No historical savings estimate. Projections are evaluated at reads/events;
core has no autonomous Telegram deadline-alert promise or new scheduler.

## Telegram, refresh, security and deployment

Telegram is core alert delivery through existing Notification/Delivery/link/retry
mechanisms: new problem, cancellation after production starts, Ozon sync/webhook
failure threatening order discovery. Linked administrators receive these without
per-event preferences. Ordinary statuses/readiness/deadline/procurement/key expiry
do not generate noise. Configure bot/HTTPS webhook and bind admins before live use.
Provider acceptance/DB commit cannot be atomic; crash redelivery remains possible.

One SSE invalidation stream per session, burst coalescing; authenticated 20-second
reconnect retains task 031 checks without another open-triggered page refresh.
Epoch/revision checkpoints recover changes during reconnect gaps/backend restart;
unchanged reconnect does not reload the page. No event replay store is required.
One shared 60-second fallback/clock refresh plus focus/online recovery. Local
countdown does not poll API. PWA shell cache, NetworkOnly APIs and one-hour same-tab
read-only offline snapshot remain; no offline auth/actions/deferred replay.

HTTPS, HttpOnly sessions/CSRF, scrypt, backend RBAC, login/body/upload limits,
encrypted credentials and immutable audit remain. PostgreSQL + one backend worker
+ Caddy on dedicated 1 CPU/1 GB Linux VPS. Pool 2+1 and configured memory caps
256/384/96 MiB remain, not a measured guarantee. No Redis/Celery. Backup and native
isolated Linux restore are mandatory. Disabled features/data remain restorable.

Acceptance: full backend/Ruff/frontend lint/typecheck/build; desktop/mobile E2E
automatic mock order → claim → comment → shared problem → fake Telegram side effect
→ resolution → PRODUCED → READY_TO_SHIP → external shipment, plus both cancellations,
RBAC/409/offline/reconciliation. No production account in automated tests.
Task 034 stays pending for Linux/PostgreSQL/Caddy/TLS/restore/capacity/providers/
physical-phone verification. Task 036 does not deploy or commit/push.
