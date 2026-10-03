# PROJECT STATE

Last updated: 2026-10-03

## Completed

- Tasks 001–033: core production workflow, RBAC/auth/audit, priority/tariffs/Money at Risk, blockers/Manager Tasks/procurement, Ozon import/webhook/reconciliation/encrypted credentials, photos/QR, notifications/Web Push/Telegram, PWA/offline, analytics, backup, security and performance hardening. Details remain in tasks/ and the dedicated docs.
- Tasks 033/035: desktop/mobile E2E and pre-deployment review; historical findings remain in FINAL_REVIEW.md. One worker and pool 2+1 retained.
- Task 036 completed and verified: two principal roles; Home/Queue/chronological Feed/Problems/My Tasks; atomic claim → production → produced → packed → Ozon shipment; simple problems/comments/human timeline; two cancellation branches; three core Telegram alerts; real verified Decimal tariff adapter. Extensions preserved behind empty-default flags. Current product is CORE_WORKFLOW.md; historical PRODUCT/decisions retained. Migration head `0024_core_workflow`.
- Task 037 completed: compact Home/Orders/Feed/Problems/order cards/timeline, unified Tailwind tokens, mobile four-item bottom navigation/safe areas, inline forms and double-submit guards, long-text disclosures, accessible states/focus/reduced motion. No new library or backend/domain change. Design rules: DESIGN_SYSTEM.md.

- Task 038: visual refinement of Home/Orders/Feed/Problems/exact-order/offline. 1280px workspace, navy first-order focus, compact shell/sync, calm rows, shared buttons/type/surfaces. Dashboard focus includes bounded real product/assignment/problem/Decimal risk projection with finance RBAC. No new dependency/schema/domain transition. Final follow-up adds a joinery logo/PWA icons, unified Home risk/counters/empty state, compact user menu and 16px less mobile top space.

## Current

- Task 038 complete: final production-PWA E2E 12/12 and 75-state visual/accessibility review passed. Task 036 core/optional gates, Ozon/Telegram and SSE/shared fallback preserved. Optional features remain off; re-enabling: OPTIONAL_FEATURES.md. No deployment/commit/push performed.
- Task 034 remains **pending** for actual Linux VPS/live acceptance. Prepared Compose/private env/backup/update/rollback/guarded restore/container E2E/probes/public smoke remain in DEPLOYMENT.md.

## Next

- Resume task 034 when VPS is available: preflight, guarded native backup→modify→restore→verify, isolated PostgreSQL/Caddy E2E, HTTPS/security/persistence/capacity, real Ozon/Telegram and physical-phone PWA. Push/camera/photos gates apply only if extensions are enabled. No production deployment/commit/push in 036.

## Known Issues

- Core has no autonomous Telegram deadline alerts; read-time Priority/Money at Risk + shared 60 s refresh provide current operational risk. Unknown/unsupported tariff sources are explicitly unpriced; RUB risk uses confirmed charges only. Historical import outside the discovery window requires backfill.
- Credential SELECT releases its slot before HTTP; domain Ozon/Telegram transactions can still wait on providers. Delivery/commit crash gap may redeliver Telegram. Verify slow-provider/pool behavior on target.
- Supported Docker daemon/target VPS unavailable here. Windows exposes only service WSL docker-desktop; its CLI refuses supported access. No Compose config/build/start, PostgreSQL query plans, container E2E, Caddy/public TLS or actual Linux restore were executed. New runners are implemented but runtime-unverified; YAML parsing/Git Bash synthetic checks are not Linux acceptance.
- Full isolated Linux backup → modify DB/uploads → restore → verify is a mandatory launch blocker. Earlier Windows Docker evidence confirmed backup creation, not authoritative restore. Production volumes must never be mounted/deleted by drills.
- Performance measurements are Windows/SQLite comparisons; exact queue priority/risk is O(active postings). PostgreSQL/backend/Caddy RAM caps 256/384/96 MiB total 736 MiB; RAM+swap ceilings 320/512/128 MiB. Recommend 1 GiB host swap as an emergency buffer, not working RAM; reserve host memory for Linux/Docker. Target CPU/RSS/concurrency/connection capacity requires measurement. Build images and run browsers off the live 1 GB VPS; target drill can reuse DRILL_BACKEND_IMAGE. See `PERFORMANCE.md`.
- Real Ozon/Telegram and physical-phone PWA remain HTTPS/device acceptance checks. Automated tests use synthetic providers only. Official tariff schema verified 2026-10-02; recheck webhook source networks on deployment (OZON_API.md).
- Offline queue is read-only, one loaded page/one hour/same tab; no offline auth/mutations. Optional photos retain existing MIME/dimension limits; device decoder RSS requires verification when enabled.
- Restore DB/uploads is not jointly atomic; pg_restore clean does not remove objects absent from dump. Schema rollback failures require stopped writers and controlled separate-DB recovery; see `DEPLOYMENT.md`/`BACKUP_RESTORE.md`.
- Existing Starlette/httpx and Alembic deprecation warnings remain.

## Deployment

- Production not deployed. Use `docker-compose.production.yml` via `scripts/production.sh`, private `.env.production`, backup before update and successful migration before API startup. Only TCP 80/443 are published; preserve SSH access. No Redis/Celery.
- All live acceptance gates are NOT RUN. Task 035 was explicitly authorized before these gates; its completion does not authorize production launch or complete task 034.

## Last Tests

- Task 038 final follow-up: lint/typecheck/build and diff check passed; visual/accessibility **75/75** at all three sizes, with explicit before/after 1440/390 comparisons in `frontend/e2e-results/ui-review/task-038-final`. Initial gzip **91.24 → 91.89 kB** (+0.65 kB, 0.7%), no library; PWA precache **307.72 KiB**. Final follow-up production-PWA E2E **12/12 passed**, desktop/mobile, retries 0; backend untouched. Fixture readiness now requires its own successful Uvicorn bind before health polling; first parallel run had 11/12 with an early/foreign-port response.
- Task 038 lint/typecheck/build and Ruff app/tests/Alembic/scripts passed. Dashboard/core/performance backend tests **30 passed** (including focus product/assignment/problem resolution/unknown-money/finance RBAC regression and 2,000-order query-budget test). Last full backend suite remains the task 036 run below.
- Visual/accessibility browser review **75 states passed**, 1440×1000 / 1024×768 / 390×844. Full-page/viewport screenshots and JSON: ignored `frontend/e2e-results/ui-review/task-038`; 037 comparison retained in `after`. Checks: overflow, first mobile focus/action visibility, keyboard/labels/touch/contrast/reduced motion, profile close/Escape/offline, long text, cancellations, empty/loading/errors, sync fresh/stale/failure, offline/reconnect and double-submit. Focus text contrast ≥7.31:1. Physical device/assistive technology remains 034.
- Initial gzip JS **83.17 → 83.82 kB**, CSS **6.08 → 7.42 kB**, combined **89.25 → 91.24 kB** (+1.99 kB, 2.2%); core precache **294.73 → 304.29 KiB**. No dependencies; optional/admin lazy-loading preserved. git diff --check passed.
- First 038 E2E 11/12: worker login encountered test-proxy 502. Dedicated upstream sockets replace keep-alive reuse in the local harness; no retries/skips/weakened checks. Full rerun and final-build rerun both **12/12 passed**, desktop/mobile, retries 0.
- Task 036 full backend **299 passed**, all collected tests in two non-overlapping file groups (161 + 138), preserving pytest file order. Ruff app/tests/Alembic/scripts passed. Fixed the performance test's time-dependent assumption that every near-term increase belongs to next_hours rather than an earlier local cutoff/midnight bucket.
- Frontend lint/typecheck/build passed; final E2E **12/12**, desktop/mobile without retries, actual FastAPI/migrations/PWA, including both documented cancellation statuses, actual SSE disconnect/focus fallback/checkpoint recovery and closing cancellation without another Telegram alert. Measured navigation: Home/Queue/Problems each one page HTTP request, plus shared badge/sync reads on refresh. Performance details: PERFORMANCE.md.
- git diff --check passed. Existing Starlette/httpx/Alembic deprecations remain. Task 034 synthetic guards are not Linux acceptance.
- Docker/PostgreSQL/Caddy/public HTTPS/container E2E/native Linux restore and external provider/physical-device checks: **NOT RUN**, commands/checklists in `DEPLOYMENT.md`.
