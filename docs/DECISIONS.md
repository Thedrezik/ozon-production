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
