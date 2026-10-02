"""Composite indexes for bounded lists, histories and delivery polling."""
from alembic import op

revision = "0023_performance"
down_revision = "0022_audit"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_notifications_user_created_id", "notifications", ["user_id", "created_at", "id"]),
    ("ix_delivery_due", "notification_deliveries", ["channel", "status", "next_attempt_at", "id"]),
    ("ix_audit_created_id", "audit_log", ["created_at", "id"]),
    ("ix_comments_order_created_id", "comments", ["order_id", "created_at", "id"]),
    ("ix_history_order_changed_id", "status_history", ["order_id", "changed_at", "id"]),
    ("ix_timeline_order_created_id", "order_timeline_events", ["order_id", "created_at", "id"]),
)


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
