from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    roles: Mapped[list["Role"]] = relationship(secondary="user_roles", back_populates="users")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    users: Mapped[list[User]] = relationship(secondary="user_roles", back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(secondary="role_permissions", back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    roles: Mapped[list[Role]] = relationship(secondary="role_permissions", back_populates="permissions")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    posting_number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    order_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    warehouse_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    ozon_status: Mapped[str] = mapped_column(String(40), nullable=False)
    internal_status: Mapped[str] = mapped_column(ForeignKey("internal_statuses.name"), nullable=False, index=True)
    shipment_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    shipment_date_without_delay: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tariff_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tariff_impact: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    order_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    tariff_steps: Mapped[list[dict] | None] = mapped_column(JSON)
    priority_override: Mapped[str | None] = mapped_column(String(2))
    priority_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    production_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    production_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    packing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_to_ship_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handed_to_shipping_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    assignment: Mapped["Assignment | None"] = relationship(back_populates="order", uselist=False, cascade="all, delete-orphan")


class PrioritySettings(Base):
    __tablename__ = "priority_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deadline_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=40)
    tariff_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    finance_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    feasibility_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    high_impact_rub: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal(1000))
    high_value_rub: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal(10000))


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_name: Mapped[str] = mapped_column(String(240), nullable=False)
    offer_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    sku: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    order: Mapped[Order] = relationship(back_populates="items")


class ProductProductionProfile(Base):
    __tablename__ = "product_production_profiles"
    __table_args__ = (
        UniqueConstraint("offer_id"),
        UniqueConstraint("sku"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    sku: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    product_name: Mapped[str] = mapped_column(String(240), nullable=False)
    production_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    packing_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    complexity: Mapped[str] = mapped_column(String(20), nullable=False)
    production_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InternalStatus(Base):
    __tablename__ = "internal_statuses"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    new_status: Mapped[str] = mapped_column(ForeignKey("internal_statuses.name"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_by_user: Mapped[User | None] = relationship()


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("order_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    order: Mapped[Order] = relationship(back_populates="assignment")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    author: Mapped[User | None] = relationship()
    mentions: Mapped[list["CommentMention"]] = relationship(cascade="all, delete-orphan")


class CommentMention(Base):
    __tablename__ = "comment_mentions"

    comment_id: Mapped[int] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)


class OrderTimelineEvent(Base):
    __tablename__ = "order_timeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    actor: Mapped[User | None] = relationship()


class BlockerType(Base):
    __tablename__ = "blocker_types"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)


class Blocker(Base):
    __tablename__ = "blockers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    type_code: Mapped[str] = mapped_column(ForeignKey("blocker_types.code"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    creator_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expected_resolution_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_production_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    order: Mapped[Order] = relationship()
    creator: Mapped[User | None] = relationship(foreign_keys=[creator_user_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assigned_to])


class ManagerTask(Base):
    __tablename__ = "manager_tasks"
    __table_args__ = (UniqueConstraint("source_type", "source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order: Mapped[Order | None] = relationship()
    assignee: Mapped[User | None] = relationship(foreign_keys=[assigned_to])


class ProcurementTask(Base):
    __tablename__ = "procurement_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_name: Mapped[str] = mapped_column(String(240), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="NEW")
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    needed_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responsible_user: Mapped[User | None] = relationship()
    order_links: Mapped[list["ProcurementOrderLink"]] = relationship(cascade="all, delete-orphan")
    blocker_links: Mapped[list["ProcurementBlockerLink"]] = relationship(cascade="all, delete-orphan")


class ProcurementOrderLink(Base):
    __tablename__ = "procurement_order_links"
    task_id: Mapped[int] = mapped_column(ForeignKey("procurement_tasks.id", ondelete="CASCADE"), primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True)


class ProcurementBlockerLink(Base):
    __tablename__ = "procurement_blocker_links"
    task_id: Mapped[int] = mapped_column(ForeignKey("procurement_tasks.id", ondelete="CASCADE"), primary_key=True)
    blocker_id: Mapped[int] = mapped_column(ForeignKey("blockers.id", ondelete="CASCADE"), primary_key=True)


class ProcurementHistory(Base):
    __tablename__ = "procurement_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("procurement_tasks.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    old_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    actor: Mapped[User | None] = relationship()
