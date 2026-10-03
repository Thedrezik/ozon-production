#!/usr/bin/env bash
# Real native PostgreSQL drill: separate initdb cluster, private Unix socket,
# synthetic env and migrations; no production credentials or TCP listeners.
set -Eeuo pipefail
[[ $(uname -s) == Linux && $EUID == 0 ]] || { echo 'Run on Linux through sudo.' >&2; exit 1; }
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PG_BIN=/usr/lib/postgresql/15/bin
VENV=${DRILL_VENV:-/opt/ozon-production/current/.venv}
CODE=${DRILL_CODE:-/opt/ozon-production/current}
[[ -x $VENV/bin/python && -f $CODE/backend/alembic.ini ]]
umask 077
work=$(mktemp -d /tmp/ozon-native-drill-XXXXXX)
export NATIVE_DRILL_ROOT=$work
export MIN_FREE_BYTES=268435456
mkdir "$work/app" "$work/private" "$work/uploads" "$work/backups" "$work/socket"
chown postgres:postgres "$work" "$work/socket"
started=false
cleanup() {
  result=$?; trap - EXIT
  if [[ $started == true ]]; then
    runuser -u postgres -- "$PG_BIN/pg_ctl" -D "$work/pgdata" -m fast -w stop || result=1
  fi
  # Only the absolute mktemp-created root is ever removed.
  if [[ $work == /tmp/ozon-native-drill-* && -d $work && ! -L $work && $result == 0 ]]; then
    rm -rf -- "$work"
  else
    echo "Drill failed; retain isolated evidence at $work. Launch remains blocked." >&2
  fi
  exit "$result"
}
trap cleanup EXIT
runuser -u postgres -- "$PG_BIN/initdb" -D "$work/pgdata" -U ozon_drill --auth-local=trust --auth-host=reject >/dev/null
runuser -u postgres -- "$PG_BIN/pg_ctl" -D "$work/pgdata" -l "$work/postgres.log" -o "-c listen_addresses='' -c unix_socket_directories='$work/socket' -c shared_buffers=16MB -c max_connections=10" -w start >/dev/null
started=true
"$PG_BIN/createdb" -h "$work/socket" -U ozon_drill ozon_drill
cat > "$work/private/test.env" <<EOF
APP_ENV=test
OZON_MOCK_MODE=true
POSTGRES_USER=ozon_drill
POSTGRES_DB=ozon_drill
POSTGRES_PASSWORD=synthetic-only
DATABASE_URL=postgresql+psycopg://ozon_drill@/ozon_drill?host=$work/socket
OZON_RECONCILIATION_ENABLED=false
OZON_WEBHOOK_ENABLED=false
OZON_CLIENT_ID=
OZON_API_KEY=
OZON_CREDENTIALS_MASTER_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
TELEGRAM_WEBHOOK_SECRET=
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=
ENABLED_OPTIONAL_FEATURES=
UPLOAD_DIR=$work/uploads
EOF
chmod 600 "$work/private/test.env"
source "$SCRIPT_DIR/native-common.sh"
native_require
cd "$CODE/backend"
env_run "$VENV/bin/python" -m alembic upgrade head
sql() { env_run psql -X -v ON_ERROR_STOP=1 -Atc "$1"; }
sql "CREATE TABLE backup_drill_probe (id integer PRIMARY KEY, marker text NOT NULL); INSERT INTO backup_drill_probe VALUES (1,'before-backup');" >/dev/null
printf upload-before > "$UPLOAD_DIR/probe.txt"
bash "$SCRIPT_DIR/backup.sh" > "$work/backup-output"
archive=$(sed -n 's/^Backup created: .*\/\(backup-[^ ]*\).*/\1/p' "$work/backup-output")
sql "UPDATE backup_drill_probe SET marker='after-backup'; INSERT INTO backup_drill_probe VALUES (2,'new');" >/dev/null
[[ $(sql 'SELECT marker FROM backup_drill_probe WHERE id=1') == after-backup ]]
[[ $(sql 'SELECT count(*) FROM backup_drill_probe') == 2 ]]
printf changed > "$UPLOAD_DIR/probe.txt"
printf extra > "$UPLOAD_DIR/after.txt"
[[ $(cat "$UPLOAD_DIR/probe.txt") == changed && -f $UPLOAD_DIR/after.txt ]]
bash "$SCRIPT_DIR/restore.sh" "$archive" --yes
[[ $(sql 'SELECT marker FROM backup_drill_probe WHERE id=1') == before-backup ]]
[[ $(sql 'SELECT count(*) FROM backup_drill_probe') == 1 ]]
[[ $(cat "$UPLOAD_DIR/probe.txt") == upload-before && ! -e $UPLOAD_DIR/after.txt ]]
env_run "$VENV/bin/python" -m alembic upgrade head
export RETENTION_COUNT=2
for n in 1 2 3; do sleep 1; bash "$SCRIPT_DIR/backup.sh" > "$work/retention-$n"; done
[[ $(find "$BACKUP_DIR" -name 'backup-*.tar.gz' | wc -l) == 2 ]]
[[ ! -e $BACKUP_DIR/$archive ]]
for n in 2 3; do sed -n 's/^Backup created: .*\/\(backup-[^ ]*\).*/\1/p' "$work/retention-$n"; done | sort > "$work/expected"
find "$BACKUP_DIR" -name 'backup-*.tar.gz' -printf '%f\n' | sort > "$work/actual"
diff -u "$work/expected" "$work/actual"
echo 'PASS: native isolated migrations, pg_dump, DB/uploads mutation+restore, newest retention; no production cluster/paths accessed.'
