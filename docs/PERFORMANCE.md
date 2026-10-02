# Task 032 — Small VPS performance

Measured locally on Windows on 2026-10-02, using private SQLite databases and
synthetic orders only. These are comparative application measurements, not Linux
VPS latency guarantees. No production data or live Ozon calls were used.

## Measurements

`tracemalloc` covers Python allocations during each authenticated request, not
native decoder/DB memory. SQL counts include authentication and bounded eager
loads. Instrumentation slows requests; absolute timings vary by host/load.

| API, 2,007 orders | Before: queries / seconds / Python peak MiB | After |
| --- | --- | --- |
| Queue, first 20 | 14 / 0.443 / 12.98 | 37 / 0.522 / 3.41 |
| Manager dashboard, including risk | 4,039 / 4.110 / 18.85 | 42 / 0.649 / 3.66 |
| Money at Risk summary | 12 / 0.596 / 14.24 | 33 / 0.470 / 2.87 |
| Analytics | 20 / 0.068 / 0.65 | 20 / 0.058 / 0.64 |

With **10,007 orders**: queue 133 queries / 2.203 s / 3.62 MiB;
dashboard 138 / 2.762 / 3.65; risk 129 / 2.580 / 2.98;
analytics 20 / 0.110 / 0.63. Bounded batches trade extra round trips for a stable
memory footprint; this is not a claim that queue latency improved at every size.
Every synthetic posting has an item and a two-step confirmed RUB tariff.
Without allocation tracing, the same 10,007-order workload measured queue
**0.494 s**, dashboard **0.575 s**, risk **0.500 s**, analytics **0.057 s**.
SQL query counting remained enabled; this is still a single local request sample,
not concurrency/p95 or an estimate for the VPS CPU.

Dashboard's measured N+1 came from committing procurement synchronization after
loading orders: ORM expiration caused thousands of reloads. Commit before reads;
SQL groups status counts and assignment workload; one batched priority/risk pass
supplies only five attention identities. Queue retains top offset+limit identities
and priorities, then loads only the response page with assignments/users. Products
and production profiles load once per batch, not per posting. Default queue omits
DONE/CANCELLED/HANDED_TO_SHIPPING; explicit status/logistics filters and exact IDs
retain archive access. History is paginated; timeline uses SQL UNION identities,
ordering/count/limit before loading the selected comments/statuses/events.

Money at Risk streams source rows, computes each order's bucket entries with a
small dictionary instead of scanning accumulated entries, retains no identities
for summaries, and retains only offset+limit entries per bucket for drill-down.
Decimal, conservative unknown-cost rules, high-water marks, categories, total
amounts and exact global ranking remain authoritative. SQL cannot simply sum raw
JSON costs: normalized timelines, unknown transitions and priority feasibility
must preserve existing business semantics. No persisted score/cache/broker added.

Notifications prefetch recipients/preferences and existing dedupe keys per batch;
repeat reconciliation has no per-order SELECT. Retirement reads notice identities
in batches and updates pending deliveries in SQL. Commit retirement even when no
new notice was created. External push/Telegram retain their existing 10-row batches,
timeouts and backoff. Reconciliation uses existing sequential scheduling, a shared
Ozon import/webhook lock and 100-row keyset backfill. It never overlaps itself.
Overdue procurement synchronization now reads tasks/links and existing source-keyed
Manager Tasks in batches, eliminating per-source lookups on repeated manager-page
reads while retaining unique-key race protection and closed-task decisions.

## Memory and production defaults

Compose runtime hard caps: PostgreSQL **256 MiB**, backend **384 MiB**, Caddy
**96 MiB**, total **736 MiB**. Dedicated production minimum: **1 CPU / 1 GB RAM**,
leaving approximately 218 MiB (decimal 1 GB) or 288 MiB (1 GiB) before kernel/host
overhead. Production explicitly limits RAM+swap to 320/512/128 MiB respectively:
at most 64/128/32 MiB swap, total 224 MiB. Recommend a 1 GiB host swap emergency
buffer with swappiness=10, not as added working RAM. Keep all functions; future
lightweight review is outside task 034. See DEPLOYMENT.md for safe host commands.
These caps require verification on the actual host;
do not confuse caps with measured container consumption. CPU quotas are 0.75,
0.75, 0.25 respectively, shared on the one CPU, not CPU reservations. Each service
has a 100-process/thread cap. No runtime Node/Vite server is deployed.

PostgreSQL: max_connections=20, shared_buffers=64MB, work_mem=2MB,
maintenance_work_mem=32MB, effective_cache_size=256MB (planner estimate, not an
allocation), query parallelism disabled, shared memory=64 MiB. Work memory is per
sort/hash operation, not per server. Existing single Uvicorn worker is required:
SSE and scheduler locks are in-process. SQLAlchemy retains pool_size=2,
max_overflow=1, pre_ping and 3-second connect timeout; add 3-second pool wait timeout.
Maximum three connections per API engine; explicit migration/backup connections
use spare PostgreSQL capacity. Liveness performs no SQL; readiness executes SELECT
1 and returns 503 on database failure. Compose healthcheck uses liveness and the
configured Host so production Host validation still applies.

Queue/risk limit remains 1–100, maximum offset 10,000 to bound heap/page retention.
Timeline/history limit 1–200; analytics page_size 1–100 and date range <=366 days;
audit/notifications/photo lists retain their existing <=100 limits. Large SQL
offsets in other paginated SQL lists can still become slow, but do not accumulate
ORM rows in Python. SSE releases the authentication DB connection before streaming,
caps subscribers at 100, pending callbacks/queues at one per subscriber, emission
at two per second, and retains the 20-second reauthentication deadline. Over-capacity
subscriptions receive 503/Retry-After. Browser refresh remains the source of truth.

Photo smoke uses a separate source-generator process so encoder allocation is
excluded from API RSS. Cold import + synthetic schema/seed + startup: about
2.2–2.4 s, **114 MiB process peak RSS**. Original photo pipeline on 20 MP JPEG
reached **421 MiB** (including test-image generation); optimized pipeline JPEG
20 MP reached **154 MiB**, PNG 20 MP **224 MiB**. WebP 20 MP still reached **422 MiB**
without source generation: reduce WebP to **10 MP**, measured **270 MiB**.
Keep JPEG/PNG at 20 MP, raw upload at 10 MiB by default, output <=1600 px, and one
upload slot per worker. JPEG draft decoding, EXIF transpose in place, and resizing
before RGB conversion remove full-size copies. WebP dimensions are guarded before
Pillow constructs its decoder, including MIME-spoofed WebP; Pillow still validates
the complete input. Header layouts verified against [WebP container specification](https://developers.google.com/speed/webp/docs/riff_container),
[lossless specification](https://developers.google.com/speed/webp/docs/webp_lossless_bitstream_specification)
and [VP8 frame header](https://datatracker.ietf.org/doc/html/rfc6386#section-9.1).
RSS and allocator behavior must be checked on Linux with real phone images.

Frontend build sampled Node + direct-child RSS peak was **428 MiB**; final PWA
precache is about 748 KiB. Runtime Caddy serves static files and has GOMEMLIMIT=64MiB
(soft Go heap target). Compose service limits do not constrain image builds.
Prefer building images in CI/on a larger host and pulling them onto the VPS;
do not build frontend concurrently with production workload on the 1 GiB host.

## Index review

Migration `0023_performance` adds:

- notifications `(user_id, created_at, id)` for recipient pages;
- notification_deliveries `(channel, status, next_attempt_at, id)` for pending due work;
- audit_log `(created_at, id)` for default descending audit pages;
- comments/order_timeline_events `(order_id, created_at, id)`;
- status_history `(order_id, changed_at, id)` for timeline branches.

Existing indexes cover order status/deadline/warehouse, assignment user/unique
order, item order/offer/SKU, analytics cohort timestamps and audit filter columns.
SQLite EXPLAIN confirms the recipient composite index; migrations are tested
through upgrade/downgrade/upgrade. PostgreSQL plans are **not locally verified**.
Substring `ILIKE '%term%'` does not benefit from ordinary B-tree search indexes;
do not add speculative trigram indexes until actual search plans/latency justify
their storage/write cost. Exact filters and keysets use existing indexes.

## Reproduce and VPS verification

From repository root on Windows:

```powershell
./scripts/benchmark-performance.ps1 -Orders 10000
./scripts/benchmark-performance.ps1 -Orders 10000 -WithoutAllocationTracing
backend/.venv/Scripts/python.exe scripts/profile-runtime.py --format JPEG
backend/.venv/Scripts/python.exe scripts/profile-runtime.py --format PNG
backend/.venv/Scripts/python.exe scripts/profile-runtime.py --format WEBP
```

On Linux, use the backend dev environment:

```sh
cd backend
PERFORMANCE_SIZE=10000 .venv/bin/python -m pytest tests/test_performance.py::test_synthetic_key_pages -s -q
.venv/bin/python ../scripts/profile-runtime.py --format WEBP
```

Benchmark databases/uploads exist only in temporary directories; the scripts never
seed the configured deployment database. Tests cover exact ranked pagination across
batches, archive access, SQL timeline pages/tie ordering, financial totals beyond
the selected page, repeated notification deduplication, 1,000-event SSE bursts,
subscriber capacity, photo orientation/header guards, analytics and migration indexes.
The 60-overdue-procurement scenario guards manager-page query count; notification
preference opt-outs remain effective alongside mandatory overdue alerts.
Existing Ozon tests cover cursor pages, rollback/replays, sequential scheduling and
responsive API during slow reconciliation. No live account testing.

Docker executable is unavailable here. Required target-host checks:

1. Follow [DEPLOYMENT.md](DEPLOYMENT.md) and `scripts/production.sh`: explicit
   backup/update/migration before API startup, status, HTTPS `/api/health` and
   `/api/health/ready`. Opt-in `E2E_CONTAINER=true E2E_PROBE=true npm run test:e2e`
   produces isolated PostgreSQL plans/concurrency/CPU/memory/RSS reports on Linux;
   this runtime-unverified runner uses small fixtures, not realistic capacity data.
2. `docker stats --no-stream`, host available memory/swap and OOM/restart counts
   during idle, synthetic requests, parallel browsers/SSE and uploads. Repeat with
   real phone JPEG/PNG/WebP within limits. Verify p95 latency at actual concurrency.
3. Inspect actual pool/pg_stat_activity counts and wait behavior while reconciliation
   and deliveries run. Verify only one scheduler instance and no prolonged idle
   transactions, readiness under exhausted pool and recovery after DB restart.
4. Run `ANALYZE` on a separate synthetic PostgreSQL database. Use EXPLAIN
   (ANALYZE, BUFFERS) on queue filters/keyset, dashboard grouped counts/workload,
   analytics cohorts, audit ordering, notification recipient/due-delivery queries
   and timeline UNION pages. Do not use production data for load tests. Confirm
   index scans/selectivity, sort spill and memory; small tables may rightly scan.
5. Confirm two-browser SSE, callback coalescing and auth/reconnect over Caddy.
   Existing task 034 isolated Linux backup/restore gate remains mandatory.

Exact priority/risk evaluation is O(active postings). At 10,000 simultaneously
active postings the local instrumented requests take seconds despite bounded
memory. Measure realistic active cardinality and VPS p95 before declaring this
load acceptable or adding SQL projections/background snapshots. No Redis/Celery
or extra queue/database has been introduced.
