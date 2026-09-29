# Task 002 — Authentication and RBAC

Complexity: HIGH

## Goal

Реализовать пользователей, авторизацию и систему прав доступа.

Не реализовывать Ozon integration в этой задаче.

---

## Read First

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`

Также прочитать существующий код auth/database.

PRODUCT.md читать только связанные разделы при необходимости.

---

## Requirements

Реализовать сущности:

- User
- Role
- Permission
- UserRole
- RolePermission

Минимальные роли:

- SUPER_ADMIN
- ADMIN
- MANAGER
- PRODUCTION_WORKER
- PACKER
- PURCHASER
- VIEWER

Минимальные permissions:

- orders.view
- orders.change_status
- orders.assign
- orders.change_priority

- comments.create
- comments.delete

- blockers.create
- blockers.resolve

- procurement.view
- procurement.create
- procurement.manage

- finance.view

- users.view
- users.create
- users.manage

- roles.manage

- settings.manage

- analytics.view

- audit.view

---

## Authentication

Реализовать:

- login;
- logout;
- current user / me;
- change password;
- deactivate user.

Использовать безопасный password hashing.

Предпочтительно:

Argon2id.

Не хранить долгоживущий access token в localStorage.

Использовать безопасную cookie/session architecture согласно ARCHITECTURE.md.

---

## Security

Permissions обязательно проверять backend.

Frontend hiding controls не считается security.

Добавить basic login rate limiting без тяжёлой инфраструктуры.

Не добавлять Redis только ради rate limiting.

---

## Admin Bootstrap

Добавить CLI command для создания первого admin.

Например:

```bash
python -m app.cli create-admin
```

Команда должна безопасно запросить или принять необходимые данные.

Пароль не логировать.

---

## Registration

Не делать открытую публичную регистрацию с мгновенным доступом.

Для MVP достаточно:

admin создаёт пользователей.

Architecture должна позволять позже добавить invite/pending approval.

---

## Frontend

Добавить:

- login screen;
- logout;
- current user;
- простую admin users page;
- роли пользователя;
- permission-aware navigation.

---

## Audit

Создать базовую audit log инфраструктуру.

Минимум логировать:

- login success;
- login failure при необходимости без sensitive data;
- user created;
- user deactivated;
- role changed;
- password changed/reset.

---

## Tests

Обязательно:

- login;
- invalid login;
- protected endpoint;
- inactive user;
- role assignment;
- permission allowed;
- permission denied;
- admin creation;
- password hashing.

---

## Acceptance Criteria

- [ ] admin можно создать CLI командой
- [ ] пользователь может войти
- [ ] пользователь может выйти
- [ ] `/me` работает
- [ ] inactive user не получает доступ
- [ ] permissions проверяются backend
- [ ] admin может создать пользователя
- [ ] admin может назначить роль
- [ ] обычный worker не получает admin permissions
- [ ] audit записывает важные изменения
- [ ] tests проходят
- [ ] STATE.md обновлён
