"""External FBS fields and separate diagnostic snapshot."""

import sqlalchemy as sa

from alembic import op

revision = "0016_ozon_fbs_import"
down_revision = "0015_telegram"
branch_labels = None
depends_on = None


def upgrade():
    for name, type_ in (
        ("ozon_order_id", sa.String(80)), ("ozon_substatus", sa.String(80)),
        ("warehouse_name", sa.String(240)),
        ("ozon_in_process_at", sa.DateTime(timezone=True)),
        ("ozon_delivering_date", sa.DateTime(timezone=True)),
    ):
        op.add_column("orders", sa.Column(name, type_, nullable=True))
    op.create_index("ix_orders_ozon_order_id", "orders", ["ozon_order_id"])
    op.add_column("order_items", sa.Column("price", sa.Numeric(18, 4), nullable=True))
    op.add_column("order_items", sa.Column("currency", sa.String(10), nullable=True))
    op.create_table("ozon_posting_data",
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("tariffication", sa.JSON(), nullable=True),
        sa.Column("tariffication_steps", sa.JSON(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("ozon_posting_data")
    op.drop_column("order_items", "currency")
    op.drop_column("order_items", "price")
    op.drop_index("ix_orders_ozon_order_id", table_name="orders")
    for name in ("ozon_delivering_date", "ozon_in_process_at", "warehouse_name",
                 "ozon_substatus", "ozon_order_id"):
        op.drop_column("orders", name)
