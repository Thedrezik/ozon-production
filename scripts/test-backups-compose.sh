#!/usr/bin/env bash
set -Eeuo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
bash_bin=$(command -v bash)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/uploads" "$tmp/backups"
printf 'synthetic upload\n' >"$tmp/uploads/photo.txt"
cat >"$tmp/bin/docker" <<'MOCK_DOCKER'
#!/usr/bin/env bash
set -Eeuo pipefail
[[ $1 == compose ]] || exit 90
shift
while [[ $1 == -f ]]; do shift 2; done
case "$1" in
  exec) shift; [[ $1 == -T ]] && shift ;;
  run) shift; while [[ $1 == -* ]]; do shift; done; [[ $1 == -T ]] && shift ;;
  *) exit 91 ;;
esac
service=$1; shift
if [[ $service == postgres ]]; then
  case "$1" in
    sh) [[ ${FAIL_DB:-false} == true ]] && exit 1; printf 'synthetic-postgres-dump' ;;
    pg_restore)
      for arg do [[ "$arg" != - ]] || { echo 'pg_restore must not receive filename -' >&2; exit 94; }; done
      [[ "${FAIL_VALIDATION:-false}" != true ]] || exit 95
      IFS= read -r -n 23 data || true; [[ "$data" == synthetic-postgres-dump ]] ;;
    *) exit 92 ;;
  esac
else
  case "$1" in
    tar) shift; exec tar "$@" ;;
    sh)
      shift
      if [[ ${FAIL_UPLOAD_EXTRACT:-false} == true && "$*" == *promoting=0* ]]; then
        printf invalid | sh "$@"
      else
        exec sh "$@"
      fi ;;
    *) exit 93 ;;
  esac
fi
MOCK_DOCKER
chmod +x "$tmp/bin/docker"
export PATH="$tmp/bin:$PATH" COMPOSE_FILE="$root/docker-compose.yml" BACKUP_DIR="$tmp/backups" UPLOAD_DIR="$tmp/uploads" RETENTION_COUNT=2

bash -n "$root/scripts/backup-compose.sh" "$root/scripts/restore-compose.sh" "$root/scripts/test-backups.sh"
first=$(bash "$root/scripts/backup-compose.sh")
archive=$(printf '%s\n' "$first" | sed -n 's/^Backup created: .*\/\(backup-[^ ]*\).*/\1/p')
[[ -n "$archive" && -s "$tmp/backups/$archive" ]]
tar -tzf "$tmp/backups/$archive" | sort >"$tmp/outer.list"
printf '%s\n' README.txt database.dump uploads.tar.gz | sort >"$tmp/expected.list"
diff -u "$tmp/expected.list" "$tmp/outer.list"
tar -xOzf "$tmp/backups/$archive" uploads.tar.gz >"$tmp/uploads.tar.gz"
tar -tzf "$tmp/uploads.tar.gz" | grep -Fx './photo.txt' >/dev/null

sleep 1; bash "$root/scripts/backup-compose.sh" >/dev/null
sleep 1; bash "$root/scripts/backup-compose.sh" >/dev/null
[[ $(find "$tmp/backups" -name 'backup-*.tar.gz' | wc -l) -eq 2 ]]
[[ ! -e "$tmp/backups/$archive" ]]
archive=$(find "$tmp/backups" -name 'backup-*.tar.gz' -printf '%f\n' | sort -r | head -n 1)

if printf 'n\n' | bash "$root/scripts/restore-compose.sh" "$archive" >/dev/null 2>&1; then
  echo 'restore unexpectedly accepted missing confirmation' >&2; exit 1
fi
if bash "$root/scripts/restore-compose.sh" "$archive" >"$tmp/restore.out" 2>&1; then
  echo 'restore unexpectedly accepted noninteractive execution without confirmation' >&2; exit 1
fi
grep -q 'confirmation required' "$tmp/restore.out"
if bash "$root/scripts/restore-compose.sh" "$archive" --yes >"$tmp/yes.out" 2>&1; then
  echo 'restore unexpectedly accepted --yes outside isolated drill mode' >&2; exit 1
fi
grep -q -- '--yes is reserved for the automated isolated drill' "$tmp/yes.out"
if PATH="$tmp/bin" COMPOSE_FILE="$COMPOSE_FILE" BACKUP_DIR="$BACKUP_DIR" UPLOAD_DIR="$UPLOAD_DIR" \
   "$bash_bin" "$root/scripts/backup-compose.sh" >"$tmp/fail.out" 2>&1; then
  echo 'backup unexpectedly succeeded without required utilities' >&2; exit 1
fi
grep -q 'required utility not found' "$tmp/fail.out"

mkdir "$tmp/db-failure"
if FAIL_DB=true BACKUP_DIR="$tmp/db-failure" bash "$root/scripts/backup-compose.sh" >"$tmp/db.out" 2>&1; then
  echo 'backup unexpectedly succeeded with unavailable database' >&2; exit 1
fi
[[ -z $(find "$tmp/db-failure" -type f -print -quit) ]]
grep -q 'PostgreSQL dump failed' "$tmp/db.out"
if FAIL_VALIDATION=true bash "$root/scripts/restore-compose.sh" "$archive" >"$tmp/validation.out" 2>&1; then
  echo 'restore accepted invalid PostgreSQL dump' >&2; exit 1
fi
grep -q 'database dump failed validation' "$tmp/validation.out"

# Exercise actual upload extraction and rollback in isolated local directories.
printf 'changed upload\n' >"$tmp/uploads/photo.txt"
printf 'post-backup upload\n' >"$tmp/uploads/after.txt"
export BACKUP_RESTORE_DRILL=true COMPOSE_OVERRIDE_FILE=docker-compose.backup-drill.yml DRILL_VOLUME_PREFIX=ozon-backup-drill-test COMPOSE_PROJECT_NAME=ozon-backup-drill-test
if FAIL_UPLOAD_EXTRACT=true bash "$root/scripts/restore-compose.sh" "$archive" --uploads-only --yes >"$tmp/upload-failure.out" 2>&1; then
  echo 'restore accepted corrupted upload stream' >&2; exit 1
fi
[[ $(cat "$tmp/uploads/photo.txt") == 'changed upload' && -f "$tmp/uploads/after.txt" ]]
bash "$root/scripts/restore-compose.sh" "$archive" --uploads-only --yes >/dev/null
[[ $(cat "$tmp/uploads/photo.txt") == 'synthetic upload' && ! -e "$tmp/uploads/after.txt" ]]
echo 'backup shell checks passed (syntax, synthetic creation, retention, archive structure, confirmation, guarded --yes, utility and database failures)'
