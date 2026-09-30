import argparse
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import get_settings
from app.database import create_db_engine
from app.models import AuditLog, Role, User
from app.orders import seed_mock_orders


def create_admin(username: str, display_name: str, password: str, db: Session) -> User:
    username = username.strip().lower()
    if not username or len(username) > 80 or not all(c.isascii() and (c.isalnum() or c in "_.-") for c in username):
        raise ValueError("Invalid username")
    if not display_name.strip() or len(display_name) > 160:
        raise ValueError("Invalid display name")
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise ValueError("Username already exists")
    role = db.scalar(select(Role).where(Role.name == "SUPER_ADMIN"))
    if role is None:
        raise ValueError("Run database migrations first")
    user = User(username=username, display_name=display_name.strip(), password_hash=hash_password(password), roles=[role])
    db.add(user)
    db.flush()
    db.add(AuditLog(action="user.created", target_user_id=user.id, detail="cli.bootstrap"))
    db.commit()
    return user


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="Create a super admin using an interactive password prompt")
    admin.add_argument("--username")
    admin.add_argument("--display-name")
    commands.add_parser("seed-mock-orders", help="Create repeatable development orders (mock mode only)")
    args = parser.parse_args()
    if args.command == "seed-mock-orders":
        settings = get_settings()
        if not settings.ozon_mock_mode or settings.app_env == "production":
            print("Mock seed requires OZON_MOCK_MODE=true outside production", file=sys.stderr)
            return 1
        engine = create_db_engine(settings.database_url)
        try:
            with Session(engine) as db:
                count = seed_mock_orders(db)
        finally:
            engine.dispose()
        print(f"Created {count} mock orders")
        return 0
    username = args.username or input("Username: ")
    display_name = args.display_name or input("Display name: ")
    password = getpass.getpass("Password (12+ characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        print("Passwords do not match", file=sys.stderr)
        return 1
    engine = create_db_engine(get_settings().database_url)
    try:
        with Session(engine) as db:
            try:
                create_admin(username, display_name, password, db)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
    finally:
        engine.dispose()
    print("Admin created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
