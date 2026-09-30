"""Procurement tasks, links and history.

Revision ID: 0008_procurement
Revises: 0007_manager_tasks
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_procurement"
down_revision = "0007_manager_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procurement_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("material_name", sa.String(240), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("responsible_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("needed_by", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ordered_at", sa.DateTime(timezone=True)),
        sa.Column("purchased_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_procurement_tasks_status", "procurement_tasks", ["status"])
    op.create_index("ix_procurement_tasks_responsible_user_id", "procurement_tasks", ["responsible_user_id"])
    op.create_index("ix_procurement_tasks_needed_by", "procurement_tasks", ["needed_by"])
    op.create_table("procurement_order_links",
                    sa.Column("task_id", sa.Integer(), sa.ForeignKey("procurement_tasks.id", ondelete="CASCADE"), primary_key=True),
                    sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True))
    op.create_table("procurement_blocker_links",
                    sa.Column("task_id", sa.Integer(), sa.ForeignKey("procurement_tasks.id", ondelete="CASCADE"), primary_key=True),
                    sa.Column("blocker_id", sa.Integer(), sa.ForeignKey("blockers.id", ondelete="CASCADE"), primary_key=True))
    op.create_table("procurement_history",
                    sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("task_id", sa.Integer(), sa.ForeignKey("procurement_tasks.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
                    sa.Column("old_status", sa.String(20)),
                    sa.Column("new_status", sa.String(20), nullable=False),
                    sa.Column("description", sa.Text(), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_procurement_history_task_id", "procurement_history", ["task_id"])


def downgrade() -> None:
    op.drop_table("procurement_history")
    op.drop_table("procurement_blocker_links")
    op.drop_table("procurement_order_links")
    op.drop_table("procurement_tasks")
