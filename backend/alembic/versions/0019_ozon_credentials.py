"""Encrypted Ozon account configuration."""
import sqlalchemy as sa

from alembic import op

revision = "0019_ozon_credentials"
down_revision = "0018_ozon_reconciliation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ozon_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("ozon_credentials")
