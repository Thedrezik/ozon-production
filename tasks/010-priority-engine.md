# Task 010 — Priority Engine

status: completed
complexity: HIGH  
recommended_model: GPT-6 Sol
reasoning: Medium

## Goal

Создать прозрачный алгоритм определения производственного приоритета заказа.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Приоритет учитывать shipment deadlines, tariff deadline, financial impact, production duration, blockers и manual override.
- Уровни: P0 CRITICAL, P1 URGENT, P2 TODAY, P3 PLANNED, P4 LATER.
- Алгоритм должен возвращать не только score, но и human-readable reasons.
- Пример причины: 'тариф ухудшится через 1ч 20м; возможная потеря 640 ₽; производство ~45 минут'.
- Blocked заказы не должны автоматически исчезать из риска; отображать их отдельно как urgent-but-blocked.
- Добавить configurable weights/settings.
- Добавить manual pin/priority override.
- Manual override записывать в audit.
- Все денежные расчёты использовать Decimal.
- Не связывать engine напрямую с UI — сделать отдельный domain/service layer.

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

- [ ] Одинаковые входные данные дают детерминированный результат.
- [ ] Срочный заказ поднимается выше обычного.
- [ ] Финансовый риск влияет на приоритет.
- [ ] Время производства влияет на возможность успеть.
- [ ] Blocked состояние учитывается.
- [ ] Manual override работает.
- [ ] Причины приоритета доступны frontend.
- [ ] Есть comprehensive unit tests.
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
