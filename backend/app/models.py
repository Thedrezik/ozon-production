from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
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
    ozon_status: Mapped[str] = mapped_column(String(40), nullable=False)
    internal_status: Mapped[str] = mapped_column(ForeignKey("internal_statuses.name"), nullable=False, index=True)
    shipment_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    assignment: Mapped["Assignment | None"] = relationship(back_populates="order", uselist=False, cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_name: Mapped[str] = mapped_column(String(240), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    order: Mapped[Order] = relationship(back_populates="items")


class InternalStatus(Base):
    __tablename__ = "internal_statuses"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)


class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    new_status: Mapped[str] = mapped_column(ForeignKey("internal_statuses.name"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


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
