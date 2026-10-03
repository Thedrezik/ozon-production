# Design system — task 038

Source of truth: `frontend/src/style.css`. Extend the existing Tailwind theme via
`@theme`; core classes consume the same variables. No extra UI framework, icon
pack, animation dependency or external font. Optional screens retain their code
and inherit the palette, radius, shadow, focus and input defaults.

## Palette and surfaces

| Purpose | Token / value | Use |
| --- | --- | --- |
| Canvas | slate-50 `#f3f5f8` | Neutral application background |
| Surface | `--surface`, white | Order rows, forms, compact panels |
| Focus workspace | `--surface-focus` `#173957` | First ranked order only; white text, `--focus-muted` metadata |
| Brand mark | `--brand-mark` `#f4c44e` | Focus eyebrow, selected nav underline and focus ring on dark surface |
| Brand hover | `--brand-surface` `#fff8e6` | Restrained warm hover and empty-state icon |
| Inset surface | slate-100 `#edf0f4` | Neutral badges and secondary content |
| Text | slate-900 `#202c3c` | Titles, identifiers, primary information |
| Muted text | slate-600 `#4c5b6d`, slate-500 `#596779` | Metadata, helper text |
| Separator | slate-200 `#dce1e8` | 1px borders; not the sole indicator of state |
| Accent | blue-800 `#193f69`, blue-50 `#eef3fb` | Primary action, selected navigation, work in progress |
| Success | `--success` `#256346`, surface `#eef7f1` | Produced, packed, shipped, save feedback |
| Warning | amber-800 `#76520b`, amber-50/100 | Ordinary production problem, risk, stale data |
| Danger | red-800 `#892c25`, red-50 `#fdf1f0` | Cancellation, critical problem, errors |

P0 is danger, P1 warning, P2 accent, P3/P4 neutral. Every status also has a
text label; production status and Ozon status remain separate. Ordinary problems
use amber; critical problems and cancellation use red. Cancellation before
production is a compact historical notice; after start has an explicit stop
message and the existing admin disposition action.

## Typography and scale

- System font stack only. Body 15px / 1.5. Inputs/textarea/select 16px to avoid
  mobile focus zoom. Service text and badges 13px, buttons/detail text 14px,
  order identifiers 16px, page headings 24px (22px mobile), focus title 22px (20px mobile), risk total 36px (28px mobile). Numeric values use tabular figures.
- Normal 400, product emphasis 500, actions/status emphasis 600, headings 650.
  No oversized KPI typography. Prices use grouped API Decimal strings through
  `format.ts`; no floating-point money calculation or guessed price/risk.
- Use Tailwind's existing 4px spacing base: 4/8/12/16/20/24/32px. Core cards
  have 16px padding (12px mobile), content gaps 8–16px. The desktop shell has a
  1280px maximum width; mobile padding respects all safe-area insets.
- Radius: 8px controls (`lg`), 10px buttons/insets (`xl`), 12px panels (`2xl`),
  5px badges. A single restrained `shadow-sm` separates white workspaces from the canvas. Inset context uses a tint; separators divide rows. Do not outline every element.

## Component principles

- Reuse `ui.tsx` button class, Loading, StatusBadge and four small inline SVG
  navigation icons. Helpers belong in `format.ts`, not a parallel component kit.
- Home uses a 1.7:1 desktop composition: one white workspace with a dark first-order focus and quiet following rows;
  risk and borderless production counts share a tinted inset on the right. Short desktop heights show two priorities. Mobile shows the
  focus first, before risk. No minimum-height filler panels or decorative charts.
- The focus shows actual product/article/quantity, stage, assignee, deadline,
  active problem and permission-gated confirmed risk; unknown money stays unknown.
  Its one action opens the exact order. Production mutations remain on the order.
- Dashboard enrichment uses the existing response: only the selected focus gets
  assignment/problems/risk. The risk uses the existing Decimal aggregation service;
  no per-card browser request, additional polling loop, new schema or permission.
- Four destinations belong to the desktop header: Главная, Заказы, Лента, Проблемы.
  Active navigation has a persistent underline; mobile keeps safe-area bottom
  navigation with a tinted selection and count. Profile and logout share one compact user disclosure; offline retains its
  existing direct logout alongside recovery controls. Profile closes on navigation/Escape (focus returns to its summary) and is unavailable offline so it cannot cover recovery controls. MOCK is a compact, labelled environment marker beside the brand.
- Ozon freshness occupies one disclosure row. Stale uses amber text/indicator;
  actual failure has a red edge/tint and announced error. Timestamp/error details
  expand on demand; fresh state stays neutral. Local work is still available.
- Buttons: navy primary only for production/form submission, neutral filled
  secondary for opening/resolving/search, ghost for refresh/navigation helpers,
  danger for production closure. Focus open is white on the dark workspace.
- Order cards: identifier/product → production status → deadline/risk → assignee
  and Ozon metadata → problem → primary permitted action. Priority reasons stay
  available in a disclosure. Feed has chronological receipt time, identifier,
  article/product, quantity, price and Ozon state without production controls.
- Desktop order rows group product/assignee and deadline/action in two columns.
  Feed uses aligned time → posting → product/price columns with thin separators;
  it stacks on phones. Cancellation has an accent edge and explicit label, with
  a stop message for critical cancellation.
- Exact-order pages omit search and have mobile sticky actions above bottom navigation. Search
  results and queue actions remain in their cards; avoid multiple sticky rows.
- Comments and problem/solution inputs are inline, labelled, bounded and preserve
  text on errors. Use a synchronous submission guard plus disabled feedback;
  whitespace-only comments/problems cannot submit. Autofocus new problem/solution
  inputs. Saved mutations restore keyboard focus to the order or workspace.
- Native disclosures keep keyboard/screen reader semantics. Human timeline is a
  compact chronological rail, with author/time and readable body; audit stays separate.
- Loading, empty, validation/error and save feedback occupy compact blocks. Keep
  loaded data during refresh; do not show an empty state before initial load.
  Existing offline snapshot/reconnect/auth restrictions remain unchanged.

## Accessibility and motion

Visible focus outline: 2px accent with 3px offset. Skip link targets the operational
workspace. Main actions and disclosures are at least 44px; mobile primary production
actions 48px, bottom navigation 56px. Names, labels and aria-current convey state.
Wrap long identifiers, names and multiline comments; no horizontal scrolling.
Long product/article and problem text use a native disclosure: compact preview in
lists, full untruncated content on expansion. Collapsed/expanded previews are not
shown together. The entire first mobile focus/action remains above bottom navigation with the
stale-sync fixture. Normal and error sync details remain keyboard accessible.

Only 160ms color/background/border transitions and 1px button press feedback.
Navigation/row hover and persistent selection use shared tokens; disclosures are
native and immediate. Save status, disabled/loading feedback and focus restoration
remain from task 037.
No pulse/glow, layout animation, animated loaders or animation-dependent tests.
`prefers-reduced-motion: reduce` disables transitions/animations. Browser review
checks normal-size text contrast ≥4.5:1 on visible shared component styles; this
is an accessibility smoke check, not a complete assistive-technology certification.

## Verification and bundle

Run `npm run lint`, `npm run typecheck`, `npm run test:e2e`, then
`node scripts/e2e/review-ui.mjs` in frontend. Review uses isolated real FastAPI/
SQLite/migrations and synthetic external providers at 1440×1000, 1024×768 and
390×844. Successful full-page/viewport screenshots and JSON live under ignored
`frontend/e2e-results/ui-review/task-038` (`UI_REVIEW_PHASE=task-038`); task 037 comparison captures remain in `after`, earlier baseline in `before`.
The review blocks SW to intercept deterministic loading/error states; the separate
12-case E2E verifies the actual generated PWA/service worker and offline recovery.
Physical mobile keyboard/notch/installation still need device acceptance in task 034.

Ozon integration, notifications and finance drill-down are lazy chunks. Admin
chunks join optional workflow/scanner chunks outside core PWA precache. No new
dependency; do not restore disabled task 036 extensions into the core path.

Task 037 historical measurement, 2026-10-02 (Vite reports rounded sizes):

| Artifact | Before | After |
| --- | ---: | ---: |
| Initial JS, gzip | 84.95 kB | 83.17 kB |
| CSS, gzip | 4.47 kB | 6.08 kB |
| Initial JS + CSS, gzip | 89.42 kB | 89.25 kB |
| Core precache, uncompressed | 300.12 KiB | 294.73 KiB |

Lint/typecheck/build/Ruff/diff checks passed; final actual PWA E2E 12/12, no retries.
Separate review: 57 states across the three viewports with screenshots and checks
described above. No backend/domain change or new dependency in task 037.

## Task 038 measurements

2026-10-03, same local toolchain, initial entry only (Vite rounded decimal kB):
JS gzip 83.17 → 83.82; CSS gzip 6.08 → 7.42; combined 89.25 → 91.24
(+1.99 kB, about 2.2%). Core precache 294.73 → 304.29 KiB uncompressed.
No dependency added. Four existing inline SVG icons retained. Optional/admin lazy
chunks and precache exclusions remain unchanged. CSS replaces the old shell/home
rules instead of adding an overriding parallel theme. Device acceptance remains 034.

Final verification: 75 visual/accessibility states, 12/12 actual PWA E2E (retries 0),
30 dashboard/core/performance backend tests; lint/typecheck/build/Ruff/diff passed.

## Final polish follow-up, 2026-10-03

One shared Home surface connects priorities, risk and production counts. Empty
Home has a small queue/check icon, clear heading, useful next step and queue action.
Counts use aligned tabular values and small semantic accents, without KPI cards.
Mobile header is 52px; sync spacing is tighter, moving the first focus upward 16px.
Refresh is a smaller 12px ghost control with the existing 44px hit area.

New vector brand mark: two opposing joinery corners, white/yellow on navy. Source
`frontend/public/icon.svg`; 192/512px antialiased PNGs serve the PWA. No external
font, raster generation service or new dependency. Theme metadata matches tokens.

This pass: initial gzip JS 83.82 → 83.99 kB, CSS 7.42 → 7.90 kB, combined
91.24 → 91.89 kB (+0.65 kB, 0.7%). Core precache 304.29 → 307.72 KiB.
Visual comparison/captures: `frontend/e2e-results/ui-review/task-038-final`;
`comparison-1440.png` and `comparison-390.png` compare the preceding result.
