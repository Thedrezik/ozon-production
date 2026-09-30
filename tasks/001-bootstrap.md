# Task 001 — Project Bootstrap

status: completed

Complexity: HIGH
recommended_model: GPT-6 Sol
reasoning: Medium

## Goal

Создать архитектуру и минимальный рабочий каркас проекта.

После выполнения задачи проект должен запускаться через Docker Compose и содержать:

- FastAPI backend;
- React + TypeScript PWA frontend;
- PostgreSQL;
- Alembic;
- Caddy;
- Mock Mode;
- базовые tests;
- документацию архитектуры.

Реальную интеграцию с Ozon пока НЕ подключать.

---

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/PRODUCT.md`
- `/docs/STATE.md`

Другие файлы читать только при необходимости.

---

## Step 1 — Architecture

Перед написанием основной логики создать:

`/docs/ARCHITECTURE.md`

Описать кратко:

- компоненты системы;
- frontend;
- backend;
- database;
- Ozon integration architecture;
- webhook flow;
- reconciliation flow;
- authentication;
- RBAC;
- notification architecture;
- file storage;
- deployment;
- backup strategy.

Не писать огромный документ.

Нужна практическая архитектура, по которой дальше можно реализовывать проект.

---

## Step 2 — Project Structure

Создать понятную структуру проекта.

Ориентировочно:

```text
/
├── AGENTS.md
├── docker-compose.yml
├── .env.example
├── README.md
│
├── docs/
│   ├── PRODUCT.md
│   ├── STATE.md
│   ├── ARCHITECTURE.md
│   └── DECISIONS.md
│
├── tasks/
│
├── backend/
│   ├── app/
│   ├── tests/
│   ├── alembic/
│   └── ...
│
├── frontend/
│   ├── src/
│   └── ...
│
└── deployment/
```

Можно немного изменить структуру, если есть объективная причина.

---

## Step 3 — Backend

Создать минимальный FastAPI backend.

Минимум:

- application factory / application entrypoint;
- config;
- database connection;
- health endpoint;
- readiness endpoint;
- basic structured logging;
- SQLAlchemy;
- Alembic.

Endpoints:

`GET /api/health`

`GET /api/health/ready`

---

## Step 4 — Database

Добавить PostgreSQL.

Настроить:

- SQLAlchemy 2;
- Alembic;
- connection pooling с учётом VPS 1 GB RAM.

Пока не создавать все таблицы полного проекта.

Создать только базовую инфраструктуру migrations.

---

## Step 5 — Frontend

Создать:

- React;
- TypeScript;
- Vite;
- Tailwind;
- PWA.

Минимальный экран:

**Ozon Production**

Показывать:

- состояние backend;
- состояние приложения;
- MOCK MODE indicator.

Приложение должно быть mobile-first.

---

## Step 6 — PWA

Добавить:

- manifest;
- service worker;
- installable PWA;
- basic offline shell;
- offline indicator.

Не кешировать API данные таким образом, чтобы пользователь видел устаревшие данные без предупреждения.

---

## Step 7 — Mock Mode

Добавить environment variable:

`OZON_MOCK_MODE=true`

Пока Mock Mode может быть минимальным.

Но architecture должна позволять позже добавить MockOzonClient.

Настоящие Ozon credentials сейчас не использовать.

---

## Step 8 — Docker

Создать production-oriented:

`docker-compose.yml`

Минимум services:

- backend;
- postgres;
- caddy.

Frontend можно собирать multi-stage и отдавать через Caddy.

Учитывать ограничение:

- 1 CPU;
- 1 GB RAM.

Не добавлять Redis.

Не добавлять Celery.

---

## Step 9 — Environment

Создать:

`.env.example`

Минимум:

```env
APP_ENV=development
APP_SECRET=change-me

DATABASE_URL=

DOMAIN=

ORGANIZATION_TIMEZONE=

OZON_MOCK_MODE=true
OZON_CLIENT_ID=
OZON_API_KEY=

UPLOAD_DIR=/data/uploads
BACKUP_DIR=/data/backups
```

Настоящие secrets не добавлять.

---

## Step 10 — Basic Tests

Добавить минимум tests:

- backend health endpoint;
- backend readiness/database;
- config loading.

Если frontend test tooling уже настроен — добавить простой smoke test.

Не добавлять сложную test infrastructure без необходимости.

---

## Step 11 — Documentation

Создать или обновить:

- README.md
- docs/ARCHITECTURE.md
- docs/DECISIONS.md

README должен содержать команды:

- configure;
- build;
- start;
- stop;
- migrations;
- tests;
- logs.

---

## Acceptance Criteria

- [ ] `docker compose build` проходит
- [ ] `docker compose up` запускает систему
- [ ] PostgreSQL работает
- [ ] backend подключается к PostgreSQL
- [ ] `/api/health` возвращает success
- [ ] frontend открывается
- [ ] PWA manifest существует
- [ ] MOCK MODE виден
- [ ] Alembic настроен
- [ ] tests проходят
- [ ] `.env.example` создан
- [ ] secrets не находятся в git
- [ ] ARCHITECTURE.md создан
- [ ] STATE.md обновлён

---

## Constraints

Не реализовывать сейчас:

- реальный Ozon API;
- пользователей;
- RBAC;
- production queue;
- Priority Engine;
- Money at Risk;
- Telegram;
- Web Push;
- blockers.

Это будут отдельные задачи.

Не забегать вперёд.

---

## Completion

После выполнения:

1. запустить backend tests;
2. запустить frontend lint/typecheck;
3. запустить Docker build;
4. исправить ошибки;
5. обновить `/docs/STATE.md`.

В финальном ответе кратко написать:

- что создано;
- основные изменённые файлы;
- результаты tests;
- есть ли проблемы.

Не выводить содержимое всех файлов целиком.
