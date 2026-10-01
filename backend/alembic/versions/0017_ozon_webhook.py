"""Durable Ozon push inbox."""

import sqlalchemy as sa

from alembic import op

revision = "0017_ozon_webhook"
down_revision = "0016_ozon_fbs_import"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("ozon_delivery_date_begin", "ozon_delivery_date_end"):
        op.add_column("orders", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.create_table("ozon_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(64), nullable=False, unique=True),
        sa.Column("message_type", sa.String(100), nullable=False),
        sa.Column("posting_number", sa.String(80), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True))
    op.create_index("ix_ozon_webhook_events_status", "ozon_webhook_events", ["status"])
    op.create_index("ix_ozon_webhook_events_next_attempt_at", "ozon_webhook_events", ["next_attempt_at"])


def downgrade():
    op.drop_table("ozon_webhook_events")
    for name in ("ozon_delivery_date_end", "ozon_delivery_date_begin"):
        op.drop_column("orders", name)
