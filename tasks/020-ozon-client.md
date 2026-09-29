# Task 020 — Ozon Seller API Client

status: pending  
complexity: HIGH  
recommended_model: GPT-5.6 Sol  
reasoning: High

## Goal

Создать production-ready клиент актуального Ozon Seller API.

Перед реализацией обязательно проверить актуальную официальную документацию.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Не доверять старым endpoint из PRODUCT.md без проверки.
- Создать OzonClient abstraction и MockOzonClient.
- Secrets только backend.
- Поддержать timeout, retry, exponential backoff, rate limit handling.
- Не retry-ить бесконечно.
- Различать 4xx, 5xx, timeout и rate limiting.
- Structured logging без secrets.
- Сделать connection check.
- Не подключать frontend напрямую к Ozon.

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

- [ ] Актуальные endpoints подтверждены официальной документацией.
- [ ] Connection check работает.
- [ ] Ошибки классифицируются.
- [ ] Retry ограничен.
- [ ] Mock и real client имеют совместимый interface.
- [ ] Tests используют mock HTTP.
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
