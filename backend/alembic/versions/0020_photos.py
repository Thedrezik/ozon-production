"""Photo metadata."""
import sqlalchemy as sa

from alembic import op

revision = "0020_photos"
down_revision = "0019_ozon_credentials"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("blocker_id", sa.Integer(), sa.ForeignKey("blockers.id")),
        sa.Column("comment_id", sa.Integer(), sa.ForeignKey("comments.id")),
        sa.Column("uploader_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("storage_key", sa.String(40), unique=True, nullable=False),
        sa.Column("mime_type", sa.String(40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    for name in ("order_id", "blocker_id", "comment_id"):
        op.create_index(f"ix_photos_{name}", "photos", [name])


def downgrade():
    op.drop_table("photos")
