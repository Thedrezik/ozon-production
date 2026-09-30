"""Manager task permissions and optional order references.

Revision ID: 0007_manager_tasks
Revises: 0006_blockers
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_manager_tasks"
down_revision = "0006_blockers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("manager_tasks", naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}) as batch:
            batch.alter_column("order_id", existing_type=sa.Integer(), nullable=True)
            batch.drop_constraint("fk_manager_tasks_order_id_orders", type_="foreignkey")
            batch.create_foreign_key("fk_manager_tasks_order_id_orders", "orders", ["order_id"], ["id"], ondelete="SET NULL")
    else:
        op.alter_column("manager_tasks", "order_id", existing_type=sa.Integer(), nullable=True)
        op.drop_constraint("manager_tasks_order_id_fkey", "manager_tasks", type_="foreignkey")
        op.create_foreign_key("manager_tasks_order_id_fkey", "manager_tasks", "orders", ["order_id"], ["id"], ondelete="SET NULL")
    permissions = sa.table("permissions", sa.column("name", sa.String()), sa.column("id", sa.Integer()))
    roles = sa.table("roles", sa.column("name", sa.String()), sa.column("id", sa.Integer()))
    grants = sa.table("role_permissions", sa.column("role_id", sa.Integer()), sa.column("permission_id", sa.Integer()))
    connection = op.get_bind()
    for name in ("manager_tasks.view", "manager_tasks.manage"):
        permission_id = connection.execute(sa.select(permissions.c.id).where(permissions.c.name == name)).scalar_one_or_none()
        if permission_id is None:
            connection.execute(permissions.insert().values(name=name))
            permission_id = connection.execute(sa.select(permissions.c.id).where(permissions.c.name == name)).scalar_one()
        for role in ("SUPER_ADMIN", "ADMIN", "MANAGER"):
            role_id = connection.execute(sa.select(roles.c.id).where(roles.c.name == role)).scalar_one()
            exists = connection.execute(sa.select(grants.c.role_id).where(
                grants.c.role_id == role_id, grants.c.permission_id == permission_id)).scalar_one_or_none()
            if exists is None:
                connection.execute(grants.insert().values(role_id=role_id, permission_id=permission_id))


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE name IN ('manager_tasks.view', 'manager_tasks.manage'))")
    op.execute("DELETE FROM permissions WHERE name IN ('manager_tasks.view', 'manager_tasks.manage')")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("manager_tasks", naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}) as batch:
            batch.drop_constraint("fk_manager_tasks_order_id_orders", type_="foreignkey")
            batch.create_foreign_key("fk_manager_tasks_order_id_orders", "orders", ["order_id"], ["id"], ondelete="CASCADE")
            batch.alter_column("order_id", existing_type=sa.Integer(), nullable=False)
    else:
        op.drop_constraint("manager_tasks_order_id_fkey", "manager_tasks", type_="foreignkey")
        op.create_foreign_key("manager_tasks_order_id_fkey", "manager_tasks", "orders", ["order_id"], ["id"], ondelete="CASCADE")
        op.alter_column("manager_tasks", "order_id", existing_type=sa.Integer(), nullable=False)
