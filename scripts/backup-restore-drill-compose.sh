#!/usr/bin/env bash
# Real Linux/PostgreSQL drill; no operational data/credentials, no published ports.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ $(uname -s) == Linux ]] || { echo 'A real Linux host is required; Windows/MSYS is not acceptance.' >&2; exit 1; }
for utility in docker python3 bash tar diff; do command -v "$utility" >/dev/null; done
docker info >/dev/null
if [[ -n "${DRILL_BACKEND_IMAGE:-}" ]]; then
  # Reuse the loaded immutable release image on the small VPS. Never build/tag
  # over it, and never mount its production volumes or load production env.
  docker image inspect "$DRILL_BACKEND_IMAGE" >/dev/null
fi
umask 077
work=$(mktemp -d)
prefix="ozon-backup-drill-$(date -u +%Y%m%d%H%M%S)-$(python3 -c 'import secrets; print(secrets.token_hex(5))')"
export COMPOSE_PROJECT_NAME="$prefix" DRILL_VOLUME_PREFIX="$prefix" BACKUP_RESTORE_DRILL=true
export COMPOSE_FILE=docker-compose.yml COMPOSE_OVERRIDE_FILE=docker-compose.backup-drill.yml
export APP_ENV_FILE="$work/test.env" COMPOSE_ENV_FILES="$work/test.env"
export APP_ENV=test OZON_MOCK_MODE=true DOMAIN=:80
export POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
export DATABASE_URL="postgresql+psycopg://ozon:$POSTGRES_PASSWORD@postgres:5432/ozon"
export OZON_RECONCILIATION_ENABLED=false OZON_WEBHOOK_ENABLED=false
export OZON_API_KEY= OZON_CLIENT_ID= TELEGRAM_BOT_TOKEN= TELEGRAM_BOT_USERNAME= TELEGRAM_WEBHOOK_SECRET=
export VAPID_PUBLIC_KEY= VAPID_PRIVATE_KEY= VAPID_SUBJECT= OZON_CREDENTIALS_MASTER_KEY=
export UPLOAD_DIR=/data/uploads BACKUP_DIR=/data/backups
python3 - "$APP_ENV_FILE" <<'PY'
import os,sys
keys='APP_ENV OZON_MOCK_MODE DOMAIN POSTGRES_PASSWORD DATABASE_URL OZON_RECONCILIATION_ENABLED OZON_WEBHOOK_ENABLED OZON_API_KEY OZON_CLIENT_ID TELEGRAM_BOT_TOKEN TELEGRAM_BOT_USERNAME TELEGRAM_WEBHOOK_SECRET VAPID_PUBLIC_KEY VAPID_PRIVATE_KEY VAPID_SUBJECT OZON_CREDENTIALS_MASTER_KEY UPLOAD_DIR BACKUP_DIR'.split()
with open(sys.argv[1],'w') as f:
    f.writelines(key+'='+os.environ[key]+'\n' for key in keys)
PY
compose=(docker compose --env-file "$APP_ENV_FILE" -p "$prefix" -f "$COMPOSE_FILE" -f "$COMPOSE_OVERRIDE_FILE")
guard() { "${compose[@]}" config --format json | python3 scripts/check-drill-config.py "$prefix" > "$work/drill-volumes"; }
started=false
stage=initialization
cleanup() {
  result=$?; trap - EXIT
  if [[ "$started" == true ]]; then
    if guard; then
      "${compose[@]}" down --volumes --remove-orphans || result=1
    else
      echo 'Cleanup guard failed; inspect isolated resources manually.' >&2; result=1
    fi
  fi
  [[ "$result" == 0 ]] || echo "FAIL during $stage; launch remains blocked." >&2
  rm -rf -- "$work"
  exit "$result"
}
trap cleanup EXIT
guard
# Snapshot ALL existing volumes, not a hardcoded production project name.
docker volume ls -q | sort > "$work/existing-volumes"
while IFS= read -r name; do
  [[ -n "$name" ]] || continue
  docker volume inspect "$name" --format '{{.Name}}|{{.CreatedAt}}|{{.Mountpoint}}'
done < "$work/existing-volumes" > "$work/before"
while IFS= read -r name; do
  ! grep -Fxq "$name" "$work/existing-volumes" || { echo 'Drill volume already exists; refusing reuse.' >&2; exit 1; }
done < "$work/drill-volumes"
stage=migrations
started=true
"${compose[@]}" up -d --wait --wait-timeout 90 postgres
if [[ -z "${DRILL_BACKEND_IMAGE:-}" ]]; then
  "${compose[@]}" build backend
fi
"${compose[@]}" run --rm --no-deps -T backend alembic upgrade head
"${compose[@]}" up -d --no-build --wait --wait-timeout 90 backend
sql() { "${compose[@]}" exec -T postgres psql -U ozon -d ozon -v ON_ERROR_STOP=1 -Atc "$1"; }
sql "CREATE TABLE backup_drill_probe (id integer PRIMARY KEY, marker text NOT NULL); INSERT INTO backup_drill_probe VALUES (1, 'before-backup');"
"${compose[@]}" exec -T backend sh -ec 'printf %s upload-before-backup > /data/uploads/backup-drill-probe.txt'
stage=backup
bash scripts/backup-compose.sh | tee "$work/backup-output"
archive=$(sed -n 's/^Backup created: .*\/\(backup-[^ ]*\).*/\1/p' "$work/backup-output")
[[ -n "$archive" ]]
"${compose[@]}" exec -T backend tar -tzf "/data/backups/$archive" | sort > "$work/members"
printf '%s\n' README.txt database.dump uploads.tar.gz | sort > "$work/expected"
diff -u "$work/expected" "$work/members"
"${compose[@]}" exec -T backend sh -ec 'tar -xOzf "/data/backups/$1" uploads.tar.gz | tar -tzf -' sh "$archive" | grep -Fx './backup-drill-probe.txt'
stage=mutation
sql "UPDATE backup_drill_probe SET marker='after-backup' WHERE id=1; INSERT INTO backup_drill_probe VALUES (2, 'post-backup-row');"
[[ $(sql 'SELECT marker FROM backup_drill_probe WHERE id=1') == after-backup ]]
[[ $(sql 'SELECT count(*) FROM backup_drill_probe') == 2 ]]
"${compose[@]}" exec -T backend sh -ec 'printf %s changed-upload > /data/uploads/backup-drill-probe.txt; printf %s post-backup > /data/uploads/backup-drill-after.txt; test "$(cat /data/uploads/backup-drill-probe.txt)" = changed-upload; test -f /data/uploads/backup-drill-after.txt'
stage=restore
guard
"${compose[@]}" stop backend
bash scripts/restore-compose.sh "$archive" --yes
"${compose[@]}" run --rm --no-deps -T backend alembic upgrade head
"${compose[@]}" up -d --no-build --wait --wait-timeout 90 backend
[[ $(sql 'SELECT marker FROM backup_drill_probe WHERE id=1') == before-backup ]]
[[ $(sql 'SELECT count(*) FROM backup_drill_probe') == 1 ]]
"${compose[@]}" exec -T backend sh -ec 'test "$(cat /data/uploads/backup-drill-probe.txt)" = upload-before-backup; test ! -e /data/uploads/backup-drill-after.txt'
stage=retention
export RETENTION_COUNT=2
for n in 1 2 3; do sleep 1; bash scripts/backup-compose.sh > "$work/retention-$n"; done
"${compose[@]}" exec -T backend sh -ec 'original=$1; set -- /data/backups/backup-*.tar.gz; test "$#" -eq 2; test ! -e "/data/backups/$original"' sh "$archive"
# Exact newest filenames, not just archive count.
for n in 2 3; do sed -n 's/^Backup created: .*\/\(backup-[^ ]*\).*/\1/p' "$work/retention-$n"; done | sort > "$work/newest"
"${compose[@]}" exec -T backend sh -ec 'for f in /data/backups/backup-*.tar.gz; do basename "$f"; done' | sort > "$work/retained"
diff -u "$work/newest" "$work/retained"
stage=cleanup
guard
"${compose[@]}" down --volumes --remove-orphans
started=false
docker volume ls -q | sort > "$work/after-volumes"
diff -u "$work/existing-volumes" "$work/after-volumes"
while IFS= read -r name; do
  [[ -n "$name" ]] || continue
  docker volume inspect "$name" --format '{{.Name}}|{{.CreatedAt}}|{{.Mountpoint}}'
done < "$work/existing-volumes" > "$work/after"
diff -u "$work/before" "$work/after"
echo "PASS $(date -u +%FT%TZ): $prefix; migrations, real pg_dump/pg_restore, bundle publication, restored DB/upload, post-backup row/file removal, newest retention, isolated cleanup, all pre-existing volumes preserved."
