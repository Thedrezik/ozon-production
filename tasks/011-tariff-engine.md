# Task 011 — Tariff and Financial Effect Engine

status: completed
complexity: HIGH  
recommended_model: GPT-6 Sol
reasoning: Medium

## Goal

Создать отдельный модуль анализа тарификации Ozon и финансового эффекта времени отгрузки.

На этом этапе допускается работать на mock payload, но структура должна соответствовать будущей реальной интеграции.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Создать domain model для current tariff, next tariff и tariff steps.
- Поддержать временную шкалу тарификации.
- Рассчитывать current_tariff_cost, next_tariff_cost, delta_to_next_tariff, potential_saving, potential_loss только когда это математически обосновано.
- Если сумму вычислить нельзя — показывать процент/тип изменения, но не придумывать ₽.
- Все денежные значения Decimal.
- Все timestamps UTC.
- Отделить parser внешних данных от domain calculations.
- Написать tests на границах времени.

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

- [ ] Tariff timeline строится корректно.
- [ ] Следующая ступень определяется корректно.
- [ ] Финансовая разница считается без float.
- [ ] Неизвестные/неполные данные не приводят к выдуманной сумме.
- [ ] Tests покрывают переход через deadline.
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
