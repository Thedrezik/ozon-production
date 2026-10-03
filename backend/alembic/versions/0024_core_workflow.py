"""Problem resolution provenance and worker permission; keep status codes/data."""
import sqlalchemy as sa

from alembic import op

revision = "0024_core_workflow"
down_revision = "0023_performance"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("blockers") as batch:
        batch.add_column(sa.Column("resolved_by_user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("resolution_comment", sa.Text(), nullable=True))
        batch.create_foreign_key("fk_blockers_resolved_by", "users", ["resolved_by_user_id"], ["id"], ondelete="SET NULL")
    op.execute(sa.text("INSERT INTO role_permissions (role_id, permission_id) "
                       "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p "
                       "WHERE r.name = 'PRODUCTION_WORKER' AND p.name = 'blockers.resolve' "
                       "AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id=r.id AND rp.permission_id=p.id)"))
    op.create_index("ix_orders_received_id", "orders", ["ozon_in_process_at", "id"])


def downgrade():
    op.drop_index("ix_orders_received_id", table_name="orders")
    op.execute(sa.text("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE name='PRODUCTION_WORKER') "
                       "AND permission_id IN (SELECT id FROM permissions WHERE name='blockers.resolve')"))
    with op.batch_alter_table("blockers") as batch:
        batch.drop_constraint("fk_blockers_resolved_by", type_="foreignkey")
        batch.drop_column("resolution_comment")
        batch.drop_column("resolved_by_user_id")
