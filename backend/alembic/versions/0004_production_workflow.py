"""Production stages and configurable status presentation.

Revision ID: 0004_production_workflow
Revises: 0003_mock_orders
"""

import sqlalchemy as sa

from alembic import op

STATUS_ROWS = (
    ("NEW", "Новый"), ("QUEUED", "В очереди"),
    ("SENT_TO_PRODUCTION", "Передан в производство"),
    ("IN_PRODUCTION", "В производстве"), ("BLOCKED", "Заблокирован"),
    ("PRODUCED", "Произведён"), ("QUALITY_CHECK", "Проверка качества"),
    ("PACKING", "Упаковка"), ("READY_TO_SHIP", "Готов к отгрузке"),
    ("HANDED_TO_SHIPPING", "Передан в доставку"),
    ("DONE", "Завершён"), ("CANCELLED", "Отменён"),
)

revision = "0004_production_workflow"
down_revision = "0003_mock_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("internal_statuses", sa.Column("display_name", sa.String(80), nullable=True))
    op.add_column("internal_statuses", sa.Column("sort_order", sa.Integer(), nullable=True))
    table = sa.table("internal_statuses", sa.column("name"), sa.column("display_name"), sa.column("sort_order"))
    for index, (code, label) in enumerate(STATUS_ROWS):
        op.execute(table.update().where(table.c.name == code).values(display_name=label, sort_order=index))
    op.bulk_insert(table, [
        {"name": code, "display_name": label, "sort_order": index}
        for index, (code, label) in enumerate(STATUS_ROWS)
        if code in ("QUALITY_CHECK", "HANDED_TO_SHIPPING")
    ])
    op.alter_column("internal_statuses", "display_name", nullable=False)
    op.alter_column("internal_statuses", "sort_order", nullable=False)
    for name in ("production_started_at", "production_completed_at", "packing_started_at", "ready_to_ship_at", "handed_to_shipping_at", "done_at"):
        op.add_column("orders", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    connection = op.get_bind()
    for code, field in (("IN_PRODUCTION", "production_started_at"), ("PRODUCED", "production_completed_at"), ("PACKING", "packing_started_at"), ("READY_TO_SHIP", "ready_to_ship_at"), ("HANDED_TO_SHIPPING", "handed_to_shipping_at"), ("DONE", "done_at")):
        connection.execute(sa.text(f"UPDATE orders SET {field} = (SELECT MIN(changed_at) FROM status_history WHERE order_id = orders.id AND new_status = :code)"), {"code": code})


def downgrade() -> None:
    for name in ("done_at", "handed_to_shipping_at", "ready_to_ship_at", "packing_started_at", "production_completed_at", "production_started_at"):
        op.drop_column("orders", name)
    op.drop_column("internal_statuses", "sort_order")
    op.drop_column("internal_statuses", "display_name")
    op.execute(sa.text("DELETE FROM internal_statuses WHERE name IN ('QUALITY_CHECK', 'HANDED_TO_SHIPPING')"))
