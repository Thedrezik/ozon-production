# Task 040 — Native Debian Production Deployment Preparation

status: completed (preparation; live acceptance remains task 034 pending)

Задача 040 — Native Debian Production Deployment Preparation
Работай с локальным репозиторием:
 C:\Users\kdn14\Documents\GitHub\ozon-production
Прочитай:
- AGENTS.md 
- docs/PRODUCT.md 
- docs/STATE.md 
- docs/DECISIONS.md 
- docs/ARCHITECTURE.md 
- docs/DEPLOYMENT.md 
- docs/SECURITY.md 
- docs/PERFORMANCE.md 
- BACKUP_RESTORE.md 
-  материалы tasks 034 и 039. 
Архитектурное решение изменено:
Production VPS должен работать БЕЗ Docker.
Docker/Compose остаются допустимыми только для development/tests.
Production target:
-  Debian 12; 
-  x86_64; 
-  1 CPU; 
-  1 GB RAM; 
-  около 7 GB SSD; 
-  1 GiB swap; 
-  публичный IPv4; 
-  собственного платного домена нет; 
-  примерно 10 Ozon FBS заказов в день. 
Цель — сделать максимально лёгкий, надёжный native deployment.
Использовать непосредственно Debian services:
-  PostgreSQL из Debian/PostgreSQL packages; 
-  Python backend в отдельном virtualenv; 
-  один backend worker; 
-  systemd unit для backend; 
-  Caddy как systemd service; 
-  статически собранный React frontend; 
-  persistent uploads/backups в обычных каталогах Linux. 
Node/npm не должны требоваться постоянно в runtime, если frontend можно собрать при deploy/update.
Redis/Celery не добавлять.
Сравни существующий Docker deployment и native вариант по:
-  RAM; 
-  disk usage; 
-  idle processes; 
-  startup complexity; 
-  update/rollback complexity. 
Не придумывай точные цифры без измерений, но убери Docker-specific limits/config.
Цель — максимально разумно работать на 1 GB RAM / 7 GB disk.
PostgreSQL настроить консервативно для маленького VPS.
Сохранить:
-  1 backend worker; 
-  небольшой DB pool; 
-  1 GiB swap как аварийный запас. 
Переделай scripts/bootstrap-vps.sh под native deployment.
Он должен на чистом Debian 12:
-  проверить OS и architecture; 
-  обновить apt; 
-  установить PostgreSQL; 
-  Python/runtime/build dependencies; 
-  Node/npm только если нужны для build; 
-  Caddy; 
-  git; 
-  firewall tooling; 
-  необходимые системные утилиты; 
-  создать deploy user/app directories; 
-  создать 1 GiB swap при отсутствии swap; 
-  настроить минимальный firewall; 
-  НЕ устанавливать Docker. 
Скрипт должен быть idempotent настолько, насколько разумно.
Выбери простой production layout, например:
/opt/ozon-production
 /var/lib/ozon-production/uploads
 /var/lib/ozon-production/backups
 /etc/ozon-production/production.env
либо другой корректный Linux FHS-compatible вариант.
Secrets не должны храниться внутри git repository.
Permissions должны быть минимально необходимыми.
Подготовь systemd service:
ozon-production.service
Требования:
-  отдельный непривилегированный user; 
-  Python virtualenv; 
-  production env; 
-  один worker; 
-  restart on failure; 
-  sane timeouts; 
-  logs через journald; 
-  health/readiness; 
-  graceful restart. 
Не запускать приложение от root.
Подготовь:
-  отдельного DB user; 
-  отдельную DB; 
-  пароль только в private env; 
-  минимальные permissions; 
-  PostgreSQL listening only where required; 
-  разумные настройки памяти для 1 GB VPS; 
-  migrations через Alembic. 
Не открывать PostgreSQL в Internet.
Production frontend собрать один раз при deployment/update.
Caddy должен отдавать static files непосредственно.
Не держать Node dev server.
Сохрани решение task 039 для trusted HTTPS непосредственно на IPv4.
Переделай deployment под system-installed Caddy без контейнера.
Certificate renewal должен быть автоматическим.
Проверить:
-  HTTPS; 
-  redirect HTTP → HTTPS; 
-  SPA fallback; 
- /api reverse proxy; 
-  SSE; 
-  security headers; 
-  upload limits. 
Docker-specific backup/restore не должен требоваться для production.
Переделай production scripts под native:
- pg_dump; 
- pg_restore; 
-  uploads archive; 
-  retention; 
-  restore verification. 
Сохрани безопасный confirmation для destructive restore.
Обнови Linux backup/restore drill так, чтобы Docker не требовался.
Пользователь не хочет выполнять десятки команд вручную.
Подготовь максимально автоматизированные scripts:
- bootstrap-vps.sh 
- deploy-native.sh 
- update-native.sh 
- rollback-native.sh 
- backup.sh 
- restore.sh 
- smoke.sh 
Обычный update:
backup → git fetch/checkout release → install/update dependencies → frontend build → alembic upgrade → restart → smoke
При failure должна быть понятная процедура rollback.
Скрипты должны быть пригодны для выполнения coding-agent через SSH без ручных интерактивных prompts, кроме действий, где подтверждение действительно необходимо.
Для автоматизированного acceptance допускается отдельный явный --yes / --non-interactive flag.
Обычный destructive restore при ручном запуске должен требовать confirmation.
Deployment должен рассчитывать на:
-  SSH key authentication; 
-  временного или постоянного deploy user с sudo; 
-  отсутствие передачи root password в prompt/chat; 
-  возможность после deployment удалить временный ключ агента. 
Добавь раздел Agent SSH deployment в docs/DEPLOYMENT.md.
Опиши, как дать coding-agent доступ к VPS так, чтобы:
-  private key не коммитился; 
-  пароль не вставлялся в prompt; 
-  доступ можно было легко отозвать. 
Сохрани всё из task 039:
-  Admin вводит Client ID/API key; 
-  encrypted storage; 
-  read/minimal permissions; 
-  FBS import; 
-  webhook если bare-IP проходит Seller Check; 
-  reconciliation fallback; 
-  tariff data. 
Не возвращать Docker-зависимости.
С учётом ~7 GB SSD:
-  ограничить journald; 
-  document log retention; 
-  backup retention; 
-  очищать build artifacts/cache после успешного deployment; 
-  npm/pip caches не должны бесконтрольно копиться; 
-  не хранить старые releases бесконечно. 
Добавь команды проверки:
df -h
 du
 journalctl --disk-usage
Запусти:
-  backend tests; 
-  Ruff; 
-  frontend lint/typecheck/build; 
-  E2E; 
-  Bash syntax/tests; 
-  systemd unit validation насколько возможно; 
- git diff --check. 
Docker live validation больше не является production acceptance criterion.
Не выполнять реальный deployment без VPS.
Task 034 оставить pending.
 Commit/push не делать.
В финале сообщи:
-  какая теперь production architecture; 
-  что полностью убрано из Docker production; 
-  оценку плюсов/минусов native deployment; 
-  какие scripts готовы; 
-  сколько ручных действий останется пользователю; 
-  как безопасно дать coding-agent SSH access; 
-  первый шаг после аренды VPS.

## Preparation validation

- Native runtime/config/scripts and runbook implemented; production Compose removed.
- Full backend 315 passed; focused deployment 21 passed (9 new native checks).
- Ruff, frontend lint/typecheck/build, desktop/mobile E2E 12/12, shell syntax and
  synthetic failure/backup checks, Windows Caddy native config validation passed.
- Native systemd/PostgreSQL/restore and live IPv4 TLS/renewal are not run without
  VPS; task 034 remains pending. No deployment, commit or push.
