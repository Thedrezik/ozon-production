from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from app.auth import (
    COOKIE_NAME,
    SESSION_SECONDS,
    Current,
    Db,
    _dummy_hash,
    create_session,
    hash_password,
    login_limiter,
    require,
    verify_password,
)
from app.models import AuditLog, Role, Session, User
from app.rbac import user_permissions

router = APIRouter(prefix="/api")


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=1024)


class PasswordInput(BaseModel):
    current_password: str
    new_password: str


class CreateUserInput(BaseModel):
    username: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=1024)
    roles: list[str] = Field(min_length=1)


class RolesInput(BaseModel):
    roles: list[str] = Field(min_length=1)


class ResetPasswordInput(BaseModel):
    new_password: str = Field(min_length=12, max_length=1024)


def user_data(user: User, csrf_token: str | None = None) -> dict:
    result = {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "roles": sorted(role.name for role in user.roles),
        "permissions": sorted(user_permissions(user)),
    }
    if csrf_token is not None:
        result["csrf_token"] = csrf_token
    return result


def audit(db: DbSession, action: str, actor: int | None, target: int | None = None) -> None:
    entity = target if target is not None else actor
    db.add(AuditLog(action=action, actor_user_id=actor, target_user_id=target,
                    entity_type="users" if entity is not None else None,
                    entity_id=str(entity) if entity is not None else None))


def chosen_roles(db: DbSession, names: list[str], actor: User) -> list[Role]:
    unique = set(names)
    roles = db.scalars(select(Role).where(Role.name.in_(unique))).all()
    if len(roles) != len(unique):
        raise HTTPException(422, "Unknown role")
    if "SUPER_ADMIN" in unique and "SUPER_ADMIN" not in {role.name for role in actor.roles}:
        raise HTTPException(403, "Only a super admin can assign this role")
    return roles


def protect_super_admin(target: User, actor: User) -> None:
    if "SUPER_ADMIN" in {role.name for role in target.roles} and "SUPER_ADMIN" not in {role.name for role in actor.roles}:
        raise HTTPException(403, "Only a super admin can manage this user")


def ensure_super_admin_remains(db: DbSession, target: User) -> None:
    if "SUPER_ADMIN" not in {role.name for role in target.roles} or not target.is_active:
        return
    others = db.scalar(
        select(func.count(User.id)).join(User.roles).where(
            Role.name == "SUPER_ADMIN", User.is_active.is_(True), User.id != target.id
        )
    )
    if not others:
        raise HTTPException(409, "The last active super admin cannot be removed")


@router.post("/auth/login")
def login(payload: LoginInput, request: Request, response: Response, db: Db) -> dict:
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "Invalid origin")
    username = payload.username.strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{username}"
    login_limiter.check(key)
    user = db.scalar(
        select(User).options(selectinload(User.roles).selectinload(Role.permissions)).where(User.username == username)
    )
    valid = verify_password(user.password_hash if user else _dummy_hash, payload.password)
    if user is None or not user.is_active or not valid:
        login_limiter.failure(key)
        audit(db, "login.failure", user.id if user else None)
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    login_limiter.success(key)
    token, session = create_session(db, user)
    audit(db, "login.success", user.id)
    db.commit()
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True,
        secure=request.app.state.secure_cookies, samesite="strict", path="/api",
    )
    return user_data(user, session.csrf_token)


@router.post("/auth/logout")
def logout(response: Response, db: Db, current: Current) -> dict[str, str]:
    user, session = current
    db.delete(session)
    audit(db, "logout", user.id)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/api")
    return {"status": "ok"}


@router.get("/auth/me")
def me(current: Current) -> dict:
    user, session = current
    return user_data(user, session.csrf_token)


@router.post("/auth/change-password")
def change_password(payload: PasswordInput, db: Db, current: Current) -> dict[str, str]:
    user, session = current
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(400, "Current password is incorrect")
    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    db.execute(delete(Session).where(Session.user_id == user.id, Session.id != session.id))
    audit(db, "password.changed", user.id, user.id)
    db.commit()
    return {"status": "ok"}


@router.get("/users")
def list_users(
    db: Db,
    _actor: Annotated[User, Depends(require("users.view"))],
    limit: int = 50,
    offset: int = 0,
) -> dict:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Invalid pagination")
    users = db.scalars(
        select(User).options(selectinload(User.roles).selectinload(Role.permissions))
        .order_by(User.id).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count(User.id))) or 0
    return {"items": [user_data(user) for user in users], "total": total}


@router.get("/roles")
def list_roles(db: Db, _actor: Annotated[User, Depends(require("users.view"))]) -> list[str]:
    return db.scalars(select(Role.name).order_by(Role.name)).all()


@router.post("/users", status_code=201)
def create_user(
    payload: CreateUserInput, db: Db,
    actor: Annotated[User, Depends(require("users.create"))],
) -> dict:
    username = payload.username.lower()
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise HTTPException(409, "Username already exists")
    roles = chosen_roles(db, payload.roles, actor)
    user = User(
        username=username, display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password), roles=roles,
    )
    if not user.display_name:
        raise HTTPException(422, "Display name is required")
    db.add(user)
    db.flush()
    audit(db, "user.created", actor.id, user.id)
    db.commit()
    return user_data(user)


@router.put("/users/{user_id}/roles")
def set_roles(
    user_id: int, payload: RolesInput, db: Db,
    actor: Annotated[User, Depends(require("users.manage"))],
) -> dict:
    user = db.scalar(select(User).options(selectinload(User.roles).selectinload(Role.permissions)).where(User.id == user_id))
    if user is None:
        raise HTTPException(404, "User not found")
    protect_super_admin(user, actor)
    roles = chosen_roles(db, payload.roles, actor)
    if "SUPER_ADMIN" in {r.name for r in user.roles} and "SUPER_ADMIN" not in {r.name for r in roles}:
        ensure_super_admin_remains(db, user)
    user.roles = roles
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, "role.changed", actor.id, user.id)
    db.commit()
    return user_data(user)


@router.post("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: int, db: Db,
    actor: Annotated[User, Depends(require("users.manage"))],
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    protect_super_admin(user, actor)
    if user.id == actor.id:
        raise HTTPException(409, "Cannot deactivate yourself")
    ensure_super_admin_remains(db, user)
    if user.is_active:
        user.is_active = False
        db.execute(delete(Session).where(Session.user_id == user.id))
        audit(db, "user.deactivated", actor.id, user.id)
        db.commit()
    return user_data(user)


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int, payload: ResetPasswordInput, db: Db,
    actor: Annotated[User, Depends(require("users.manage"))],
) -> dict[str, str]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    protect_super_admin(user, actor)
    user.password_hash = hash_password(payload.new_password)
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, "password.reset", actor.id, user.id)
    db.commit()
    return {"status": "ok"}
