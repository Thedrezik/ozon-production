# PROJECT STATE

Last updated: 2026-10-02

## Completed

- Tasks 001–033: core production workflow, RBAC/auth/audit, priority/tariffs/Money at Risk, blockers/Manager Tasks/procurement, Ozon import/webhook/reconciliation/encrypted credentials, photos/QR, notifications/Web Push/Telegram, PWA/offline, analytics, backup, security and performance hardening. Details remain in tasks/ and the dedicated docs.
- Task 033: real application desktop/mobile E2E on migrated isolated SQLite, 12/12 without retries. Task 032 keeps one worker, pool 2+1 and migration head `0023_performance`.
- Task 035: **pre-deployment final review completed** before renting VPS. Full PRODUCT/code coverage and five finding categories are in [FINAL_REVIEW.md](FINAL_REVIEW.md). Fixed cancelled-posting blocker closure, priority-response finance redaction, P4 filter and missing-tariff unknown-risk reporting; regression tests added. No features removed, no deployment/commit/push/task 036.

## Current

- Task 034 dedicated 1 CPU / 1 GB implementation prepared: standalone production Compose/private env generator; explicit consistent backup/update/migration/rollback operations; guarded native Linux restore drill; optional PostgreSQL/Caddy HTTPS mode for existing E2E with query/resource probes; public smoke and `docs/DEPLOYMENT.md`.
- Task 034 remains **pending** only for unavailable real Linux VPS/live acceptance. Preparation exists; runtime validation is deferred until final product corrections. Task 035 completed as a review, not production acceptance.

## Next

- User selects final product corrections/lightweight options from FINAL_REVIEW.md; no next task created automatically.
- Afterwards resume task 034: target preflight, guarded Linux restore, isolated PostgreSQL/Caddy E2E, public HTTPS/security/persistence/capacity and provider/physical-phone gates in DEPLOYMENT.md. Mark 034 completed only after actual runtime acceptance passes.

## Known Issues

- MVP does not fully satisfy PRODUCT: real tariff adapter absent; clock-based deadline/procurement alerts depend on reads/changed imports; DEADLINE_RISK/STALLED_ORDER/UNASSIGNED_ORDER have no automatic evaluators. Worker comments/packing blockers, list limits, timezone/detail UX, workload minutes and custom-role/configuration gaps remain review decisions. See FINAL_REVIEW.md for evidence and severity.
- Refresh triggers overlap (SSE reconnect, auth 30 s, refresh 60 s); external HTTP retains DB transactions/slots with pool 2+1. These are measured-capacity/final-correction concerns, not evidence that every optional function must be removed.
- Supported Docker daemon/target VPS unavailable here. Windows exposes only service WSL docker-desktop; its CLI refuses supported access. No Compose config/build/start, PostgreSQL query plans, container E2E, Caddy/public TLS or actual Linux restore were executed. New runners are implemented but runtime-unverified; YAML parsing/Git Bash synthetic checks are not Linux acceptance.
- Full isolated Linux backup → modify DB/uploads → restore → verify is a mandatory launch blocker. Earlier Windows Docker evidence confirmed backup creation, not authoritative restore. Production volumes must never be mounted/deleted by drills.
- Performance measurements are Windows/SQLite comparisons; exact queue priority/risk is O(active postings). PostgreSQL/backend/Caddy RAM caps 256/384/96 MiB total 736 MiB; RAM+swap ceilings 320/512/128 MiB. Recommend 1 GiB host swap as an emergency buffer, not working RAM; reserve host memory for Linux/Docker. Target CPU/RSS/concurrency/connection capacity requires measurement. Build images and run browsers off the live 1 GB VPS; target drill can reuse DRILL_BACKEND_IMAGE. See `PERFORMANCE.md`.
- Real Ozon import/webhook/provider delivery and physical-phone PWA/camera/Web Push remain HTTPS/device acceptance checks. Automated tests never use production provider credentials. Official Ozon contracts were verified 2026-10-01; recheck source networks on deployment (`OZON_API.md`).
- Signed mapping of real Ozon tariff sources remains unconfirmed; Money at Risk does not infer amounts from order prices/unsigned discounts. Historical imports beyond the discovery window require the existing importer.
- Offline queue is read-only, one loaded page/one hour/same tab; no offline auth/mutations. HEIC/HEIF unsupported; JPEG/PNG up to 20 MP, WebP up to 10 MP. Actual phone decoder RSS remains a deployment check.
- Restore DB/uploads is not jointly atomic; pg_restore clean does not remove objects absent from dump. Schema rollback failures require stopped writers and controlled separate-DB recovery; see `DEPLOYMENT.md`/`BACKUP_RESTORE.md`.
- Existing Starlette/httpx and Alembic deprecation warnings remain.

## Deployment

- Production not deployed. Use `docker-compose.production.yml` via `scripts/production.sh`, private `.env.production`, backup before update and successful migration before API startup. Only TCP 80/443 are published; preserve SSH access. No Redis/Celery.
- All live acceptance gates are NOT RUN. Task 035 was explicitly authorized before these gates; its completion does not authorize production launch or complete task 034.

## Last Tests

- Task 035 baseline backend **275 passed**; final backend **279 passed**, including four new regression cases. Focused blockers/priority/Ozon changes **17 passed**, risk/dashboard/performance **16 passed**. Ruff app/tests/Alembic/deployment Python scripts passed.
- Frontend lint/typecheck/build passed; baseline and final E2E **12/12 each**, desktop/mobile without retries, actual FastAPI/migrations/PWA on isolated SQLite. Offline snapshot/privacy/expiry/NetworkOnly tests passed. Initial sandbox esbuild parent-directory denial resolved by authorized local rerun.
- git diff --check passed. Existing Starlette/httpx and Alembic warnings remain. Task 034's earlier Bash synthetic guards passed, not repeated as Linux acceptance.
- Docker/PostgreSQL/Caddy/public HTTPS/container E2E/native Linux restore and external provider/physical-device checks: **NOT RUN**, commands/checklists in `DEPLOYMENT.md`.
