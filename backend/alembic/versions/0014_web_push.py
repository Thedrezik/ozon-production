"""User push subscriptions and per-device delivery receipts."""

import sqlalchemy as sa

from alembic import op

revision = "0014_web_push"
down_revision = "0013_notification_engine"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notification_deliveries", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("notification_deliveries", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.create_table("push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.String(2048), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(120), nullable=False),
        sa.Column("auth", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])
    op.create_table("push_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("delivery_id", sa.Integer(), sa.ForeignKey("notification_deliveries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("push_subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("delivery_id", "subscription_id"))
    op.create_index("ix_push_receipts_subscription_id", "push_receipts", ["subscription_id"])


def downgrade():
    op.drop_table("push_receipts")
    op.drop_table("push_subscriptions")
    op.drop_column("notification_deliveries", "next_attempt_at")
    op.drop_column("notification_deliveries", "attempts")
