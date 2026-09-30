# Task 003 — Mock Orders and Production Queue

Status: completed

Complexity: MEDIUM/HIGH
recommended_model: GPT-6 Sol
reasoning: Medium

## Goal

Создать первую реально полезную версию производственной очереди.

Использовать только Mock Ozon data.

Реальный Ozon API пока не подключать.

После выполнения работник должен иметь возможность открыть приложение на телефоне и работать с тестовыми заказами.

---

## Read First

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`

Прочитать существующие:

- database models;
- auth;
- RBAC;
- frontend routing.

---

## Order Model

Создать необходимые сущности для mock-заказов.

Минимум:

Order / Posting

OrderItem

InternalStatus

StatusHistory

Assignment

Хранить отдельно:

- ozon_status;
- internal_status.

Никогда их не смешивать.

---

## Mock Orders

Создать Mock Ozon service.

При:

`OZON_MOCK_MODE=true`

должна быть возможность создать тестовые заказы.

Минимум:

1. обычный заказ;
2. срочный;
3. заказ с близким дедлайном;
4. просроченный;
5. blocked;
6. отменённый;
7. готовый к отгрузке.

Добавить development command или seed.

---

## Internal Statuses

Минимальные статусы:

NEW

QUEUED

SENT_TO_PRODUCTION

IN_PRODUCTION

BLOCKED

PRODUCED

PACKING

READY_TO_SHIP

DONE

CANCELLED

---

## Status History

Каждое изменение статуса сохранять:

- old status;
- new status;
- changed_at;
- changed_by.

---

## Production Queue

Создать backend API производственной очереди.

Фильтры минимум:

- internal status;
- assigned user;
- blocked;
- ready;
- overdue.

Добавить pagination.

---

## Employee UI

Создать mobile-first экран:

**Очередь**

Карточка должна показывать:

- название товара;
- количество;
- posting number;
- deadline;
- internal status;
- assigned worker.

Большие действия:

- Взять в работу
- Начать производство
- Проблема
- Произведено
- На упаковку
- Готово

Кнопка `Проблема` пока может открывать простой placeholder/modal.

Полноценные blockers будут следующей задачей.

---

## My Tasks

Добавить экран:

**Мои задачи**

Показывать заказы, назначенные текущему пользователю.

---

## Assignment

Пользователь с нужным permission может:

- назначить заказ пользователю;
- снять назначение.

Работник может нажать:

`Взять в работу`

если это разрешено правилами.

---

## Realtime

Изменения статуса должны быстро появляться у других пользователей.

Использовать WebSocket или SSE согласно ARCHITECTURE.md.

Не добавлять Redis.

Для single-instance backend достаточно простой in-process реализации.

---

## Permissions

Минимум:

Worker:

- orders.view
- orders.change_status
- comments/create later
- blockers/create later

Manager:

- видит все заказы;
- может назначать;
- может менять status.

---

## Tests

Обязательно:

- создание mock orders;
- status transition;
- invalid status transition;
- assignment;
- permission checks;
- status history;
- queue filtering.

---

## Acceptance Scenario

1. Admin входит.
2. Создаёт worker.
3. Mock seed создаёт заказы.
4. Worker входит с телефона.
5. Открывает очередь.
6. Нажимает `Взять в работу`.
7. Заказ назначается ему.
8. Нажимает `Начать производство`.
9. Manager видит новое состояние.
10. Worker нажимает `Произведено`.
11. Заказ переходит дальше по workflow.

---

## Acceptance Criteria

- [x] mock orders существуют
- [x] очередь работает
- [x] статусы работают
- [x] history сохраняется
- [x] assignment работает
- [x] permissions работают
- [x] mobile UI удобен
- [x] realtime update работает
- [x] tests проходят
- [x] STATE.md обновлён
