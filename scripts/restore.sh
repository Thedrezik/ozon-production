#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.yml}
COMPOSE_OVERRIDE_FILE=${COMPOSE_OVERRIDE_FILE:-}
BACKUP_DIR=${BACKUP_DIR:-/data/backups}
UPLOAD_DIR=${UPLOAD_DIR:-/data/uploads}
POSTGRES_SERVICE=${POSTGRES_SERVICE:-postgres}
BACKEND_SERVICE=${BACKEND_SERVICE:-backend}
usage() { echo "Usage: $0 BACKUP_FILENAME [--database-only | --uploads-only] [--yes]" >&2; exit 2; }
die() { printf 'restore: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "required utility not found: $1"; }
for utility in docker tar mktemp; do need "$utility"; done
[[ -f "$COMPOSE_FILE" ]] || die "Compose file not found: $COMPOSE_FILE"
compose=(docker compose -f "$COMPOSE_FILE")
if [[ -n "$COMPOSE_OVERRIDE_FILE" ]]; then
  [[ -f "$COMPOSE_OVERRIDE_FILE" ]] || die "Compose override file not found: $COMPOSE_OVERRIDE_FILE"
  compose+=(-f "$COMPOSE_OVERRIDE_FILE")
fi
[[ $# -ge 1 ]] || usage
backup_name=$1; shift
[[ "$backup_name" == backup-*.tar.gz && "$backup_name" != */* ]] || die 'provide a backup filename (not a path)'
database=true; uploads=true; yes=false
while (($#)); do
  case "$1" in
    --database-only) uploads=false ;;
    --uploads-only) database=false ;;
    --yes) yes=true ;;
    *) usage ;;
  esac
  shift
done
[[ "$database" == true || "$uploads" == true ]] || usage
if [[ "$yes" == true ]]; then
  [[ "${BACKUP_RESTORE_DRILL:-}" == true ]] || die '--yes is reserved for the automated isolated drill'
  [[ "${COMPOSE_OVERRIDE_FILE:-}" == docker-compose.backup-drill.yml ]] || die '--yes requires the backup drill Compose override'
  [[ "${DRILL_VOLUME_PREFIX:-}" =~ ^ozon-backup-drill-[a-z0-9-]+$ ]] || die '--yes requires a generated drill volume prefix'
  [[ "${COMPOSE_PROJECT_NAME:-}" == "$DRILL_VOLUME_PREFIX" ]] || die '--yes requires the drill-specific Compose project'
fi
stage=$(mktemp -d)
cleanup() { rm -rf -- "$stage"; }
trap cleanup EXIT

"${compose[@]}" run --rm --no-deps -T "$BACKEND_SERVICE" sh -ec \
  'cat "$1/$2"' sh "$BACKUP_DIR" "$backup_name" >"$stage/$backup_name" || die 'cannot read backup from persistent volume'
tar -tzf "$stage/$backup_name" >/dev/null || die 'backup archive is invalid'
tar -xzf "$stage/$backup_name" -C "$stage" database.dump uploads.tar.gz README.txt || die 'backup contents are incomplete'
if [[ "$database" == true ]]; then
  [[ -s "$stage/database.dump" ]] || die 'database dump is missing or empty'
  # pg_restore reads stdin when no input filename is supplied. A literal '-'
  # is an ordinary filename for this utility, not a stdin sentinel.
  "${compose[@]}" exec -T "$POSTGRES_SERVICE" pg_restore --list <"$stage/database.dump" >/dev/null || die 'database dump failed validation'
fi
if [[ "$uploads" == true ]]; then
  [[ -s "$stage/uploads.tar.gz" ]] || die 'uploads archive is missing or empty'
  tar -tzf "$stage/uploads.tar.gz" >/dev/null || die 'uploads archive is invalid'
fi

printf 'WARNING: restore replaces database objects from the dump in one transaction; uploads restore replaces files under %s. Stop the application first.\n' "$UPLOAD_DIR" >&2
if [[ "$yes" != true ]]; then
  [[ -t 0 ]] || die 'confirmation required; rerun interactively or pass --yes'
  printf 'Type RESTORE to continue: ' >&2
  IFS= read -r answer
  [[ "$answer" == RESTORE ]] || die 'restore cancelled'
fi

if [[ "$database" == true ]]; then
  printf 'Restoring PostgreSQL database...\n'
  "${compose[@]}" exec -T "$POSTGRES_SERVICE" sh -ec \
    'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore --single-transaction --exit-on-error --clean --if-exists --no-owner --no-privileges --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
    <"$stage/database.dump" || die 'database restore failed'
fi
if [[ "$uploads" == true ]]; then
  printf 'Replacing uploads...\n'
  "${compose[@]}" run --rm --no-deps -T "$BACKEND_SERVICE" sh -ec \
    'target=$1; mkdir -p "$target"; work=$(mktemp -d "$target/.restore.XXXXXX")
     mkdir "$work/new" "$work/old"
     promoting=0; committed=0
     rollback() {
       status=$?; trap - EXIT
       if [ "$committed" -eq 0 ]; then
         if [ "$promoting" -eq 1 ]; then
           for f in "$target"/* "$target"/.[!.]* "$target"/..?*; do
             [ -e "$f" ] || [ -L "$f" ] || continue
             [ "$f" = "$work" ] && continue
             mv -- "$f" "$work/new/" || { echo "uploads rollback failed; recovery files: $work" >&2; exit 1; }
           done
         fi
         for f in "$work/old"/* "$work/old"/.[!.]* "$work/old"/..?*; do
           [ -e "$f" ] || [ -L "$f" ] || continue
           mv -- "$f" "$target/" || { echo "uploads rollback failed; recovery files: $work" >&2; exit 1; }
         done
       fi
       rm -rf -- "$work" || exit 1
       exit "$status"
     }
     trap rollback EXIT
     tar -xzf - -C "$work/new"
     for f in "$target"/* "$target"/.[!.]* "$target"/..?*; do
       [ -e "$f" ] || [ -L "$f" ] || continue
       [ "$f" = "$work" ] && continue
       mv -- "$f" "$work/old/"
     done
     promoting=1
     for f in "$work/new"/* "$work/new"/.[!.]* "$work/new"/..?*; do
       [ -e "$f" ] || [ -L "$f" ] || continue
       mv -- "$f" "$target/"
     done
     committed=1' \
    sh "$UPLOAD_DIR" <"$stage/uploads.tar.gz" || die 'uploads restore failed'
fi
printf 'Restore completed from %s. Apply application migrations if required.\n' "$backup_name"
