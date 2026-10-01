# Architecture Decisions

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
