# Task 027 — Offline and Poor Network Support

status: pending  
complexity: HIGH  
recommended_model: GPT-5.6 Sol  
reasoning: High

## Goal

Сделать PWA устойчивой к кратковременной потере интернета в цеху.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Последняя загруженная очередь остаётся видимой offline.
- Показывать заметный OFFLINE indicator.
- Не показывать устаревшие данные как свежие.
- Оценить необходимость IndexedDB action queue.
- Если реализуется offline mutation queue — поддержать status actions с idempotency key.
- При конфликте не делать silent overwrite.
- После reconnect выполнить server refresh.
- Auth/security не ослаблять ради offline режима.

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

- [ ] Приложение открывается после кратковременной потери сети.
- [ ] Пользователь понимает, что данные offline.
- [ ] Reconnect восстанавливает актуальное состояние.
- [ ] Если offline mutations реализованы — они синхронизируются без duplicate.
- [ ] Conflict case протестирован.
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
