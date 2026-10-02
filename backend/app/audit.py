"""Structured audit in the existing table; explicit allowlists never inspect secrets."""
import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, event, inspect, or_, select
from sqlalchemy.orm import Session

from app import models
from app.logging import redact_text

# No request body, credential ciphertext, token, password, free-form descriptions or
# raw integration payloads are serialized. Extend only after reviewing a field.
FIELDS = {
    models.Order: "internal_status priority_override priority_pinned",
    models.Assignment: "order_id user_id assigned_by",
    models.User: "is_active",
    models.Role: "name",
    models.InternalStatus: "name display_name sort_order",
    models.PrioritySettings: "deadline_weight tariff_weight finance_weight feasibility_weight high_impact_rub high_value_rub",
    models.Blocker: "order_id type_code severity status assigned_to expected_resolution_at resolved_at previous_production_status",
    models.ManagerTask: "source_type source_id order_id severity status assigned_to due_at resolved_at",
    models.ProcurementTask: "quantity severity status responsible_user_id needed_by ordered_at purchased_at delivered_at cancelled_at",
    models.ProcurementOrderLink: "task_id order_id",
    models.ProcurementBlockerLink: "task_id blocker_id",
    models.ProductProductionProfile: "offer_id sku production_minutes packing_minutes complexity production_group",
    models.OzonCredentials: "revision expires_at checked_at",
}
_installed = False
SECRET = re.compile(r"password|secret|token|api.?key|master.?key|private.?key|encrypted.?credentials|authorization|cookie", re.IGNORECASE)


def redact(item):
    if isinstance(item, dict):
        return {key: "[REDACTED]" if SECRET.search(key) else redact(val) for key, val in item.items()}
    if isinstance(item, list):
        return [redact(val) for val in item]
    if isinstance(item, str):
        return redact_text(item)
    return item


def value(item):
    if isinstance(item, datetime):
        return (item.replace(tzinfo=timezone.utc) if item.tzinfo is None else item.astimezone(timezone.utc)).isoformat()
    if isinstance(item, Decimal):
        return str(item)
    return item


def before_flush(db, _context, _instances):
    # Historical Alembic data seeds run before the extended audit schema exists.
    if not getattr(db.get_bind(), "_audit_enabled", False):
        return
    for row in db.deleted:
        if isinstance(row, models.AuditLog):
            raise RuntimeError("Audit history is immutable")  # noqa: TRY004 - append-only policy
    for row in db.dirty:
        if isinstance(row, models.AuditLog) and db.is_modified(row):
            raise RuntimeError("Audit history is immutable")
    pending = db.info.setdefault("audit_pending", [])
    tracked = [row for row in set(db.new) | set(db.dirty) | set(db.deleted) if type(row) in FIELDS]
    originals = {}
    # One bounded snapshot query per entity type, including bulk mutations.
    for model in {type(row) for row in tracked}:
        persistent = [row for row in tracked if type(row) is model and inspect(row).persistent]
        if not persistent:
            continue
        mapper = inspect(model)
        table = mapper.local_table
        columns = list(dict.fromkeys([*mapper.primary_key, *[table.c[key] for key in FIELDS[model].split()]]))
        previous = db.connection().execute(select(*columns).where(or_(*[
            and_(*[column == item for column, item in zip(mapper.primary_key, inspect(row).identity, strict=True)])
            for row in persistent
        ]))).mappings().all()
        by_identity = {tuple(record[column.key] for column in mapper.primary_key): record for record in previous}
        for row in persistent:
            originals[row] = {key: value(by_identity[inspect(row).identity][key]) for key in FIELDS[model].split()}
    for row in tracked:
        state = inspect(row)
        fields = FIELDS[type(row)].split()
        old = originals.get(row)
        new = None if row in db.deleted else {key: value(getattr(row, key)) for key in fields}
        if isinstance(row, models.User):
            history = state.attrs.roles.history
            current = sorted(role.name for role in row.roles)
            if old is not None:
                old["roles"] = sorted({role.name for role in row.roles if role not in history.added} |
                                      {role.name for role in history.deleted})
            if new is not None:
                new["roles"] = current
        if isinstance(row, models.Role):
            history = state.attrs.permissions.history
            if old is not None:
                old["permissions"] = sorted({p.name for p in row.permissions if p not in history.added} |
                                            {p.name for p in history.deleted})
            if new is not None:
                new["permissions"] = sorted(p.name for p in row.permissions)
        # Record text-only edits without copying untrusted text into audit.
        if old is not None and new is not None:
            changed_text = [key for key in ("description", "title", "material_name", "product_name")
                            if key in state.attrs and state.attrs[key].history.has_changes()]
            if changed_text:
                old["edited_text_fields"] = []
                new["edited_text_fields"] = changed_text
        if old == new:
            continue
        operation = "deleted" if new is None else "created" if old is None else "updated"
        pending.append((row, state.mapper, old, new, operation, dict(db.info.get("audit_context", {}))))
    for row in db.new:
        if isinstance(row, models.AuditLog):
            row.old_value = redact(row.old_value)
            row.new_value = redact(row.new_value)
            context = db.info.get("audit_context", {})
            row.ip = row.ip or context.get("ip")
            row.user_agent = row.user_agent or context.get("user_agent")
            row.user_agent = redact_text(row.user_agent) if row.user_agent else None
            row.detail = redact_text(row.detail) if row.detail else None
            row.actor_user_id = row.actor_user_id or context.get("actor_user_id")


def after_flush(db, _context):
    for row, mapper, old, new, operation, context in db.info.pop("audit_pending", []):
        if old is None and new is not None:
            for key in FIELDS[type(row)].split():
                new[key] = value(getattr(row, key))
        identity = ":".join(str(getattr(row, column.key)) for column in mapper.primary_key)
        db.add(models.AuditLog(action=f"{mapper.local_table.name}.{operation}",
                               entity_type=mapper.local_table.name, entity_id=identity,
                               old_value=old, new_value=new, **context))


def clear_pending(db, *_args):
    db.info.pop("audit_pending", None)


def guard_bulk(execution):
    statement = execution.statement
    if (execution.is_update or execution.is_delete) and getattr(getattr(statement, "table", None), "name", None) == "audit_log":
        raise RuntimeError("Audit history is immutable")


def install_audit():
    global _installed
    if _installed:
        return
    _installed = True
    event.listen(Session, "do_orm_execute", guard_bulk)
    event.listen(Session, "before_flush", before_flush)
    event.listen(Session, "after_flush_postexec", after_flush)
    event.listen(Session, "after_rollback", clear_pending)
    event.listen(Session, "after_soft_rollback", clear_pending)
