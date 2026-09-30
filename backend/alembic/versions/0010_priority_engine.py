"""Priority inputs, override and configurable weights.

Revision ID: 0010_priority_engine
Revises: 0009_product_profiles
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_priority_engine"
down_revision = "0009_product_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("shipment_date_without_delay", sa.DateTime(timezone=True)))
    op.add_column("orders", sa.Column("tariff_deadline", sa.DateTime(timezone=True)))
    op.add_column("orders", sa.Column("tariff_impact", sa.Numeric(12, 2)))
    op.add_column("orders", sa.Column("order_value", sa.Numeric(12, 2)))
    op.add_column("orders", sa.Column("priority_override", sa.String(2)))
    op.add_column("orders", sa.Column("priority_pinned", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("orders") as batch:
        batch.create_check_constraint("ck_orders_tariff_impact_nonnegative", "tariff_impact IS NULL OR tariff_impact >= 0")
        batch.create_check_constraint("ck_orders_order_value_nonnegative", "order_value IS NULL OR order_value >= 0")
        batch.create_check_constraint("ck_orders_priority_override", "priority_override IS NULL OR priority_override IN ('P0','P1','P2','P3','P4')")
    op.create_table(
        "priority_settings", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deadline_weight", sa.Integer(), nullable=False),
        sa.Column("tariff_weight", sa.Integer(), nullable=False),
        sa.Column("finance_weight", sa.Integer(), nullable=False),
        sa.Column("feasibility_weight", sa.Integer(), nullable=False),
        sa.Column("high_impact_rub", sa.Numeric(12, 2), nullable=False),
        sa.Column("high_value_rub", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("deadline_weight + tariff_weight + finance_weight + feasibility_weight = 100", name="ck_priority_weights_sum"),
        sa.CheckConstraint("high_impact_rub > 0", name="ck_priority_impact_positive"),
        sa.CheckConstraint("high_value_rub > 0", name="ck_priority_value_positive"),
    )
    op.execute("INSERT INTO priority_settings (id, deadline_weight, tariff_weight, finance_weight, feasibility_weight, high_impact_rub, high_value_rub) VALUES (1, 40, 25, 20, 15, 1000, 10000)")


def downgrade() -> None:
    op.drop_table("priority_settings")
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("ck_orders_priority_override", type_="check")
        batch.drop_constraint("ck_orders_order_value_nonnegative", type_="check")
        batch.drop_constraint("ck_orders_tariff_impact_nonnegative", type_="check")
    for name in ("priority_pinned", "priority_override", "order_value", "tariff_impact", "tariff_deadline", "shipment_date_without_delay"):
        op.drop_column("orders", name)
