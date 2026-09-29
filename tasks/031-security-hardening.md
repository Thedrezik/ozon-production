# Task 031 — Security Hardening

status: pending  
complexity: HIGH  
recommended_model: GPT-6 Sol
reasoning: Medium

## Goal

Провести полноценный security review приложения перед production deployment.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Проверить auth/session/cookies.
- Проверить CSRF, если cookie auth.
- Проверить RBAC всех чувствительных endpoints.
- Проверить login rate limiting.
- Проверить security headers.
- Проверить CORS.
- Проверить file uploads.
- Проверить secret handling.
- Проверить SQL injection/XSS risk.
- Проверить admin endpoints.
- Проверить debug/docs exposure в production.
- Создать SECURITY.md.
- Исправить найденные критические и high issues.

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

- [ ] Нет известных critical/high security issues.
- [ ] Secrets не попадают frontend/logs.
- [ ] RBAC backend покрыт tests.
- [ ] Security headers включены.
- [ ] Upload validation существует.
- [ ] SECURITY.md создан.
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
