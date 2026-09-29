# Task 032 — Performance for Small VPS

status: pending  
complexity: HIGH  
recommended_model: GPT-6 Sol
reasoning: Medium

## Goal

Оптимизировать приложение для реального VPS около 1 CPU / 1 GB RAM.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Проверить Docker memory footprint.
- Ограничить PostgreSQL resources разумными настройками.
- Использовать один backend worker, если profiling не показывает обратного.
- Проверить DB connection pool.
- Найти N+1 queries.
- Проверить индексы на основных списках.
- Проверить pagination.
- Не загружать огромную историю заказов без необходимости.
- Проверить memory usage frontend build/runtime services.
- Не вводить Redis/cache без измеренной необходимости.

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

- [ ] Система стабильно стартует в целевом resource profile.
- [ ] Основные списки работают приемлемо.
- [ ] Нет очевидных N+1.
- [ ] Indexes проверены.
- [ ] Результаты и решения записаны в docs/DECISIONS.md или отдельный performance section.
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
