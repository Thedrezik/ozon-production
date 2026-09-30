"""Product production profiles and order item identifiers.

Revision ID: 0009_product_profiles
Revises: 0008_procurement
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_product_profiles"
down_revision = "0008_procurement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("offer_id", sa.String(160), nullable=True))
    op.add_column("order_items", sa.Column("sku", sa.String(80), nullable=True))
    op.create_index("ix_order_items_offer_id", "order_items", ["offer_id"])
    op.create_index("ix_order_items_sku", "order_items", ["sku"])
    op.create_table(
        "product_production_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.String(160)),
        sa.Column("sku", sa.String(80)),
        sa.Column("product_name", sa.String(240), nullable=False),
        sa.Column("production_minutes", sa.Integer(), nullable=False),
        sa.Column("packing_minutes", sa.Integer(), nullable=False),
        sa.Column("complexity", sa.String(20), nullable=False),
        sa.Column("production_group", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("offer_id"),
        sa.UniqueConstraint("sku"),
        sa.CheckConstraint("offer_id IS NOT NULL OR sku IS NOT NULL", name="ck_product_profile_identifier"),
        sa.CheckConstraint("production_minutes >= 0", name="ck_product_profile_production_minutes"),
        sa.CheckConstraint("packing_minutes >= 0", name="ck_product_profile_packing_minutes"),
    )
    op.create_index("ix_product_production_profiles_offer_id", "product_production_profiles", ["offer_id"])
    op.create_index("ix_product_production_profiles_sku", "product_production_profiles", ["sku"])


def downgrade() -> None:
    op.drop_table("product_production_profiles")
    op.drop_index("ix_order_items_sku", table_name="order_items")
    op.drop_index("ix_order_items_offer_id", table_name="order_items")
    op.drop_column("order_items", "sku")
    op.drop_column("order_items", "offer_id")
