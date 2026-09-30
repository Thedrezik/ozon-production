"""Production blockers.

Revision ID: 0006_blockers
Revises: 0005_comments_timeline
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_blockers"
down_revision = "0005_comments_timeline"
branch_labels = None
depends_on = None

TYPES = (
    ("MATERIAL_MISSING", "Нет материала"), ("EDGE_TAPE_MISSING", "Нет кромки"),
    ("HARDWARE_MISSING", "Нет фурнитуры"), ("PACKAGING_MISSING", "Нет упаковки"),
    ("PART_MISSING", "Нет детали"), ("DEFECT", "Брак"), ("REWORK", "Переделка"),
    ("EQUIPMENT_FAILURE", "Поломка оборудования"), ("PICKING_ERROR", "Ошибка комплектации"),
    ("CLARIFICATION", "Нужно уточнение"), ("OTHER", "Другое"),
)


def upgrade() -> None:
    op.create_table("blocker_types", sa.Column("code", sa.String(40), primary_key=True),
                    sa.Column("display_name", sa.String(100), nullable=False))
    table = sa.table("blocker_types", sa.column("code", sa.String), sa.column("display_name", sa.String))
    op.bulk_insert(table, [{"code": code, "display_name": name} for code, name in TYPES])
    op.create_table(
        "blockers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type_code", sa.String(40), sa.ForeignKey("blocker_types.code"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("creator_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("expected_resolution_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("previous_production_status", sa.String(40)),
    )
    op.create_index("ix_blockers_order_id", "blockers", ["order_id"])
    op.create_index("ix_blockers_status", "blockers", ["status"])
    op.create_table(
        "manager_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("source_type", "source_id"),
    )
    op.create_index("ix_manager_tasks_order_id", "manager_tasks", ["order_id"])
    op.create_index("ix_manager_tasks_status", "manager_tasks", ["status"])


def downgrade() -> None:
    op.drop_table("manager_tasks")
    op.drop_table("blockers")
    op.drop_table("blocker_types")
