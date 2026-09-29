# Task 034 — Production Deployment

status: pending  
complexity: HIGH  
recommended_model: GPT-6 Sol
reasoning: Medium

## Goal

Подготовить безопасный production deployment на VPS, не ломая существующий VPN.

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
- Не изменять существующий VPN без необходимости.
- Открывать только необходимые порты.
- Webhook должен быть доступен Ozon.
- Продумать доступ UI: публичный HTTPS с auth либо ограничение сетью, если это практически совместимо с телефонами работников.
- Persistent volumes для PostgreSQL, uploads, backups.
- Production env/secrets.
- Alembic migrations deployment flow.
- Health/readiness checks.
- Создать DEPLOYMENT.md.
- Добавить команды update/rollback на разумном уровне.

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
- [ ] VPN продолжает работать.
- [ ] Frontend/backend доступны по ожидаемому URL.
- [ ] Webhook route доступен извне.
- [ ] Persistent data переживает container restart.
- [ ] DEPLOYMENT.md создан.
- [ ] STATE.md обновлён.

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
