#!/usr/bin/env bash
# Consistent native DB/files snapshot; root-only bundles, no env/master key.
source "$(dirname "$0")/native-common.sh"
native_require
RETENTION_COUNT=${RETENTION_COUNT:-3}
[[ $RETENTION_COUNT =~ ^[1-9][0-9]*$ ]] || fail 'Invalid RETENTION_COUNT.'
space_check
was_active=false
stage=$(mktemp -d "$BACKUP_DIR/.backup.XXXXXX")
cleanup() {
  result=$?; trap - EXIT
  rm -rf -- "$stage"
  if [[ $was_active == true ]]; then systemctl start "$SERVICE" || result=1; fi
  exit "$result"
}
trap cleanup EXIT
if [[ -z ${NATIVE_DRILL_ROOT:-} ]] && systemctl is-active --quiet "$SERVICE"; then
  was_active=true
  systemctl stop "$SERVICE"
fi
name="backup-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM.tar.gz"
env_run pg_dump --format=custom --no-password --no-owner --no-privileges > "$stage/database.dump" || fail 'PostgreSQL dump failed; nothing published.'
pg_restore --list "$stage/database.dump" >/dev/null || fail 'Dump validation failed.'
tar -czf "$stage/uploads.tar.gz" -C "$UPLOAD_DIR" .
printf 'Ozon native backup UTC: %s\nNo secrets included.\n' "$(date -u +%FT%TZ)" > "$stage/README.txt"
tar -czf "$stage/bundle" -C "$stage" database.dump uploads.tar.gz README.txt
mv "$stage/bundle" "$BACKUP_DIR/$name"
# Protect the database snapshot explicitly referenced by the rollback record.
protected=$(python3 - "$STATE_DIR/previous.json" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); print(json.loads(p.read_text()).get('backup','') if p.exists() else '')
PY
)
mapfile -t archives < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'backup-*.tar.gz' -printf '%f\n' | sort -r)
for ((i=RETENTION_COUNT; i<${#archives[@]}; i++)); do
  [[ ${archives[i]} == "$protected" ]] || rm -f -- "$BACKUP_DIR/${archives[i]}"
done
printf 'Backup created: %s/%s (retaining newest %s plus rollback snapshot)\n' "$BACKUP_DIR" "$name" "$RETENTION_COUNT"
