"""Indexes for bounded analytics cohorts."""
from alembic import op

revision = "0021_analytics"
down_revision = "0020_photos"
branch_labels = None
depends_on = None

INDEXES = {"orders": ("created_at", "production_started_at", "production_completed_at", "ready_to_ship_at"),
           "blockers": ("created_at",), "status_history": ("changed_at",)}


def upgrade():
    for table, columns in INDEXES.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table, columns in INDEXES.items():
        for column in columns:
            op.drop_index(f"ix_{table}_{column}", table_name=table)
