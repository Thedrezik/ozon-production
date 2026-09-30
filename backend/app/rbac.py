from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Permission, Role, User

PERMISSIONS = (
    "orders.view", "orders.change_status", "orders.assign", "orders.change_priority",
    "comments.create", "comments.delete", "blockers.create", "blockers.resolve",
    "manager_tasks.view", "manager_tasks.manage",
    "procurement.view", "procurement.create", "procurement.manage", "finance.view",
    "users.view", "users.create", "users.manage", "roles.manage", "settings.manage",
    "analytics.view", "audit.view",
)

ROLE_PERMISSIONS = {
    "SUPER_ADMIN": PERMISSIONS,
    "ADMIN": tuple(p for p in PERMISSIONS if p != "roles.manage"),
    "MANAGER": (
        "orders.view", "orders.change_status", "orders.assign", "orders.change_priority",
        "comments.create", "blockers.create", "blockers.resolve", "procurement.view",
        "procurement.create", "procurement.manage", "finance.view", "users.view",
        "analytics.view", "manager_tasks.view", "manager_tasks.manage",
    ),
    "PRODUCTION_WORKER": ("orders.view", "orders.change_status", "comments.create", "blockers.create"),
    "PACKER": ("orders.view", "orders.change_status", "comments.create", "blockers.create"),
    "PURCHASER": ("orders.view", "comments.create", "procurement.view", "procurement.create", "procurement.manage"),
    "VIEWER": ("orders.view",),
}


def seed_rbac(db: Session) -> None:
    permissions = {p.name: p for p in db.scalars(select(Permission)).all()}
    for name in PERMISSIONS:
        if name not in permissions:
            permissions[name] = Permission(name=name)
            db.add(permissions[name])
    roles = {r.name: r for r in db.scalars(select(Role)).all()}
    for name, grants in ROLE_PERMISSIONS.items():
        if name not in roles:
            roles[name] = Role(name=name)
            db.add(roles[name])
        roles[name].permissions = [permissions[p] for p in grants]
    db.flush()


def user_permissions(user: User) -> set[str]:
    return {permission.name for role in user.roles for permission in role.permissions}
