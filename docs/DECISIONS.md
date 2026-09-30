# Architecture Decisions

## 001 — Single VPS bootstrap

Use Docker Compose with one FastAPI worker, a small SQLAlchemy pool, PostgreSQL, and Caddy serving a static PWA. This fits the initial 1 CPU / 1 GB RAM target and avoids a broker or extra worker service. Migrations run explicitly, not concurrently at every API start. The bootstrap has no business tables or real Ozon integration; later tasks add these behind an Ozon client boundary.

## 002 — Server-side sessions and RBAC

Store random session token digests in PostgreSQL and send the token only in a Strict SameSite, HttpOnly cookie (`Secure` in production). Mutations require a per-session CSRF token. Recheck active status and permissions against the database on every request; role changes and deactivation revoke sessions. Use scrypt password hashing from Python's standard library, with a unique salt and fixed memory cost, as the secure Argon2id alternative. The single API worker applies an in-memory login limiter. A migration seeds the initial role and permission matrix; the first super admin is created interactively by CLI.
