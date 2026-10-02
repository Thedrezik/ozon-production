# Security review — MVP / task 031

Reviewed 2026-10-02. This review covers the existing single-worker FastAPI + React
PWA deployment behind Caddy, with synthetic data and mocked external providers.
It is not a penetration-test certification. No known critical/high application
issues remain within the reviewed scope. Launch verification below is still required.

## Findings and fixes

| Finding | Resolution |
| --- | --- |
| Production accepted mock/dev settings and exposed API documentation | Fail startup on invalid production configuration; disable Swagger, ReDoc and OpenAPI in production; validate Host against public origin. |
| No application/edge security headers | API responses, including errors, use nosniff, DENY, no-referrer, restrictive CSP and no-store. Caddy covers the static PWA and adds Permissions-Policy and HTTPS-only HSTS. |
| Login limiter could be bypassed by rotating usernames or concurrent checks | Extend the existing limiter with atomic reservations and an aggregate socket-peer budget; bound its key count. Password-change guessing uses the same limiter. |
| Concurrent promotion/removal could race admin target protection or the last-super-admin guard | Lock the target user before reading roles for management; serialize super-admin removals on the existing Role row before counting active survivors. |
| Existing scrypt cost below current OWASP guidance | New hashes use N=32768, r=8, p=3 (32 MiB). Verify existing p=1 hashes and upgrade after successful login. Serialize hashing to bound memory on the small VPS. |
| Validation responses/startup errors could echo secrets | Return generic request-validation errors; hide settings inputs in validation messages and secrets in repr. |
| Transport/access logs could include Telegram token, push endpoint or query data | Disable transport/access logging, redact configured secrets and sensitive assignments in JSON logs/audit text; never serialize raw exceptions. |
| Unbounded JSON parsing and Telegram callback body | General mutation bodies capped at 256 KiB before parsing; Telegram additionally caps at 64 KiB. Image bodies retain the existing streamed limit. Caddy caps API requests at 21 MB. |
| Telegram link issued before deactivation could still be consumed | Recheck active user before binding, remove stale inactive link; retain hashed one-time code/expiry/transactional locking. |
| Continuous SSE events could prevent session reauthentication indefinitely | Absolute 20-second stream lifetime, independent of event traffic; reconnect runs existing auth/RBAC again. |
| Malformed non-ASCII cookie/CSRF/provider secret could cause a 500 | Fail closed before ASCII digest/constant-time comparison. |
| Vulnerable development tooling | Upgrade pip to >=26.2 and pytest to >=9.0.3. Runtime dependencies and frontend needed no upgrades. |

## Confirmed existing controls

- Opaque, random server-side sessions; only token digests are persisted. Cookies
  are host-only, HttpOnly, SameSite=Strict, Path=/api, with Secure in production,
  including logout deletion. Twelve-hour expiry is checked on each request.
  Logout deletes the current session; password reset, deactivation and role changes
  invalidate all affected sessions. Password change invalidates other sessions.
- Per-session constant-time CSRF validation on authenticated mutations. Browser
  mutations additionally enforce exact Origin and reject cross-site Fetch Metadata;
  login receives this protection too. Provider callbacks authenticate independently.
  Missing Origin is allowed for CLI/non-browser clients; it does not bypass CSRF.
- No cross-origin credentials/CORS policy is enabled; frontend/API share one origin.
  Backend permissions protect admin/settings/import/retry, user management, finance,
  audit and destructive actions. ADMIN cannot manage or grant SUPER_ADMIN; the
  last active super admin is guarded. Own-device push and Telegram controls are
  session-bound. Frontend visibility grants no authority.
- Ozon credentials remain backend-only, Fernet-encrypted in the existing singleton
  store, with safe metadata responses and real-client validation before rotation.
  No credentials/session/password/request bodies are included in audit snapshots.
  Audit remains append-only with ORM and PostgreSQL enforcement and audit.view.
- Ozon callbacks retain the existing source-network and seller-ID checks, durable
  inbox and replay protection. Caddy overwrites X-Ozon-Source-IP from its socket.
  Backend trusts it only from configured exact proxy addresses in production.
  Uvicorn ignores forwarded proxy headers; caller-supplied X-Forwarded-For cannot
  change auth/audit/limiter identity. No invented webhook signatures or API contracts.
- Telegram callbacks require a constant-time secret comparison; codes are random,
  hashed, private-chat-only, single-use and expire after ten minutes. Telegram
  delivery uses plain text, safe internal links and bounded retries.
- Push endpoints are HTTPS, validated against the existing provider hostname
  allowlist, with no arbitrary host/port/userinfo; P-256/auth keys are validated,
  subscriptions are owned by the session user, and delivery links are allowlisted.
- Uploads retain the existing declared-MIME/decoded-format checks, 10 MiB streamed
  cap, 20-million-pixel cap, serialized decoding, EXIF removal and JPEG re-encoding.
  SVG/HTML/forged images and decompression bombs are rejected; trailing active
  content is discarded. Authenticated reads use server-generated opaque keys;
  supplied filenames, traversal, Windows paths/streams and invalid persisted keys
  cannot expose files outside the upload root. No public static upload route.
- SQLAlchemy parameter binding is used for runtime queries/search; raw SQL is a
  fixed readiness SELECT. Migration-only interpolated identifiers come from a
  fixed local allowlist. SQL parameters are hidden in DB exceptions.
- React renders untrusted text without HTML injection; no dangerouslySetInnerHTML,
  dynamic HTML or eval path was found. Browser regression uses a real production
  build and malicious markup. CSP rejects inline scripts, objects and framing;
  style-src permits inline styles for existing UI styles, not scripts. Camera
  remains self-only; microphone/geolocation are disabled.
- PWA caches static shell assets only; API is NetworkOnly. Offline snapshots exclude
  secrets and auth state, expire after one hour, and clear on logout/auth rejection.
  Frontend build with backend-secret sentinels did not contain those values.

## Production launch / operator responsibility

1. Explicitly set APP_ENV=production, OZON_MOCK_MODE=false, DOMAIN to the real
   domain and APP_PUBLIC_URL to the matching HTTPS origin. Do not use .env.example
   unchanged. Production startup requires DOMAIN to equal APP_PUBLIC_URL's host
   and port; Compose also requires APP_ENV explicitly. Supply random APP_SECRET (32+ characters), PostgreSQL password
   (16+ characters), and a valid Fernet OZON_CREDENTIALS_MASTER_KEY. Startup rejects
   placeholders, mock mode, invalid environment names, insecure/public example
   origins and incomplete optional Telegram/VAPID configuration. APP_SECRET is
   retained as deployment configuration, not a second session/signing mechanism.
2. Keep .env, master/VAPID keys, bot tokens, DB dumps and uploads private. Back up
   the master key separately. Never enable HTTP/SQL debug logs or request-body
   logging; do not enter secrets into business text. Restrict operator/DB privileges.
   Old dormant p=1 password hashes upgrade on next login; reset unused accounts.
3. Publish only Caddy ports. Keep PostgreSQL/backend on the private Compose network;
   configure exact Caddy peer IP (/32 or /128) for Ozon callbacks. Do not insert a
   CDN/proxy without revisiting source validation. IP ingress protection is not
   cryptographic proof of Ozon identity. Recheck official source ranges when deploying.
4. Run one API worker/instance. In-process limits reset on restart. Behind Caddy,
   login sees the proxy peer: the aggregate 60 attempts/15 minutes is shared by
   users behind it; per-username limit is 5/15 minutes and clears on success.
   Tune only with measured production usage; no new distributed limiter is added.
5. On the target host run `docker compose up -d --build`, then
   `docker compose exec backend alembic upgrade head`, inspect `docker compose ps`,
   `/api/health`, `/api/health/ready`, HTTPS redirect/certificate, headers on success
   and errors, and absence of API docs, stack traces and credential leakage.
   Check backend Host against APP_PUBLIC_URL; direct health checks must use that Host.
   Validate Caddy configuration, PostgreSQL audit trigger and concurrent
   user-management row-lock behavior there (SQLite test DB does not enforce FOR UPDATE).
6. Repeat `npm audit`, Python `pip-audit` and `pip check` against the final deployment
   dependency set/image, keeping patched versions. A clean audit is a point-in-time
   advisory check, not a guarantee. Do not enable runtime debug mode.
7. Verify real Ozon webhook/reconciliation, Telegram and VAPID delivery, phone/PWA
   camera, SSE reconnect and isolated Linux backup/restore (mandatory task 034 gate).
   Rotate exposed secrets, invalidate affected sessions and use private operational
   channels to report a vulnerability; never attach real credentials to a report.

Docker and Caddy executables are unavailable in this review environment. Container
build, migrations, live PostgreSQL/Caddy headers and production debug-leak checks
must be performed at deployment. Local health/readiness, headers, production config,
error redaction, auth/RBAC and browser controls are covered by automated tests.

References: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[Caddy headers](https://caddyserver.com/docs/caddyfile/directives/header),
[Caddy body limits](https://caddyserver.com/docs/caddyfile/directives/request_body).

## Verification results

- Full backend suite passed twice: 245, then 250 tests. After final logging changes,
  focused security/audit/Ozon tests: 90 passed. After final user-management locking,
  auth/security/audit tests: 57 passed. Existing Starlette/httpx and Alembic
  deprecation warnings remain; no failed tests remain.
- Ruff app/tests/Alembic, Python compileall and git diff --check passed.
- Frontend lint, typecheck, production build, offline snapshot and push-worker tests
  passed. Headless Edge verified actual React XSS escaping, CSP inline-script
  rejection, PWA build loading and absence of backend-secret sentinel values.
- Final pip-audit: no known vulnerabilities; pip check: no broken requirements.
  Final npm audit: zero vulnerabilities across 530 dependencies. Python audit
  covered the installed 73-package runtime/dev/tooling environment. No major
  application upgrades; pytest's security fix required the dev-only 9.x migration.
