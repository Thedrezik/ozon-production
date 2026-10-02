#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.yml}
COMPOSE_OVERRIDE_FILE=${COMPOSE_OVERRIDE_FILE:-}
BACKUP_DIR=${BACKUP_DIR:-/data/backups}
UPLOAD_DIR=${UPLOAD_DIR:-/data/uploads}
RETENTION_COUNT=${RETENTION_COUNT:-14}
POSTGRES_SERVICE=${POSTGRES_SERVICE:-postgres}
BACKEND_SERVICE=${BACKEND_SERVICE:-backend}

die() { printf 'backup: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "required utility not found: $1"; }
for utility in docker date tar mktemp; do need "$utility"; done
[[ "$RETENTION_COUNT" =~ ^[1-9][0-9]*$ ]] || die 'RETENTION_COUNT must be a positive integer'
[[ -f "$COMPOSE_FILE" ]] || die "Compose file not found: $COMPOSE_FILE"
compose=(docker compose -f "$COMPOSE_FILE")
if [[ -n "$COMPOSE_OVERRIDE_FILE" ]]; then
  [[ -f "$COMPOSE_OVERRIDE_FILE" ]] || die "Compose override file not found: $COMPOSE_OVERRIDE_FILE"
  compose+=(-f "$COMPOSE_OVERRIDE_FILE")
fi
backend_command=(exec -T "$BACKEND_SERVICE")
# Deployment pauses the API for a consistent DB/files snapshot. One-off helpers
# mount the same volumes and never start app/background jobs.
if [[ "${BACKUP_STOPPED_BACKEND:-false}" == true ]]; then
  backend_command=(run --rm --no-deps -T "$BACKEND_SERVICE")
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
name="backup-${timestamp}.tar.gz"
stage=$(mktemp -d)
archive="$stage/$name"
cleanup() { rm -rf -- "$stage"; }
trap cleanup EXIT

printf 'Creating PostgreSQL dump...\n'
if ! "${compose[@]}" exec -T "$POSTGRES_SERVICE" sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --format=custom --no-password --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  >"$stage/database.dump"; then
  die 'PostgreSQL dump failed; no backup was published'
fi
[[ -s "$stage/database.dump" ]] || die 'PostgreSQL dump is empty'

printf 'Archiving uploads...\n'
if ! "${compose[@]}" "${backend_command[@]}" tar -czf - -C "$UPLOAD_DIR" . \
  >"$stage/uploads.tar.gz"; then
  die 'uploads archive failed; no backup was published'
fi
[[ -s "$stage/uploads.tar.gz" ]] || die 'uploads archive is empty'

cat >"$stage/README.txt" <<EOF
Ozon Production backup
Created UTC: $timestamp
Contains: PostgreSQL custom-format dump (database.dump) and contents of $UPLOAD_DIR (uploads.tar.gz).
Secrets and environment files are not included.
EOF
tar -czf "$archive" -C "$stage" database.dump uploads.tar.gz README.txt

printf 'Publishing %s...\n' "$name"
if ! "${compose[@]}" "${backend_command[@]}" sh -ec \
  'mkdir -p "$1" && umask 077 && cat > "$1/$2.tmp" && mv "$1/$2.tmp" "$1/$2"' \
  sh "$BACKUP_DIR" "$name" <"$archive"; then
  die 'could not publish backup to persistent backup volume'
fi

"${compose[@]}" "${backend_command[@]}" sh -ec \
  'dir=$1; keep=$2; n=0
   for f in "$dir"/backup-*.tar.gz; do [ -f "$f" ] || continue; n=$((n + 1)); done
   for f in "$dir"/backup-*.tar.gz; do
     [ -f "$f" ] || continue
     [ "$n" -gt "$keep" ] || break
     rm -f -- "$f"; n=$((n - 1))
   done' \
  sh "$BACKUP_DIR" "$RETENTION_COUNT" || die 'backup created, but retention cleanup failed'

printf 'Backup created: %s/%s (retaining newest %s)\n' "$BACKUP_DIR" "$name" "$RETENTION_COUNT"
