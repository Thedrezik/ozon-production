#!/usr/bin/env bash
source "$(dirname "$0")/native-common.sh"
native_require
[[ $# == 0 || ( $# == 1 && ( $1 == --yes || $1 == --non-interactive ) ) ]] || fail 'Usage: rollback-native.sh [--yes]'
[[ -z ${NATIVE_DRILL_ROOT:-} ]] || fail 'Rollback cannot target a drill.'
mapfile -t record < <(python3 - "$STATE_DIR/previous.json" "$APP_ROOT/releases" <<'PY'
import json,pathlib,sys
d=json.loads(pathlib.Path(sys.argv[1]).read_text()); p=pathlib.Path(d['release'])
assert p.is_dir() and not p.is_symlink() and p.parent == pathlib.Path(sys.argv[2])
print(p); print(d['backup'])
PY
)
[[ ${#record[@]} == 2 && -f $STATE_DIR/previous.env ]] || fail 'No complete rollback record.'
echo 'Rollback restores DB/uploads to pre-update snapshot; post-update writes will be lost.' >&2
if [[ $# == 0 ]]; then
  [[ -t 0 ]] || fail 'Interactive confirmation required; use explicit --yes for an authorized automated rollback.'
  read -r -p 'Type ROLLBACK to continue: ' answer
  [[ $answer == ROLLBACK ]] || fail 'Rollback cancelled.'
fi
systemctl stop "$SERVICE"
trap 'result=$?; if [[ $result != 0 ]]; then echo "Rollback failed; backend remains stopped. Inspect private recovery record." >&2; systemctl stop "$SERVICE"; fi' EXIT
# Database credentials must remain unchanged until the update backup is restored.
bash "$SCRIPT_DIR/restore.sh" "${record[1]}" --yes
install -m 600 "$STATE_DIR/previous.env" "$ENV_FILE"
release=${record[0]}
install -m 644 "$release/deployment/ozon-production.service" /etc/systemd/system/ozon-production.service
install -m 644 "$release/deployment/caddy.service" /etc/systemd/system/caddy.service
install -m 644 "$release/deployment/ozon-backup.service" /etc/systemd/system/ozon-backup.service
install -m 644 "$release/deployment/ozon-backup.timer" /etc/systemd/system/ozon-backup.timer
install -m 644 "$release/deployment/Caddyfile" /etc/caddy/Caddyfile
install -m 644 "$release/deployment/postgresql-small.conf" /etc/postgresql/15/main/conf.d/ozon.conf
host=$(python3 "$SCRIPT_DIR/native-env.py" "$ENV_FILE" public)
printf 'DOMAIN=%s\n' "$host" > /etc/ozon-production/caddy.env
DOMAIN="$host" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
switch_release "$release"
systemctl daemon-reload
systemctl restart postgresql@15-main
systemctl restart "$SERVICE"
ready
systemctl reload-or-restart caddy.service
bash "$SCRIPT_DIR/smoke.sh"
rm -f -- "$STATE_DIR/update-pending"
echo 'Rollback completed and smoke passed; previous environment retained privately.'
