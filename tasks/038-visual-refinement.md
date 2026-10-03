# 038 — Visual Refinement / Premium UI Polish

Source: user's supplied task, 2026-10-03. Refine task 036/037 core as a complete
operational product. Preserve existing work, default-off extensions and task 034
pending. No deployment, commit or push.

Status: **completed**. Final-build E2E **12/12**, retries 0; visual/accessibility
review **75 states**, backend **30 tests**, lint/typecheck/build/Ruff/diff checks
passed. Initial gzip **89.25 → 91.24 kB**, no new dependencies.

## Concept and changes

A production workspace: deep navy first-order focus, calm light canvas, white
workspace and tinted context, restrained yellow brand accent. Desktop max-width
1280px, asymmetric two-column Home; compact single desktop shell. Mobile prioritizes
the complete first order/action, with four-item safe-area bottom navigation.

Home, Orders, chronological Feed, Problems and exact-order view use the shared
surfaces/buttons/typography. Ozon fresh/stale/error is a compact disclosure; real
errors remain prominent. Long product/problem text still expands. No icon,
animation or UI dependency. Native disclosures and 160ms feedback/reduced motion.

Focus gets real product/stage/assignee/problem/confirmed risk from the existing
Dashboard endpoint, with bounded enrichment, existing Decimal risk calculation
and finance permission. No domain workflow, schema, Ozon API or provider change.

## Acceptance

- Review 1440×1000, 1024×768 and 390×844: main screens, P0/exact order, long
  product/problem/comments, both cancellations, empty/loading/error, Ozon states,
  offline, accessibility/keyboard/touch/contrast/reduced-motion.
- Capture full-page and viewport screenshots in ignored
  `frontend/e2e-results/ui-review/task-038`; task 037 `after` retained for comparison.
- Frontend lint/typecheck/build; production-PWA E2E 12/12, retries 0; relevant
  backend dashboard/core/performance tests and Ruff; git diff --check.
- Bundle before/after and final results: DESIGN_SYSTEM.md, E2E.md, STATE.md.
- Optional features off; task 034 pending; no deployment/commit/push.

## Review corrections

Visual review caught excessive height at 1024×768 and an open profile covering
mobile offline controls; both corrected, with menu navigation/Escape/offline
regression assertions. First full E2E was 11/12: the worker auth GET received a
synthetic proxy 502. Local test proxy now uses dedicated upstream sockets instead
of reusing sockets near Uvicorn idle expiry, and logs transport error codes.
No retry, scenario skip or relaxed assertion was added. Extended visual review
explicitly returns Home after reload (the app restores the loaded queue by design).

## Main files

- `frontend/src/App.tsx`, `Dashboard.tsx`, `CoreOrders.tsx`, `OzonSyncStatus.tsx`,
  `OfflineQueue.tsx`, `style.css`: shell, composition, states and shared visual rules.
- `backend/app/api_dashboard.py`, `backend/tests/test_dashboard.py`: focus projection
  and operational/financial permission regression.
- `frontend/scripts/e2e/review-ui.mjs`, `helpers.mjs`: 75-state visual/accessibility
  review and dedicated mock-proxy upstream connections.
- `docs/DESIGN_SYSTEM.md`, `E2E.md`, `STATE.md`: design rules and verification.

## Final polish follow-up

2026-10-03: shared Home workspace/inset risk + production state, finished empty
state, stronger inline counters, 16px less mobile top space, smaller refresh,
combined profile/logout menu and restrained yellow interaction accents. New
white/yellow joinery logo in SVG/favicon and 192/512 PWA PNGs; matching theme colors.
No architecture/backend/business/workflow change or library.

Initial JS+CSS gzip 91.24 → 91.89 kB (+0.65 kB, 0.7%). Screenshots and direct
1440/390 comparisons: `frontend/e2e-results/ui-review/task-038-final`.
Visual/accessibility review 75/75 passed. The first full E2E had a parallel-fixture
startup failure: proxy requests reached the reserved port before its own Uvicorn
bind. Readiness now waits for that fixture's successful bind before checking health;
no retry, skipped scenario or relaxed assertion. Final E2E result: **12/12 passed**, desktop/mobile, retries 0. Lint/typecheck/build and diff check passed.

Additional files: `frontend/public/icon.svg`, `icon-192.png`, `icon-512.png`,
`frontend/index.html`, `frontend/vite.config.ts`; `helpers.mjs` readiness and
`run.mjs` logout navigation adapted to the user menu. No commit/push/deployment.
