"""Comments and order timeline.

Revision ID: 0005_comments_timeline
Revises: 0004_production_workflow
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_comments_timeline"
down_revision = "0004_production_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_comments_order_id", "comments", ["order_id"])
    op.create_index("ix_comments_author_user_id", "comments", ["author_user_id"])
    op.create_index("ix_comments_created_at", "comments", ["created_at"])
    op.create_table(
        "comment_mentions",
        sa.Column("comment_id", sa.Integer(), sa.ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "order_timeline_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_order_timeline_events_order_id", "order_timeline_events", ["order_id"])
    op.create_index("ix_order_timeline_events_actor_user_id", "order_timeline_events", ["actor_user_id"])
    op.create_index("ix_order_timeline_events_created_at", "order_timeline_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("order_timeline_events")
    op.drop_table("comment_mentions")
    op.drop_table("comments")
