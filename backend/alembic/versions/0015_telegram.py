"""Telegram account links for notification delivery."""

import sqlalchemy as sa

from alembic import op

revision = "0015_telegram"
down_revision = "0014_web_push"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("telegram_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("chat_id", sa.String(40), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_telegram_accounts_user_id", "telegram_accounts", ["user_id"])
    op.create_table("telegram_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_telegram_links_user_id", "telegram_links", ["user_id"])
    op.create_index("ix_telegram_links_expires_at", "telegram_links", ["expires_at"])


def downgrade():
    op.drop_table("telegram_links")
    op.drop_table("telegram_accounts")
