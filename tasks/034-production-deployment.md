# Task 034 — Production Deployment

status: pending  
complexity: HIGH  
recommended_model: GPT-6 Sol
reasoning: Medium

## Goal

Подготовить безопасный production deployment на отдельном VPS: 1 CPU / 1 GB RAM.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Проверить текущую deployment architecture.
- Caddy + HTTPS.
- Отдельный VPS; Caddy/backend/PostgreSQL на одном сервере.
- Сохранить один backend worker, небольшой pool и все существующие функции; lightweight review выполняется позднее отдельной задачей.
- Открывать только необходимые порты.
- Webhook должен быть доступен Ozon.
- Продумать доступ UI: публичный HTTPS с auth либо ограничение сетью, если это практически совместимо с телефонами работников.
- Persistent volumes для PostgreSQL, uploads, backups.
- Production env/secrets.
- Alembic migrations deployment flow.
- Health/readiness checks.
- Создать DEPLOYMENT.md.
- Добавить команды update/rollback на разумном уровне.
- До production launch выполнить на целевом Linux VPS полный destructive backup → modify → restore → verify drill через реальные `scripts/backup.sh` / `scripts/restore.sh` на synthetic данных в отдельном Compose project с уникальными PostgreSQL/uploads/backups volumes. Проверить resolved volume names до restore/cleanup: production volumes запрещены. Windows PowerShell/Git Bash/MSYS drill не заменяет эту проверку.
- Зафиксировать результат Linux drill в DEPLOYMENT.md и STATE.md: migrations, database.dump/uploads.tar.gz/README.txt и публикация в /data/backups; подтверждённое изменение DB/upload после backup; настоящий PostgreSQL restore; DB marker `before-backup`, исходный upload восстановлен, post-backup upload отсутствует; retention сохраняет последние архивы; cleanup удаляет только drill resources; production volumes остаются прежними. Сбой любого этапа блокирует production launch.

## General Constraints

- Не менять несвязанные части системы без необходимости.
- Не делать большой refactoring одновременно с реализацией задачи.
- Не добавлять тяжёлую инфраструктуру без доказанной необходимости.
- Учитывать VPS примерно 1 CPU / 1 GB RAM.
- Проверять permissions на backend.
- Все timestamps хранить в UTC.
- Денежные значения считать через Decimal/NUMERIC, не float.
- Не коммитить secrets.
- Не выводить secrets в logs.
- Важные изменения фиксировать в audit, если audit infrastructure уже существует.
- Если принимается новое существенное архитектурное решение — кратко записать его в `/docs/DECISIONS.md`.

## Acceptance Criteria

- [ ] Production compose запускается.
- [ ] HTTPS работает.
- [ ] На отдельном VPS 1 CPU / 1 GB RAM подтверждены resource limits, запас ОС/Docker, отсутствие OOM и приемлемая отзывчивость.
- [ ] Frontend/backend доступны по ожидаемому URL.
- [ ] Webhook route доступен извне.
- [ ] Persistent data переживает container restart.
- [ ] На целевом Linux VPS успешно выполнен и документирован полный isolated backup/restore drill из task 030 со всеми проверками выше; production volumes не затронуты. Обязательное условие перед production launch.
- [x] DEPLOYMENT.md создан.
- [x] STATE.md обновлён.

Implementation prepared 2026-10-02: standalone production Compose/env, explicit
update/migration/rollback operations, automated guarded Linux restore drill,
optional PostgreSQL/Caddy HTTPS mode for the existing E2E runner, deployment smoke
and runbook. Dedicated target: 1 CPU / 1 GB RAM, no functionality removal. Status
remains pending: Docker daemon/target VPS/public HTTPS are
unavailable to the agent. All runtime acceptance criteria above require actual
execution and evidence; see docs/DEPLOYMENT.md. No commit/push; task 035 not started.

## Completion

Перед завершением задачи:

1. Проверить все acceptance criteria.
2. Запустить связанные backend tests.
3. Запустить frontend tests/lint/typecheck, если задача затрагивает frontend.
4. Исправить обнаруженные ошибки.
5. Обновить `/docs/STATE.md`.
6. Изменить `status: pending` этого task на `status: completed`, если задача полностью закончена.

Финальный отчёт должен быть коротким:

- что реализовано;
- основные изменённые файлы;
- какие tests запущены;
- результат tests;
- оставшиеся проблемы, если есть.

Не печатать содержимое целых исходных файлов в финальном ответе.
