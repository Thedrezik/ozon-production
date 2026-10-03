# Optional features — task 036

Default: `ENABLED_OPTIONAL_FEATURES=` (empty). Set a comma-separated list in the
private backend env, restart the single backend process, reload the PWA. Settings
reject unknown names; authenticated `/api/features` exposes flags/timezone only.
Existing tables, rows, code and historical decisions remain intact.

| Flag | Disabled by default | Restore |
| --- | --- | --- |
| manager_tasks | API/UI, automatic source task creation and dashboard task queries | Add manager_tasks. Historical tasks remain; resolve obsolete historical sources explicitly. |
| procurement | API/UI and read-time overdue evaluation | Add procurement,manager_tasks. There is no independent procurement scheduler. |
| analytics | Historical, employee and workload API/UI/queries | Add analytics. Existing stage timestamps/history remain. Prevented money stays unavailable. |
| photos | Upload/read UI/API and image decoding | Add photos,advanced_workflow for retained order photo UI. Keep existing uploads volume/MIME/memory controls. |
| scanner | QR/camera/scanner UI/API | Add scanner,advanced_workflow. Files router is shared with photos; enable photos,scanner together for full legacy files UI. |
| bulk_actions | Bulk API and legacy selection/actions | Add bulk_actions,advanced_workflow; backend RBAC and confirmation remain. |
| notification_preferences | Granular preference API/UI, non-core notices and read-triggered deadline evaluation | Add notification_preferences. This restores explicit external opt-ins instead of mandatory linked-admin core Telegram. Deadline alerts still depend on reads/changes; no autonomous guarantee. |
| web_push | Subscription UI/API and lifespan delivery loop | Add web_push,notification_preferences; configure VAPID and opt in. Requires device/HTTPS verification. |
| key_expiration | Hourly credential expiry evaluator | Add key_expiration,notification_preferences; optionally manager_tasks. Supply manual expires_at. |
| advanced_workflow | Extra stages/editor and retained Orders controls | Add advanced_workflow with required flags. Full legacy Orders UI expects manager_tasks,procurement,photos,scanner,bulk_actions; enable that group together. |

Full extension test set:
`ENABLED_OPTIONAL_FEATURES=manager_tasks,procurement,analytics,photos,scanner,bulk_actions,notification_preferences,web_push,key_expiration,advanced_workflow`.
Backend legacy suites explicitly enable it; core tests/E2E force an empty set.
Do not change production flags for tests. Existing legacy roles/assignments stay;
new user UI focuses on ADMIN and PRODUCTION_WORKER, with bootstrap SUPER_ADMIN.

## Processes, queries and assets

Core lifespan owns Ozon inbox (5-second idle check, immediate drain), reconciliation
(startup + 900 seconds after completion) and configured Telegram delivery (15-second
bounded queue check/retry). No Web Push loop or hourly key-expiry loop by default.
No new deadline scheduler, Redis or Celery. Automatic Manager Tasks are gated;
core dashboard never evaluates procurement overdue or employee workload.

One SSE plus one shared 60-second fallback/clock refresh. Authenticated 20-second
SSE reconnect retains session/role checks, without another full-page open refresh.
An in-process epoch/revision checkpoint detects changes during the reconnect gap
or a backend restart: only a changed checkpoint invalidates data, without replay
storage or another polling timer. One worker remains a required deployment setting.
Focus/online/mutations also invalidate data; countdown is local. A normal screen
fetches sync-state + problem badge + its own API. Queue embeds active problems for
the actual page; no global latest-100 blockers query. Timeline loads on expansion
with SQL pages. No photo/preferences/analytics/procurement/tasks requests in core.

Optional frontend modules are lazy. Scanner has its own chunk; core PWA precache
excludes optional chunks. Restored extensions load them when opened online.
The static push handler stays inert without configured subscriptions.

## Preserved boundaries

No status enum or relationship deletion. Migration 0024 adds resolution provenance,
worker resolve permission and chronological index only. Security task 031,
one worker, pool 2+1 and memory caps remain. Telegram dedupe prevents repeated source
events; a crash between provider acceptance and DB commit may still redeliver.
Credential-client SELECT releases its DB slot before HTTP. Domain Ozon/Telegram
transactions may wait on providers: Linux pool/capacity checks remain task 034.
