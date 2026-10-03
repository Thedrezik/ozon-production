#!/usr/bin/env bash
# Shared deploy/update engine. Called by the public wrappers.
source "$(dirname "$0")/native-common.sh"
[[ $(uname -s) == Linux && $EUID == 0 ]] || fail 'Run on Debian through sudo.'
mode=${1:-}; ref=${2:-}; domain=${3:-}
[[ $mode == deploy || $mode == update ]] || fail 'Invalid release action.'
[[ $ref =~ ^[a-zA-Z0-9][a-zA-Z0-9_./-]{0,150}$ ]] || fail 'Supply an explicit release SHA/tag.'
[[ -z ${NATIVE_DRILL_ROOT:-} ]] || fail 'Release operations cannot target a backup drill.'
repo=$APP_ROOT/repo
[[ -d $repo/.git && ! -L $repo ]] || fail 'Clone the release repository into /opt/ozon-production/repo first.'
repo_user=$(stat -c %U "$repo")
git_repo() { runuser -u "$repo_user" -- git -C "$repo" "$@"; }
[[ -z $(git_repo status --porcelain) ]] || fail 'Release repository must be clean.'
if [[ ! -f $ENV_FILE ]]; then
  [[ $mode == deploy && -n $domain ]] || fail 'Initial deploy requires PUBLIC_IPV4 as third argument.'
  python3 "$SCRIPT_DIR/init-production-env.py" --domain "$domain" --release "$ref" --output "$ENV_FILE"
fi
native_require
[[ ! -e $STATE_DIR/update-pending ]] || fail 'Previous update failed; complete rollback/recovery before another update.'
space_check
old=''; backup=''
if [[ -L $APP_ROOT/current ]]; then old=$(readlink -f "$APP_ROOT/current"); fi
[[ $mode != deploy || -z $old ]] || fail 'Existing installation: use update-native.sh.'
[[ $mode != update || -n $old ]] || fail 'No installation: use deploy-native.sh.'
candidate=''
failure() {
  status=$?; trap - EXIT
  if [[ -n $candidate && -d $candidate ]]; then
    rm -rf -- "$candidate/frontend/node_modules" "$candidate/.npm-cache"
  fi
  if [[ $status != 0 ]]; then
    systemctl stop "$SERVICE" || true
    echo "Release failed (exit $status); backend stopped. Previous code: ${old:-none}." >&2
    echo 'Inspect journalctl -u ozon-production; use rollback-native.sh after reviewing its DB/uploads restore.' >&2
  fi
  exit "$status"
}
trap failure EXIT
if [[ $mode == update ]]; then
  systemctl stop "$SERVICE"
elif systemctl is-active --quiet "$SERVICE"; then
  systemctl stop "$SERVICE"
fi
if [[ $mode == update ]]; then
  bash "$SCRIPT_DIR/backup.sh" > "$STATE_DIR/backup-output"
  backup=$(sed -n 's/^Backup created: .*\/\(backup-[^ ]*\).*/\1/p' "$STATE_DIR/backup-output")
  [[ -n $backup && -s $BACKUP_DIR/$backup ]] || fail 'Update backup missing; code not changed.'
  # Publish recovery record before fetch/build/migration; never lose the prior one
  # on failed backup. ENV/config snapshots stay private and out of backup bundles.
  cp "$ENV_FILE" "$STATE_DIR/previous.env"
  python3 - "$old" "$backup" "$STATE_DIR" <<'PY'
import json,pathlib,sys
old,backup,state=sys.argv[1:]; p=pathlib.Path(state)/'previous.json.tmp'
p.write_text(json.dumps({'release':old,'backup':backup})+'\n'); p.replace(p.with_suffix(''))
PY
  touch "$STATE_DIR/update-pending"
fi
git_repo fetch --prune --tags origin
sha=$(git_repo rev-parse --verify "$ref^{commit}")
[[ $sha =~ ^[a-f0-9]{40}$ ]] || fail 'Release does not resolve to a commit.'
git_repo checkout --detach "$sha"
candidate=$APP_ROOT/releases/$sha-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM
mkdir -m 755 "$candidate"
git_repo archive "$sha" | tar -xf - -C "$candidate"
chown -R "$APP_USER:$APP_USER" "$candidate"
export UV_PYTHON_INSTALL_DIR=$APP_ROOT/python UV_NO_CACHE=1
runuser -u "$APP_USER" -- uv venv --python 3.12 --seed "$candidate/.venv"
runuser -u "$APP_USER" -- "$candidate/.venv/bin/python" -m pip install --no-cache-dir --only-binary=:all: -r "$candidate/backend/requirements.txt"
runuser -u "$APP_USER" -- "$candidate/.venv/bin/python" -m pip check
runuser -u "$APP_USER" -- "$candidate/.venv/bin/python" -m pip freeze > "$candidate/installed-requirements.txt"
(
  cd "$candidate/frontend"
  runuser -u "$APP_USER" -- env npm_config_cache="$candidate/.npm-cache" npm ci --no-audit --no-fund
  runuser -u "$APP_USER" -- env npm_config_cache="$candidate/.npm-cache" NODE_OPTIONS=--max-old-space-size=384 npm run build
)
rm -rf -- "$candidate/frontend/node_modules" "$candidate/.npm-cache"
find "$candidate" -type d -name __pycache__ -prune -exec rm -rf -- {} +
chown -R root:root "$candidate"
chmod -R go-w "$candidate"
# Archive modes and umask must allow unprivileged API/Caddy to traverse/read.
find "$candidate" -type d -exec chmod a+rx {} +
find "$candidate" -type f -exec chmod a+r {} +
(
  cd "$candidate/backend"
  PYTHONPATH="$candidate/backend" env_run "$candidate/.venv/bin/python" "$SCRIPT_DIR/native-env.py" "$ENV_FILE" check
)
if [[ $mode == deploy ]]; then
  python3 "$SCRIPT_DIR/native-env.py" "$ENV_FILE" provision
fi
install -m 644 "$candidate/deployment/postgresql-small.conf" /etc/postgresql/15/main/conf.d/ozon.conf
systemctl restart postgresql@15-main
(
  cd "$candidate/backend"
  env_run runuser -u "$APP_USER" -- "$candidate/.venv/bin/python" -m alembic upgrade head
)
install -m 644 "$candidate/deployment/ozon-production.service" /etc/systemd/system/ozon-production.service
install -m 644 "$candidate/deployment/caddy.service" /etc/systemd/system/caddy.service
install -m 644 "$candidate/deployment/ozon-backup.service" /etc/systemd/system/ozon-backup.service
install -m 644 "$candidate/deployment/ozon-backup.timer" /etc/systemd/system/ozon-backup.timer
install -m 644 "$candidate/deployment/Caddyfile" /etc/caddy/Caddyfile
host=$(python3 "$SCRIPT_DIR/native-env.py" "$ENV_FILE" public)
printf 'DOMAIN=%s\n' "$host" > /etc/ozon-production/caddy.env
chmod 600 /etc/ozon-production/caddy.env
DOMAIN="$host" /usr/local/bin/caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemd-analyze verify /etc/systemd/system/ozon-production.service /etc/systemd/system/caddy.service /etc/systemd/system/ozon-backup.service /etc/systemd/system/ozon-backup.timer
switch_release "$candidate"
systemctl daemon-reload
systemctl enable ozon-production.service caddy.service
systemctl enable --now ozon-backup.timer
systemctl restart "$SERVICE"
ready
if systemctl is-active --quiet caddy.service; then systemctl reload caddy.service; else systemctl start caddy.service; fi
bash "$SCRIPT_DIR/smoke.sh"
rm -f -- "$STATE_DIR/update-pending"
# Retain precisely current + previous. Failed candidates are cleaned on success.
for release in "$APP_ROOT/releases/"*; do
  [[ -d $release && ! -L $release ]] || continue
  [[ $release == "$candidate" || $release == "$old" ]] || rm -rf -- "$release"
done
echo "Native $mode completed: $sha. Inspect disk/RSS and external acceptance before launch."
