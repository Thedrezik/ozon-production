"""Store normalized tariff timeline source data.

Revision ID: 0011_tariff_engine
Revises: 0010_priority_engine
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_tariff_engine"
down_revision = "0010_priority_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("tariff_steps", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "tariff_steps")
