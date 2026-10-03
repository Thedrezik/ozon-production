# PROJECT STATE

Last updated: 2026-10-03

## Completed

- Task 039: IP-only production preparation and Ozon review; Debian 12 bootstrap/runbook/env ready. Ozon literal-IP webhook acceptance remains unconfirmed until Seller Check; free DNS fallback documented, reconciliation retained. Caddy config validated locally; live TLS/renewal and Linux acceptance remain 034.

- Tasks 001–033: core production workflow, RBAC/auth/audit, priority/tariffs/Money at Risk, blockers/Manager Tasks/procurement, Ozon import/webhook/reconciliation/encrypted credentials, photos/QR, notifications/Web Push/Telegram, PWA/offline, analytics, backup, security and performance hardening. Details remain in tasks/ and the dedicated docs.
- Tasks 033/035: desktop/mobile E2E and pre-deployment review; historical findings remain in FINAL_REVIEW.md. One worker and pool 2+1 retained.
- Task 036 completed and verified: two principal roles; Home/Queue/chronological Feed/Problems/My Tasks; atomic claim → production → produced → packed → Ozon shipment; simple problems/comments/human timeline; two cancellation branches; three core Telegram alerts; real verified Decimal tariff adapter. Extensions preserved behind empty-default flags. Current product is CORE_WORKFLOW.md; historical PRODUCT/decisions retained. Migration head `0024_core_workflow`.
- Task 037 completed: compact Home/Orders/Feed/Problems/order cards/timeline, unified Tailwind tokens, mobile four-item bottom navigation/safe areas, inline forms and double-submit guards, long-text disclosures, accessible states/focus/reduced motion. No new library or backend/domain change. Design rules: DESIGN_SYSTEM.md.

- Task 038: visual refinement of Home/Orders/Feed/Problems/exact-order/offline. 1280px workspace, navy first-order focus, compact shell/sync, calm rows, shared buttons/type/surfaces. Dashboard focus includes bounded real product/assignment/problem/Decimal risk projection with finance RBAC. No new dependency/schema/domain transition. Final follow-up adds a joinery logo/PWA icons, unified Home risk/counters/empty state, compact user menu and 16px less mobile top space.

## Current

- Task 039 preparation complete: public IPv4 env, pinned Caddy 2.11.6 with public shortlived ACME/default_sni, bootstrap/deploy/update/smoke and verified upstream expiry + core Admin warning. Optional features remain off. No deployment/commit/push performed.
- Task 034 remains **pending** for actual Linux VPS/live acceptance. Prepared Compose/private env/backup/update/rollback/guarded restore/container E2E/probes/public smoke remain in DEPLOYMENT.md.

## Next

- Resume task 034 when VPS is available: preflight, guarded native backup→modify→restore→verify, isolated PostgreSQL/Caddy E2E, HTTPS/security/persistence/capacity, real Ozon/Telegram and physical-phone PWA. Push/camera/photos gates apply only if extensions are enabled. No production deployment/commit/push in 036.

## Known Issues

- Core has no autonomous Telegram deadline alerts; read-time Priority/Money at Risk + shared 60 s refresh provide current operational risk. Unknown/unsupported tariff sources are explicitly unpriced; RUB risk uses confirmed charges only. Historical import outside the discovery window requires backfill.
- Credential SELECT releases its slot before HTTP; domain Ozon/Telegram transactions can still wait on providers. Delivery/commit crash gap may redeliver Telegram. Verify slow-provider/pool behavior on target.
- Docker CLI/daemon and target VPS unavailable here. No Compose config/build/start, PostgreSQL query plans, container E2E, public TLS or actual Linux restore were executed. Caddy 2.11.6 Windows adapt/validate passed; no public issuance/renewal was attempted. YAML parsing/Git Bash synthetic checks are not Linux acceptance.
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

- Task 039 full backend suite: **315 passed**, 8 existing Starlette/httpx/Alembic deprecation warnings; synthetic providers only. Includes 25 focused private-env/encrypted-credentials/expiry checks.
- Ruff `check app tests alembic ../scripts` from backend: passed. Frontend lint/typecheck/build: passed; Vite build required sandbox escalation. Production-PWA desktop/mobile E2E: **12/12 passed**, retries 0, actual mock FastAPI/migrations/SSE/offline.
- All shell scripts `bash -n`, synthetic production-flow and backup/restore guard checks passed under Git Bash; not native Linux execution. Bootstrap itself was not run on a VPS.
- Official Caddy 2.11.6 Windows release downloaded and SHA512 matched publisher checksum. `adapt`/`validate` passed for a synthetic global IPv4; JSON confirms sole public ACME issuer + shortlived + default_sni, automatic redirects. No server started/certificate requested.
- Docker CLI unavailable: Compose config/build/container E2E **NOT RUN**. Public IP TLS issuance/renewal, real Ozon URL/permissions/delivery, Telegram, physical Android/PWA, target performance and Linux restore **NOT RUN**; task 034 remains pending.
- git diff --check passed. Task 038 historical visual review: 75/75 states; no core UI redesign in 039.
