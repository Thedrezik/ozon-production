"""Add searchable order number and warehouse fields."""

import sqlalchemy as sa
from alembic import op

revision = "0012_order_search_fields"
down_revision = "0011_tariff_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("order_number", sa.String(80), nullable=True))
    op.add_column("orders", sa.Column("warehouse_id", sa.String(80), nullable=True))
    op.create_index("ix_orders_order_number", "orders", ["order_number"])
    op.create_index("ix_orders_warehouse_id", "orders", ["warehouse_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_warehouse_id", table_name="orders")
    op.drop_index("ix_orders_order_number", table_name="orders")
    op.drop_column("orders", "warehouse_id")
    op.drop_column("orders", "order_number")
