"""Persistent reconciliation freshness, separately for real and mock data."""

import sqlalchemy as sa

from alembic import op

revision = "0018_ozon_reconciliation"
down_revision = "0017_ozon_webhook"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ozon_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_sync", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_episode", sa.Integer(), nullable=False))
    op.bulk_insert(sa.table("ozon_sync_state", sa.column("id", sa.Integer()),
                           sa.column("status", sa.String()), sa.column("error_episode", sa.Integer())),
                   [{"id": 1, "status": "NEVER", "error_episode": 0},
                    {"id": 2, "status": "NEVER", "error_episode": 0}])


def downgrade():
    op.drop_table("ozon_sync_state")
