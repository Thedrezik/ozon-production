#!/usr/bin/env bash
source "$(dirname "$0")/native-common.sh"
native_require
[[ $# -ge 1 ]] || fail 'Usage: restore.sh BACKUP_FILENAME [--database-only|--uploads-only] [--yes]'
name=$1; shift
[[ $name == backup-*.tar.gz && $name != */* && -f $BACKUP_DIR/$name && ! -L $BACKUP_DIR/$name ]] || fail 'Provide a local backup filename.'
database=true; uploads=true; yes=false
for arg; do
  case $arg in
    --yes|--non-interactive) yes=true ;;
    --database-only) uploads=false ;;
    --uploads-only) database=false ;;
    *) fail 'Unknown restore option.' ;;
  esac
done
[[ $database == true || $uploads == true ]] || fail 'No restore operation selected.'
if [[ -z ${NATIVE_DRILL_ROOT:-} ]]; then
  ! systemctl is-active --quiet "$SERVICE" || fail 'Stop the backend before destructive restore.'
fi
stage=$(mktemp -d "$BACKUP_DIR/.restore.XXXXXX")
trap 'rm -rf -- "$stage"' EXIT
# Validate both archive layers before extraction; no links/devices/traversal.
python3 "$SCRIPT_DIR/validate-backup.py" "$BACKUP_DIR/$name" "$stage"
pg_restore --list "$stage/database.dump" >/dev/null || fail 'Database dump failed validation.'
if [[ $yes != true ]]; then
  [[ -t 0 ]] || fail 'Interactive confirmation required; automated restore must explicitly pass --yes.'
  echo 'WARNING: replaces DB objects and uploads; backend must remain stopped.' >&2
  read -r -p 'Type RESTORE to continue: ' answer
  [[ $answer == RESTORE ]] || fail 'Restore cancelled.'
fi
if [[ $database == true ]]; then
  env_run pg_restore --single-transaction --exit-on-error --clean --if-exists --no-owner --no-privileges --no-password "$stage/database.dump" || fail 'DB restore failed; backend remains stopped.'
  env_run psql -X -v ON_ERROR_STOP=1 -Atc 'SELECT 1' | grep -qx 1
fi
if [[ $uploads == true ]]; then
  work=$(mktemp -d "$(dirname "$UPLOAD_DIR")/.uploads-restore.XXXXXX")
  mkdir "$work/new" "$work/old"
  tar -xzf "$stage/uploads.tar.gz" -C "$work/new" --no-same-owner --no-same-permissions
  if [[ -z ${NATIVE_DRILL_ROOT:-} ]]; then chown -R "$APP_USER:$APP_USER" "$work/new"; fi
  chmod 700 "$work/new"
  mv "$UPLOAD_DIR" "$work/old/uploads"
  if ! mv "$work/new" "$UPLOAD_DIR"; then
    mv "$work/old/uploads" "$UPLOAD_DIR" || fail "Upload recovery required: $work"
    fail "Upload promotion failed; old files retained: $work"
  fi
  rm -rf -- "$work"
fi
echo "Restore completed: $name. Backend remains stopped; verify migrations/readiness before startup."
