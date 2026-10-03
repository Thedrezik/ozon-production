# PROJECT STATE

Last updated: 2026-10-03

## Completed

- Task 040: native Debian 12 production preparation; host PostgreSQL 15, managed Python 3.12/release venv, one systemd worker, pinned system Caddy 2.11.6/static PWA/IP TLS. Native bootstrap/deploy/update/rollback/backup/restore/smoke + isolated Unix-socket PostgreSQL drill, private FHS env, log/backup/release retention and revocable agent SSH runbook. Docker production Compose removed; Docker remains development/tests only.

- Task 039: IP-only production preparation and Ozon review; Debian 12 bootstrap/runbook/env ready. Ozon literal-IP webhook acceptance remains unconfirmed until Seller Check; free DNS fallback documented, reconciliation retained. Caddy config validated locally; live TLS/renewal and Linux acceptance remain 034.

- Tasks 001–033: core production workflow, RBAC/auth/audit, priority/tariffs/Money at Risk, blockers/Manager Tasks/procurement, Ozon import/webhook/reconciliation/encrypted credentials, photos/QR, notifications/Web Push/Telegram, PWA/offline, analytics, backup, security and performance hardening. Details remain in tasks/ and the dedicated docs.
- Tasks 033/035: desktop/mobile E2E and pre-deployment review; historical findings remain in FINAL_REVIEW.md. One worker and pool 2+1 retained.
- Task 036 completed and verified: two principal roles; Home/Queue/chronological Feed/Problems/My Tasks; atomic claim → production → produced → packed → Ozon shipment; simple problems/comments/human timeline; two cancellation branches; three core Telegram alerts; real verified Decimal tariff adapter. Extensions preserved behind empty-default flags. Current product is CORE_WORKFLOW.md; historical PRODUCT/decisions retained. Migration head `0024_core_workflow`.
- Task 037 completed: compact Home/Orders/Feed/Problems/order cards/timeline, unified Tailwind tokens, mobile four-item bottom navigation/safe areas, inline forms and double-submit guards, long-text disclosures, accessible states/focus/reduced motion. No new library or backend/domain change. Design rules: DESIGN_SYSTEM.md.

- Task 038: visual refinement of Home/Orders/Feed/Problems/exact-order/offline. 1280px workspace, navy first-order focus, compact shell/sync, calm rows, shared buttons/type/surfaces. Dashboard focus includes bounded real product/assignment/problem/Decimal risk projection with finance RBAC. No new dependency/schema/domain transition. Final follow-up adds a joinery logo/PWA icons, unified Home risk/counters/empty state, compact user menu and 16px less mobile top space.

## Current

- Task 040 preparation complete; no VPS deployment, commit or push. Task 039 HTTPS/Ozon behavior retained. Native production runbook: DEPLOYMENT.md; optional features remain off.
- Task 034 **pending**: actual Debian/systemd/PostgreSQL/Caddy, native restore, public IP certificate issuance/renewal, provider/device/capacity acceptance. Docker live validation is no longer a production gate.

## Next

- Resume task 034 when VPS is available: preflight, guarded native backup→modify→restore→verify, native PostgreSQL/Caddy checks, HTTPS/security/persistence/capacity, real Ozon/Telegram and physical-phone PWA. Push/camera/photos gates apply only if extensions are enabled. No production deployment/commit/push in 040.

## Known Issues

- Core has no autonomous Telegram deadline alerts; read-time Priority/Money at Risk + shared 60 s refresh provide current operational risk. Unknown/unsupported tariff sources are explicitly unpriced; RUB risk uses confirmed charges only. Historical import outside the discovery window requires backfill.
- Credential SELECT releases its slot before HTTP; domain Ozon/Telegram transactions can still wait on providers. Delivery/commit crash gap may redeliver Telegram. Verify slow-provider/pool behavior on target.
- No target Debian VPS available here. Native bootstrap/services/pg_dump+pg_restore drill, public TLS and capacity are **NOT RUN**. Git Bash mocks and Windows Caddy adapt/validate are preparation evidence only. systemd-analyze is unavailable locally; static unit checks passed and real unit verification is built into deploy.
- Full isolated native Linux backup → modify DB/uploads → restore → verify is a mandatory launch blocker. The drill uses a fresh initdb cluster/private Unix socket and synthetic paths, never production DB/env/uploads; no Docker required.
- Native RAM/disk savings are unmeasured. PostgreSQL starts with 64MB shared_buffers, 20 connections, 2MB work_mem; API pool 2+1/one worker. No Docker-specific resource caps; 1 GiB swap is emergency reserve. ~7 GB disk/build peaks/two releases/backup bytes/WAL need measurement; log/count retention alone does not guarantee capacity. See PERFORMANCE.md.
- Real Ozon/Telegram and physical-phone PWA remain HTTPS/device acceptance checks. Automated tests use synthetic providers only. Official tariff schema verified 2026-10-02; recheck webhook source networks on deployment (OZON_API.md).
- Offline queue is read-only, one loaded page/one hour/same tab; no offline auth/mutations. Optional photos retain existing MIME/dimension limits; device decoder RSS requires verification when enabled.
- Restore DB/uploads is not jointly atomic; pg_restore clean does not remove objects absent from dump. Schema rollback failures require stopped writers and controlled separate-DB recovery; see `DEPLOYMENT.md`/`BACKUP_RESTORE.md`.
- Existing Starlette/httpx and Alembic deprecation warnings remain.

## Deployment

- Not deployed. Production is native only: `/opt/ozon-production/{repo,releases,current}`, private root-600 `/etc/ozon-production/production.env`, ordinary uploads/backups under `/var/lib/ozon-production`, persistent `/var/lib/caddy`. Backup → fetch/build → migrations → restart/readiness → smoke; guarded snapshot rollback with previous venv/env. Only TCP 80/443 plus actual SSH; DB/API loopback. No Redis/Celery/Node runtime server.
- All live task 034 acceptance gates remain NOT RUN. Preparation completion does not authorize production launch.

## Last Tests

- Task 040 full backend suite: **315 passed**, 8 existing Starlette/httpx/Alembic warnings; synthetic providers only. After adding native security/env/archive checks, focused deployment suite: **21 passed** (includes 9 new native tests).
- Ruff `check app tests alembic ../scripts` from backend passed. Frontend lint/typecheck/build passed; Vite/esbuild needed sandbox escalation. Production PWA desktop/mobile E2E **12/12 passed**, retries 0, real mock FastAPI/migrations/SSE/offline.
- All shell scripts `bash -n` passed. Native synthetic backup/restore and update/first-deploy failure ordering passed under Git Bash; development-only Compose backup and PowerShell command guard regression passed. No Linux native execution claimed.
- Pinned checksum-verified Caddy 2.11.6 Windows adapt/validate of native IPv4 config passed; public ACME shortlived/default_sni, redirects, loopback proxy/static paths checked. No server started/certificate requested. Static unprivileged systemd unit checks passed; native `systemd-analyze verify` NOT RUN locally.
- `git diff --check` passed. Public TLS/renewal, actual native PostgreSQL restore, Ozon Seller Check/minimal permissions/delivery, Telegram, physical phone and target capacity **NOT RUN**; task 034 pending. No commit/push.
