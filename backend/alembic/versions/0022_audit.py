"""Extend existing audit history, with database append-only protection."""
import sqlalchemy as sa

from alembic import op

revision = "0022_audit"
down_revision = "0021_analytics"
branch_labels = None
depends_on = None


def upgrade():
    for column in (sa.Column("entity_type", sa.String(80)), sa.Column("entity_id", sa.String(160)),
                   sa.Column("old_value", sa.JSON()), sa.Column("new_value", sa.JSON()),
                   sa.Column("ip", sa.String(80)), sa.Column("user_agent", sa.String(512))):
        op.add_column("audit_log", column)
    for name in ("entity_type", "entity_id"):
        op.create_index(f"ix_audit_log_{name}", "audit_log", [name])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Audit history is immutable'; END; $$""")
        op.execute("""CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
                   ON audit_log FOR EACH STATEMENT EXECUTE FUNCTION audit_immutable()""")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER audit_immutable ON audit_log")
        op.execute("DROP FUNCTION audit_immutable()")
    for name in ("entity_type", "entity_id"):
        op.drop_index(f"ix_audit_log_{name}", table_name="audit_log")
    for name in ("entity_type", "entity_id", "old_value", "new_value", "ip", "user_agent"):
        op.drop_column("audit_log", name)
