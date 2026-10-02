# Task 035 — Pre-deployment final review

Дата: 2026-10-02. Локальный checkout, включая уже подготовленные изменения task 034.
Review выполнен до аренды VPS; это **не production acceptance**. Task 034 остаётся
`pending`. Deployment, commit/push, удаление функций и task 036 не выполнялись.

## Вывод

Основной MVP работает: очередь → назначение → производство → blocker → Manager Task
и in-app notification → закупка → подтверждение решения → упаковка → READY_TO_SHIP.
Но **полного соответствия PRODUCT.md пока нет**. Самые существенные пробелы —
реальная тарификация/Money at Risk, независимые от открытого UI deadline alerts и
часть автоматических Manager Tasks. Есть ограничения рабочего UI и списков.
Запуск на 1 CPU / 1 GB — целевая конфигурация, ещё не измеренная гарантия.

Прочитаны PRODUCT, STATE, DECISIONS, ARCHITECTURE, PERFORMANCE, E2E, DEPLOYMENT,
BACKUP_RESTORE и task 035. Запрошенный `docs/SECURITY.md` отсутствует: актуальный
security review находится в [../SECURITY.md](../SECURITY.md). ARCHITECTURE содержит
bootstrap/future формулировки, которые уже не описывают реализованные интеграции.
Требования сверялись с исходниками, callers и тестами, а не со статусами tasks.

## 1. Blocking before production

**B1. Реальные Ozon тарифы не подключены к финансовым engines.**
`ozon_import.upsert_posting` сохраняет `tariffication/tariffication_steps` в
`OzonPostingData`, но не заполняет нормализованный `Order.tariff_steps`.
`tariff.parse_normalized_steps` принимает внутренний формат, а не Seller API.
На mock подписанных стоимостях работают timeline, delta и risk; на реальном импорте
этого недостаточно для требований PRODUCT §§5–7, 19, 66. Это не только live smoke:
нужен проверенный adapter или явное согласование версии с неизвестными суммами.
Не вычислять деньги из цены заказа или неподтверждённого знака discount.
Исправленный в этом review unknown indicator предотвращает ложное впечатление
«риск точно нулевой», но не реализует adapter.

**B2. Прохождение времени само по себе не создаёт deadline notifications.**
[notifications.py](../backend/app/notifications.py), `sync_deadline_notifications`,
вызывается из GET центра уведомлений менеджера и `ozon_webhook.refresh_projections`
при изменённых postings. При закрытом UI и неизменном upstream posting приближение
срока не создаёт notice/delivery; существующие Push/Telegram loops лишь доставляют
уже созданные записи. Аналогично overdue procurement эскалирует при чтении страниц
или записи, а не независимо от активности пользователя. Для обещания «срочное
нельзя пропустить» требуется согласовать один ограниченный периодический evaluator
либо явно принять ручной контроль. Не добавлять отдельный scheduler для каждого правила.

**B3. Открыты launch gates task 034.** Полный target Linux restore, production
PostgreSQL/Caddy/HTTPS/security/persistence/capacity не проверены. Подготовленные
скрипты не заменяют успешный runtime. Конкретные проверки — раздел 5 ниже и
[DEPLOYMENT.md](DEPLOYMENT.md). Они отложены по указанию пользователя; task 035
может завершиться, но production запуск до этих проверок не подтверждён.

## 2. Should fix before production

| ID | Наблюдение и влияние | Основание / требуемое решение |
| --- | --- | --- |
| S1 | `DEADLINE_RISK`, `STALLED_ORDER`, `UNASSIGNED_ORDER` существуют как source types и UI filters, но нет callers, вычисляющих эти причины. Нет отдельного автоматического task для просрочки/дорогого заказа у дедлайна. | `manager_tasks.py`, поиск callers `ensure_task/sync_rule`; PRODUCT и AGENTS. Нужны пороги, дедупликация, повторный эпизод и автоматическое закрытие либо явно уменьшенное ТЗ. |
| S2 | Worker имеет `comments.create`, но `OrderTimeline` с формой комментария скрыт через `!shopWorker`. В worker UI нельзя оставить обычный комментарий; остаются blocker и фото. | `frontend/src/Orders.tsx`, конец карточки. Восстановить короткую форму комментария без административной истории; решение UI отдельно от review. |
| S3 | «Проблема» недоступна в PRODUCED/PACKING; нет перехода из этих стадий в BLOCKED и возврата в PACKING. Не хватает упаковки — штатный blocker type, но упаковщик не может оформить его на стадии упаковки. | `api_blockers.BLOCKABLE`, `orders.TRANSITIONS`, `Orders.actions`. Согласовать стадии, из которых разрешается блокировать/возобновлять работу. |
| S4 | Queue загружает только последние 100 blockers глобально, затем фильтрует их по карточке. Старый активный blocker может отсутствовать; exact order lookup не устраняет лимит. История UI берёт первые 100 событий и игнорирует total/offset; новые комментарии длинной истории не видны. Notifications UI показывает первые 50 без перехода на следующую страницу. | `Orders.refresh`, `OrderTimeline.refresh`, `Notifications.tsx`; APIs имеют pagination. Нужны выборка blockers для показанных заказов и доступ к остальным событиям/уведомлениям. |
| S5 | «Следующая задача» проверяет первые 100 orders, а не всю очередь; допустимость claim проверяется шире backend contract: unassigned IN_PRODUCTION/PRODUCED/PACKING может быть выбран, затем claim вернёт 409. Следующая подходящая задача за первой сотней не найдётся. | `Orders.nextTask`, `api_orders.claim`. Определить единый eligibility contract и получать первый подходящий заказ с backend. |
| S6 | Карточка не показывает отдельный внешний Ozon status, SKU/offer_id, цену изделия и order number; эти требования не закрываются одним raw JSON в БД. Deadline/reasons — снимок, секундного countdown нет. Большинство дат используют timezone браузера, только Money at Risk явно использует timezone организации. | `api_orders.order_data`, `Orders.tsx`, `App.tsx`, PRODUCT §§18, 31, 41, 66. Раскрывать цену только по finance permission; timezone нужен общий для UI. |
| S7 | Production workload показывает число active orders, не сумму нормативных минут. Dashboard не показывает unassigned и сегодняшние NEW/PRODUCED/READY counters; throughput и средние доступны отдельно в Analytics. | `api_dashboard`, `Dashboard`, `api_analytics`; PRODUCT §§19, 62. Нужен компактный рабочий набор показателей, не дополнительный BI экран. |
| S8 | Внешний HTTP выполняется с открытыми DB transactions: `ManagedOzonClient._call` держит credential SELECT connection; import/reconciliation — свою; Push и Telegram держат batch/row locks до окончания сетевых отправок. Pool 2+1 и timeout 3 s делают одновременную медленную доставку риском голодания API. Graceful shutdown ждёт loops; Push batch может превысить production stop grace 40 s. | `ozon_credentials.py:45`, `web_push.deliver_pending`, `telegram.deliver_pending`, `main.lifespan`. Измерить slow providers + оба канала + reconciliation на PostgreSQL; при подтверждении сократить время удержания соединений, сохранив receipts/claim semantics. Не увеличивать pool вслепую. |
| S9 | Locks защищают claim и транзакционную целостность, но нет expected-version для назначения, приоритета, metadata задач. Последовательно обработанный stale PUT может заменить более новое решение; не все конфликты заканчиваются 409. | `api_orders.assign/set_priority_override`, модели без version, PRODUCT §58. Согласовать optimistic concurrency для ключевых изменений; SQLite E2E deterministic claim barrier не доказывает все races. |
| S10 | Нет UI/API создания кастомных ролей и изменения набора permissions. Permissions модели и backend проверки существуют, `/roles` только читает названия. Priority weights/суммовые пороги настраиваются, временные 120/480/1440/2880 минут — hardcoded. | `api_auth.py`, `rbac.py`, `priority.evaluate`; PRODUCT §§7,22. Выбрать фиксированный MVP policy либо реализовать admin configuration. |
| S11 | Закупка DELIVERED не закрывает blocker: работник/менеджер подтверждает решение отдельно. Это осознанное решение 008, но буквальный acceptance PRODUCT говорит «после покупки blocker закрывается». Blocker и его Manager Task могут иметь разных assignees или остаться без assignee. | `api_procurement.update`, DECISIONS 008, `api_blockers.create_blocker`. Предпочтительно сохранить ручное подтверждение фактического устранения, но закрепить это в продуктовом сценарии и ответственности. |
| S12 | Частичное изменение товаров записывается в raw/snapshot и заменяет items; readable change timeline отслеживает statuses/dates, не изменения SKU/quantity. Отдельного actionable alert о частичном изменении состава после начала производства нет. | `ozon_import.upsert_posting`, `ozon_webhook.apply_posting`. Уточнить требуемый alert для уже запущенного изделия; full cancellation покрыта. |
| S13 | Документы и legacy verification routes местами противоречат текущему состоянию: bootstrap ARCHITECTURE, «task 035 не начата» в DEPLOYMENT, старое STATE запрещало review до VPS. Expiration reminders работают только после сохранения credential row, не для одних env credentials. | Привести entrypoint docs после продуктовых решений; для запуска сохранить/проверить ключ через Integration UI и вручную задать expiry. |

Эти пункты — конкретные ограничения/пробелы для решения пользователя. Крупные
workflow/RBAC/UI/alert подсистемы в task 035 не перестраивались. Полное PRODUCT
нельзя объявить выполненным, ссылаясь на completed предыдущих tasks.

## 3. Can simplify/remove

Ниже **кандидаты**, а не уже отключённые функции. Эффект на RAM/CPU не измерен;
известны структура обращений и локальные сравнительные benchmarks.

| Функция / механизм: что делает | Польза основному workflow | Ресурсы и сложность | Последствие отключения / упрощения |
| --- | --- | --- | --- |
| Несколько refresh triggers: auth check каждые 30 s, 60 s refresh, SSE open/events, focus/online; SSE reconnect максимум через 20 s. | Realtime и auth recovery нужны; одновременные повторные полные reads мало добавляют. | `App.check` всегда setUser новым объектом и refreshToken; user dependency пересоздаёт EventSource. Каждый refresh запускает активный экран + sync banner; риск/очередь O(active). | Объединить/coalesce refresh, сохранить обязательную session revalidation и один recovery timer. Меньше запросов; чрезмерное урежение ухудшит freshness/revocation. Простое отключение SSE даст лишь polling и потерю мгновенного обновления. |
| Eager photo/history/QR на каждой карточке даже при закрытых details. | Фото/история/QR полезны при конкретной проблеме; редко нужны сразу для 20 карточек. | Photos и manager timeline делают GET на mount; QR img имеет src без lazy/open guard. Дополнительные requests, auth SQL, decode/DOM; фото комментариев создают дополнительные компоненты. | Lazy загрузка при раскрытии сохранит функции и сократит HTTP fan-out. Полное удаление фото лишит доказательств брака; QR можно скрыть, если ярлыки не используются. |
| Analytics: intervals, throughput, SKU/employee aggregates. | Полезна руководителю периодически, редко отвечает на «что делать сейчас». | ~20 SQL queries локально, без background aggregation и отдельного сервиса. Сейчас active screen обновляется на каждый общий refresh, даже для выбранного исторического периода. | Ручное refresh/optional menu снизит ненужные reads. Скрыть экран можно; runtime loops это не выключит, потому что отдельного analytics job нет. Не удалять status timestamps/history. |
| Telegram delivery и account linking. | Дополнительный канал; может быть лишним при устойчивом Push. | Bot/token/webhook/link lifecycle, HTTP каждые 15 s при настройке, batch locks/retries и delivery rows. | Пустая полная Telegram env группа не запускает delivery loop. In-app/производство сохраняются, Telegram отсутствует; выключить preferences, иначе pending rows остаются. Уже отдельный optional adapter, не второй notification engine. |
| Web Push delivery и device subscriptions. | Полезен при закрытой PWA, особенно для критических blockers; не заменяет UI. | VAPID, provider retries, subscriptions/receipts, per-device fan-out, 15 s loop при настройке. | Пустая VAPID группа отключает delivery loop; теряются OS alerts. Сохранить хотя бы один проверенный внешний канал по рабочему процессу; in-app виден только при открытом приложении. |
| Durable webhook worker polling: каждые 0.5 s в idle, 0.05 s после работы. | Inbox/restart/retries нужны для надёжного быстрого импорта. | При отсутствии contention до ~2 inbox SELECT/s (≈172800/сутки); shared posting lock задерживает poll во время reconciliation. Нет отдельного broker/service. | Adaptive idle wait/wakeup может снизить idle SQL. Полное `OZON_WEBHOOK_ENABLED=false` отключает receiver/worker: новые данные приходят через reconciliation и теряется seconds-level обещание. Не рекомендуем удалять inbox/idempotency. |
| Reconciliation rolling 30-day list каждые 240 s + get отсутствующих nonterminal postings. | Обязательная страховка от пропущенного webhook; это не дубль, который можно безопасно удалить. | Sequential API calls, all-page transaction, seen set, shared lock; long runs задерживают webhook processing. | Можно настроить window/interval после измерения. Полное отключение оставит пропущенные/изменённые postings до ручного импорта; для production не рекомендуется. |
| Hourly credential expiry loop, даже если credential row пока отсутствует. | Высокая польза при реальном ключе; без ключа — одна почти пустая проверка. | Один SELECT/час и простая lifespan task. Практически не является главным потребителем. | Conditional startup/skip даст минимальную экономию; без него срок ключа придётся контролировать вручную. Удалять ради 1 GB не обосновано. |

Двойные записи semantic audit + structured snapshots, status_history и readable
timeline имеют разные назначения (проверяемый audit, этапы, рабочая история).
Это дополнительная запись/диск, но не две независимые бизнес-системы. Удаление
audit/history не предлагается. Исторические Windows drill и специализированные
browser runners добавляют maintenance, не production RAM; после Linux acceptance
можно определить один авторитетный путь и оставить остальные диагностическими.

## 4. Optional / future

- Production grouping похожих offer_id (§16) отсутствует; postings нельзя сливать.
  Production group пока атрибут профиля, не назначаемая команда (§59).
- Полностью configurable workflow с пользовательскими codes/transitions — future
  по PRODUCT §9; сейчас меняются labels/order, бизнес-переходы фиксированы.
- `@mentions` сохраняются backend, в UI нет выбора/уведомления mentioned user;
  PRODUCT допускает «по возможности».
- Initial setup wizard — желательный, не обязательный. CLI admin + инструкции и
  Integration UI уже есть. Настройка organization timezone — env, не settings UI.
- Подтверждённые исторические «сэкономлено/предотвращённые потери» отсутствуют.
  Analytics честно возвращает unavailable; текущий risk нельзя записывать как savings.
- Расширенный BI/export, MES scheduler, BOM/material stock, несколько кабинетов/
  цехов/маркетплейсов, native app, S3/MinIO, offline mutation queue — не реализованы
  и не нужны для первого запуска. LocalStorage adapter заменяем, originals не хранятся.
- Read-only offline: одна страница, один час, одна вкладка. Новое открытие PWA
  без сети/снимка не восстанавливает очередь. Это осознанная безопасная граница,
  а не реализованная offline работа со status actions.
- Политика retention для webhook inbox, expired sessions, delivered notifications,
  raw customer data и orphan photos пока отсутствует. Планировать по диску/приватности,
  не вводить purge audit/order history ради произвольной экономии.
- Физические HEIC/HEIF и специфические форматы документов не поддержаны; storage
  API реализован для JPEG/PNG/WebP, а не произвольных attachments.
- FastAPI OpenAPI доступен dev/test, в production выключен целиком, admin-only docs
  route нет. Можно оставить отключённым ради меньшей поверхности атаки.

## 5. Requires real VPS validation

После финальных продуктовых решений продолжить существующую task 034:

1. **Linux/Docker/release:** preflight, реальные Compose config/build images вне
   live 1 GB host, migrations head `0023_performance`, startup/restart persistence,
   failure stops writers, actual image digests/SHA, ports/firewall, safe update/rollback.
2. **Backup/restore:** synthetic target Linux backup → изменить DB/uploads → restore
   → проверить original/new row/file, retention, cleanup и preservation всех прежних
   volumes. Проверить cron/systemd, ненулевой exit alert, off-host encrypted copy и
   отдельное хранение master key. DB/uploads не имеют общей атомарной транзакции;
   `pg_restore --clean` не удаляет объекты вне dump. Failed backup оставляет API stopped.
3. **HTTPS/security:** публичный ACME/TLS, headers/errors, Secure/HttpOnly/Strict cookies,
   CSRF/Origin/Host, отсутствие docs/secrets/leaks, source-IP overwrite и exact Caddy
   peer trust, PostgreSQL audit UPDATE/DELETE/TRUNCATE trigger и user-management locks.
4. **Capacity:** RAM caps 256+384+96 = 736 MiB — не фактическое потребление. Host reserve
   около 218 MiB для decimal 1 GB либо 288 MiB для 1 GiB до overhead. Измерить host/
   cgroup RSS/CPU/swap/OOM/restarts, p95 при заявленной active cardinality/users, pool
   exhaustion и recovery. Одновременно queue/dashboard/risk, несколько SSE, PNG/WebP
   uploads, reconciliation и медленные providers. Не строить images/браузеры на live VPS.
5. **PostgreSQL:** планы фактических SQL (EXPLAIN ANALYZE BUFFERS на synthetic DB),
   pagination/search selectivity, сортировки/spill, concurrency/locks/uniqueness,
   idle transactions и starvation pool. SQLite не подтверждает production FOR UPDATE.
6. **E2E:** isolated PostgreSQL/backend/Caddy HTTPS desktop/mobile 12/12. Local CA/test
   cookies/source relaxation runner не доказывает unmodified public production security.
7. **Providers:** проверить текущую официальную Ozon документацию/source ranges,
   permissions FBS, реальные import/ping/webhook/replay/cancellation/reconciliation
   recovery; корректность tariff source отдельно от доступности API. Для выбранных
   optional каналов — реальная доставка/deep link/retry/expired subscription.
8. **Физический телефон:** PWA install/update/offline/reconnect, камера и QR/штрихкод,
   real JPEG/PNG/WebP и decoder RSS, OS Push permission/receipt, отказ разрешений,
   сценарий работника/упаковщика, скорость действий и читаемость в цеху.

Документация Ozon проверялась проектом 2026-10-01. Повторный запрос review
2026-10-02 к официальным [FBS list](https://docs.ozon.ru/api/seller/#operation/PostingFbsList)
и [push contract](https://docs.ozon.ru/api/seller/#tag/push_start) получил redirect loop.
Новая успешная независимая проверка актуальности здесь **не заявляется**. Endpoints/
поля/суммы не менялись по догадке; локальные contract tests используют mock только.

## Матрица PRODUCT.md → реализация

| Область | Фактически реализовано / граница | Код и проверки |
| --- | --- | --- |
| Production workflow / statuses | Все 12 codes, timestamps/history, guarded transitions; labels/order editable. Custom transitions future. | `orders.py`, `api_orders.py`, test_orders, E2E workflow; S3/S9 |
| Queue / assignment / worker | Exact ranked pagination, mine, claim/user/unassigned, large buttons; group assignment отсутствует. | `performance.py`, `api_orders.py`, Orders; S2/S4/S5 |
| Blockers / Manager Tasks | Transactional task+notice, source unique key, last blocker restores stage, task auto resolves. Automatic sources реализованы частично. | api_blockers, manager_tasks, test_blockers/test_manager_tasks; S1 |
| Procurement | Decimal quantity, order/blocker links, lifecycle/history/responsible, overdue high/critical task; manual blocker confirmation. | api_procurement/procurement, tests/E2E; B2/S11 |
| Normatives / Priority | Offer-first/SKU fallback, quantity, production+packing, deadlines, money/value, feasibility, blocked/manual/pin reasons; configurable weights. | api_product_profiles, priority, test_priority/profiles; S10 |
| Tariff / Money at Risk | Decimal normalized timeline, disjoint high-water increments, categories, as_of drill-down; real adapter отсутствует. | tariff/money_at_risk, tests, E2E 470 RUB mock; B1 |
| Manager dashboard | Critical/blocked/ready/overdue, tasks, workload, clickable risk buckets; компактный, не полный §19. | api_dashboard/Dashboard, tests; S7 |
| Search / filters / bulk | Posting/order/SKU/offer/name search, statuses/worker/blocked/ready/overdue/warehouse, P0–P4 после fix; atomic RBAC bulk+confirm+audit. today explicit filter отсутствует. | api_orders/Orders, test_orders/performance, E2E |
| Realtime | One single-worker bounded SSE bus, after-commit invalidation, auth reconnect/fallback; non-order side effects не все публикуют SSE (credential expiry/rotation, responsible procurement). | main/order_events/api_orders, App; test_performance/E2E; §3 |
| Notifications / Push / Telegram | One NotificationDelivery queue, per-type/channel prefs, mandatory admin in-app, optional external adapters/retries/receipts/binding. only-own/only-critical/global mandatory config отсутствуют; отдельного OZON_WEBHOOK_ERROR type нет, ошибки идут OZON_SYNC_ERROR. | notifications/web_push/telegram, tests; B2 |
| Ozon client / FBS import | v4 cursor list, v3 get, roles check, bounded retries/429, Decimal parse, raw snapshot, external-only upsert. Raw хранит дополнительные upstream поля, UI/typed columns только subset §5. | ozon/ozon_import, tests; docs/OZON_API |
| Webhook / reconciliation | Durable bounded inbox, source/seller validation, idempotency, retries, source tasks, rolling discovery + get backfill, one shared lock. Historic discovery вручную. | ozon_webhook/ozon_reconciliation, tests/E2E; B2/S8 |
| Cancellation / changes | Full external cancellation separate, archive, assigned-worker/manager alert and critical task after start; date/status history. Item composition alert gap. | test_ozon_changes/webhook/reconciliation; S12 |
| Credentials | Backend encrypted singleton, verified rotation, env bootstrap, fail closed master key, manual expiry 14/7/3/1 reminders. | ozon_credentials/api_ozon_credentials, tests; S13 |
| Photos / files / QR | Private compressed JPEG, MIME/size/pixels/EXIF guards, opaque storage, order/blocker/comment links, QR/camera decoder/manual lookup. HEIC/general files отсутствуют. | photos/storage/api_files/Files, test_files/E2E; physical gate |
| Offline PWA | Static shell NetworkOnly API, manifest/icons/autoUpdate, bounded sessionStorage projection, stale read-only, no auth/deferred mutations, cleanup/reconnect. | offline/OfflineQueue/vite config, tests/E2E |
| Analytics / audit | Bounded SQL aggregates/current workload, append-only transactional audit allowlists plus PG trigger; no financial savings guess. | api_analytics/audit/api_audit, tests; real PG gate |
| Auth / RBAC / security | HttpOnly sessions/CSRF, scrypt, rate limits, active role enforcement, admin guards, production validation/redaction/headers. Custom roles UI/API gap. | auth/api_auth/rbac/security/config, test_auth/security/audit; S9/S10 |
| Backup / deployment | Consistent stopped-writer bundle, retention, guarded restore/drill, explicit immutable release flow/private env, public-only Caddy. Schedule/off-host/run success operator gates. | scripts, production Compose, test_deployment_tools; B3 |
| Performance / E2E | One worker/pool2+1, batched exact rank/risk, indexes/upload caps; 12 real-app local scenarios. Tests are SQLite/Edge, not target hardware. | PERFORMANCE/E2E, test_performance and browser suite; §5 |

## Исправленные подтверждённые дефекты

1. **Отмена Ozon + blocker:** закрытие последнего blocker пыталось вернуть production
   status и падало с ValueError/500. Теперь closure/task resolution коммитятся,
   внутренний BLOCKED остаётся до решения менеджера; новый blocker на cancelled
   posting получает 409. Regression для RESOLVED и CANCELLED.
2. **RBAC financial leak:** PUT priority возвращал `financial_impact` и денежные
   reasons без `finance.view`. Общий response projector используется для queue
   и PUT; custom permission combination regression подтверждает redaction и
   сохранение денег для finance actor.
3. **P4:** queue API отвергал валидный priority level, UI filter его не предлагал.
   Теперь все LEVELS допустимы, dropdown содержит P4; regression exact filtering.
4. **Неизвестный risk:** postings без normalized steps выпадали из unpriced count.
   При real import могло быть `0 ₽ / unknown=0`. Теперь missing timelines считаются
   SQL count без загрузки всех unpriced orders, dashboard показывает предупреждение;
   empty timelines учитываются aggregate. Regression summary/dashboard.

Новых сервисов/jobs/schema, adapters и изменений бизнес-политики не добавлено.
Основные исходники изменены только для этих дефектов. Упрощения выше не применены.

## Проверки

- Baseline: backend **275 passed**, E2E **12/12**, без retries.
- После fixes: focused blockers/priority/Ozon changes **17 passed**;
  risk/dashboard/performance **16 passed**. Новые regressions воспроизводили дефекты
  до исправлений (отдельно исправлена опечатка имени permission в тестовой setup).
- Финальный backend **279 passed**, 8 существующих deprecation warnings.
  Ruff app/tests/Alembic/deployment scripts, frontend lint/typecheck/build прошли;
  финальный E2E **12/12** без retries, offline snapshot/privacy/expiry/NetworkOnly
  tests прошли. `git diff --check` прошёл.
- Linux/Docker/PostgreSQL/public HTTPS/native restore/providers/physical devices:
  **NOT RUN**, отложены в task 034. Sandbox build initially failed на чтении
  parent directory; разрешённый повтор собрал тот же исходный проект успешно.

## Acceptance task 035

Локальный production сценарий, blockers/tasks/in-app notification, финансовый
drill-down на подтверждённых mock costs, migrations/tests и deployment documentation
проверены. Полное PRODUCT compliance и live backup/restore/production acceptance
не заявляются: оставшиеся blockers перечислены выше. Review завершён как
**pre-deployment final review** по изменённому порядку пользователя. Следующая
крупная задача не создавалась; решения о функциях остаются за пользователем.
