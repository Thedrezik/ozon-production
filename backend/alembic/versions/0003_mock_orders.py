"""Mock orders and production workflow.

Revision ID: 0003_mock_orders
Revises: 0002_auth_rbac
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_mock_orders"
down_revision = "0002_auth_rbac"
branch_labels = None
depends_on = None

STATUSES = (
    "NEW", "QUEUED", "SENT_TO_PRODUCTION", "IN_PRODUCTION", "BLOCKED",
    "PRODUCED", "PACKING", "READY_TO_SHIP", "DONE", "CANCELLED",
)


def upgrade() -> None:
    op.create_table("internal_statuses", sa.Column("name", sa.String(40), primary_key=True))
    op.bulk_insert(sa.table("internal_statuses", sa.column("name", sa.String)), [{"name": name} for name in STATUSES])
    op.create_table(
        "orders", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("posting_number", sa.String(80), nullable=False),
        sa.Column("ozon_status", sa.String(40), nullable=False),
        sa.Column("internal_status", sa.String(40), sa.ForeignKey("internal_statuses.name"), nullable=False),
        sa.Column("shipment_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_mock", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_orders_posting_number", "orders", ["posting_number"], unique=True)
    op.create_index("ix_orders_internal_status", "orders", ["internal_status"])
    op.create_index("ix_orders_shipment_deadline", "orders", ["shipment_deadline"])
    op.create_table(
        "order_items", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_name", sa.String(240), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_table(
        "status_history", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_status", sa.String(40)),
        sa.Column("new_status", sa.String(40), sa.ForeignKey("internal_statuses.name"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index("ix_status_history_order_id", "status_history", ["order_id"])
    op.create_table(
        "assignments", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index("ix_assignments_user_id", "assignments", ["user_id"])


def downgrade() -> None:
    op.drop_table("assignments")
    op.drop_table("status_history")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("internal_statuses")
