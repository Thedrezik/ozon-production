# Task 026 — Files, Photos and QR

status: completed
complexity: MEDIUM  
recommended_model: GPT-6 Sol
reasoning: Low

## Goal

Добавить фотографии, безопасное файловое хранилище и QR/штрихкод workflow.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Локальное storage abstraction с возможностью позже заменить на S3.
- Upload size limits.
- Проверка MIME.
- Random server filenames.
- Сжатие изображений.
- Привязка фото к order, blocker или comment.
- Генерировать внутренний QR для posting_number.
- PWA должна уметь сканировать QR/поддерживаемый barcode камерой.
- При сканировании открывать заказ.

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

- [x] Фото можно прикрепить к blocker.
- [x] Большой/неподдерживаемый файл отклоняется.
- [x] QR заказа генерируется.
- [x] Сканирование открывает нужный order.
- [x] Storage service абстрагирован.
- [x] STATE.md обновлён.

## Completion

Перед завершением задачи:

1. Проверить все acceptance criteria.
2. Запустить связанные backend tests.
3. Запустить frontend tests/lint/typecheck, если задача затрагивает frontend.
4. Исправить обнаруженные ошибки.
5. Обновить `/docs/STATE.md`.
6. Изменить `status: completed` этого task на `status: completed`, если задача полностью закончена.

Финальный отчёт должен быть коротким:

- что реализовано;
- основные изменённые файлы;
- какие tests запущены;
- результат tests;
- оставшиеся проблемы, если есть.

Не печатать содержимое целых исходных файлов в финальном ответе.
