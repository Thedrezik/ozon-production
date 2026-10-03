# Task 036 — Simplification / final product workflow

status: completed

Source: user-supplied task 036. Local implementation; no deployment/commit/push.
Task 034 remains pending. Current product: docs/CORE_WORKFLOW.md; preserved
extensions and restoration: docs/OPTIONAL_FEATURES.md.

## Acceptance

- [x] ADMIN/PRODUCTION_WORKER principal UI; existing roles/data/RBAC preserved.
- [x] Home/Queue/Problems/My Tasks plus SQL-paginated chronological all-order Feed.
- [x] Atomic claim starts production; produced → packed; shipment only from Ozon.
- [x] Simple shared problem/resolve with provenance, comment and human timeline.
- [x] Before-start cancellation red in Feed; after-start critical + Telegram.
- [x] Core Telegram problem/cancellation/integration error; no ordinary status spam.
- [x] Automatic webhook/reconciliation; current official tariff adapter connected.
- [x] Optional routes/jobs/queries/assets disabled; documented re-enabling.
- [x] SSE primary + one fallback; security/PWA/backup preserved.
- [x] Core loops/request counts/bundle/idle CPU/RSS/memory configuration checked.
- [x] PRODUCT/architecture/decisions/E2E documentation updated; history preserved.
- [x] Final full backend/Ruff/frontend lint/typecheck/build/E2E/diff checks recorded.

## Verification — 2026-10-02

- Full backend collection: 299 passed across two non-overlapping file groups
  (161 + 138), each in pytest file order. Existing deprecation warnings remain.
- Ruff app/tests/Alembic/scripts; frontend lint/typecheck/build: passed.
- Full core E2E: 12 passed, 0 failed, desktop/mobile, retries 0.
- git diff --check: passed. Runtime/request/bundle measurements: docs/PERFORMANCE.md.

Docker unavailable. Linux/PostgreSQL/Caddy/TLS/native restore/capacity and real
provider/physical-phone gates remain task 034; no live acceptance claim in 036.
