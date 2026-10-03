"""Read private key=value data without executing shell syntax or logging secrets."""
import argparse
import os
import re
import subprocess
from pathlib import Path


def read_env(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or "\x00" in value:
            raise ValueError("Invalid private env format")
        values[key] = value
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    parser.add_argument("action", choices=["run", "public", "provision", "check"])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    values = read_env(args.file)
    if args.action == "public":
        host = values["DOMAIN"]
        if not re.fullmatch(r"[a-z0-9.-]+", host) or "." not in host:
            parser.error("Invalid public host")
        print(host)
        return
    if args.action == "check":
        # Runs with the release interpreter, before migrations/startup.
        from sqlalchemy.engine import make_url

        from app.config import Settings

        settings = Settings(_env_file=None, **{k.lower(): v for k, v in values.items()})
        db = make_url(settings.database_url)
        if (db.host != "127.0.0.1" or db.port != 5432
                or db.username != values["POSTGRES_USER"] or db.database != values["POSTGRES_DB"]
                or db.password != values["POSTGRES_PASSWORD"]):
            raise SystemExit("Private application/backup database settings must match local PostgreSQL")
        return
    if args.action == "provision":
        user, db = values["POSTGRES_USER"], values["POSTGRES_DB"]
        if not all(re.fullmatch(r"[a-z][a-z0-9_]{0,30}", x) for x in (user, db)):
            parser.error("Invalid DB identifiers")
        if user in ("postgres", "root") or db in ("postgres", "template0", "template1"):
            parser.error("Reserved DB identifiers")
        password = values["POSTGRES_PASSWORD"].replace("'", "''")
        # stdin only; password never enters argv, shell history or command output.
        sql = rf"""SET log_statement = 'none';
SET log_min_error_statement = 'panic';
SELECT 'CREATE ROLE {user} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{user}')\gexec
ALTER ROLE {user} PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
SELECT 'CREATE DATABASE {db} OWNER {user}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='{db}')\gexec
REVOKE ALL ON DATABASE {db} FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE {db} TO {user};
\connect {db}
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO {user};
"""
        result = subprocess.run(["runuser", "-u", "postgres", "--", "psql", "-X",
                                 "-v", "ON_ERROR_STOP=1", "-d", "postgres"],
                                input=sql, text=True, capture_output=True, check=False)
        if result.returncode:
            raise SystemExit("Database provisioning failed; output suppressed to protect credentials")
        return
    env = os.environ | values
    env.update(PGHOST="127.0.0.1", PGPORT="5432", PGDATABASE=values["POSTGRES_DB"],
               PGUSER=values["POSTGRES_USER"], PGPASSWORD=values["POSTGRES_PASSWORD"])
    drill = os.environ.get("NATIVE_DRILL_ROOT")
    if drill:
        if (not drill.startswith("/tmp/ozon-native-drill-") or values.get("APP_ENV") != "test"
                or values["POSTGRES_DB"] != "ozon_drill" or values["POSTGRES_USER"] != "ozon_drill"):
            parser.error("Invalid isolated native drill environment")
        env["PGHOST"] = drill + "/socket"
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("Missing command")
    if command[0] == "pg_restore" and "--list" not in command:
        command += ["--dbname", values["POSTGRES_DB"]]
    raise SystemExit(subprocess.run(command, env=env, check=False).returncode)


if __name__ == "__main__":
    main()
