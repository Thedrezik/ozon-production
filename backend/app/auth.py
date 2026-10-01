import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from app.models import Role, Session, User, utc_now
from app.rbac import user_permissions

COOKIE_NAME = "ozon_session"
SESSION_SECONDS = 12 * 60 * 60
SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1


def _scrypt(password: str, salt: bytes, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=64 * 1024 * 1024)


_dummy_hash = None


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Password must contain 12-1024 characters")
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password_hash: str, password: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = password_hash.split("$")
        if algorithm != "scrypt" or (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        return secrets.compare_digest(_scrypt(password, bytes.fromhex(salt)), bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


_dummy_hash = hash_password("invalid-password")


def get_db(request: Request):
    with DbSession(request.app.state.engine) as db:
        db.info["audit_context"] = {"ip": request.client.host if request.client else None,
                                    "user_agent": request.headers.get("user-agent", "")[:512]}
        yield db


Db = Annotated[DbSession, Depends(get_db)]


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def create_session(db: DbSession, user: User) -> tuple[str, Session]:
    token = secrets.token_urlsafe(32)
    session = Session(
        user_id=user.id,
        token_hash=token_digest(token),
        csrf_token=secrets.token_urlsafe(32),
        expires_at=utc_now() + timedelta(seconds=SESSION_SECONDS),
    )
    db.add(session)
    db.flush()
    return token, session


def authenticated(request: Request, db: Db) -> tuple[User, Session]:
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 128:
        raise HTTPException(401, "Authentication required")
    session = db.scalar(select(Session).where(Session.token_hash == token_digest(token)))
    if session is None:
        raise HTTPException(401, "Authentication required")
    expiry = session.expires_at.replace(tzinfo=timezone.utc) if session.expires_at.tzinfo is None else session.expires_at
    if expiry <= utc_now():
        db.delete(session)
        db.commit()
        raise HTTPException(401, "Session expired")
    user = db.scalar(
        select(User).options(selectinload(User.roles).selectinload(Role.permissions)).where(User.id == session.user_id)
    )
    if user is None or not user.is_active:
        raise HTTPException(401, "Authentication required")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not secrets.compare_digest(csrf, session.csrf_token):
            raise HTTPException(403, "Invalid CSRF token")
    db.info["audit_context"]["actor_user_id"] = user.id
    return user, session


Current = Annotated[tuple[User, Session], Depends(authenticated)]


def require(permission: str):
    def check(current: Current) -> User:
        user, _session = current
        if permission not in user_permissions(user):
            raise HTTPException(403, "Permission denied")
        return user
    return check


class LoginLimiter:
    """Small bounded per-process limiter; deployment has one API worker."""

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            if len(self._attempts) > 4096:
                self._attempts = defaultdict(deque, {k: v for k, v in self._attempts.items() if v and v[-1] > now - 900})
            attempts = self._attempts[key]
            while attempts and attempts[0] <= now - 900:
                attempts.popleft()
            if len(attempts) >= 5:
                raise HTTPException(429, "Too many login attempts")

    def failure(self, key: str) -> None:
        with self._lock:
            self._attempts[key].append(time.monotonic())

    def success(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


login_limiter = LoginLimiter()
