# Task 016 — Realtime Updates

status: pending  
complexity: MEDIUM  
recommended_model: GPT-5.6 Sol  
reasoning: Medium

## Goal

Сделать устойчивые realtime-обновления интерфейса без Redis и тяжёлой инфраструктуры.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Использовать SSE или WebSocket согласно ARCHITECTURE/DECISIONS.
- Single-instance backend должен работать без Redis.
- События: order created, status changed, assignment changed, blocker created/resolved, manager task changed.
- Frontend должен корректно восстанавливать соединение.
- После reconnect делать refresh/reconciliation клиентских данных.
- Не полагаться только на realtime transport как на единственный источник истины.

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

- [ ] Два браузера видят изменение статуса без ручного refresh.
- [ ] После потери соединения frontend reconnect-ится.
- [ ] Пропущенные события восстанавливаются обычным API refresh.
- [ ] Нет обязательной зависимости Redis.
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
