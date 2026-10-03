#!/usr/bin/env bash
# Source from native operations. Production paths are deliberately fixed.
set -Eeuo pipefail
umask 077
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
fail() { echo "native: $*" >&2; exit 1; }
APP_ROOT=/opt/ozon-production
STATE_DIR=/var/lib/ozon-production/private
ENV_FILE=/etc/ozon-production/production.env
UPLOAD_DIR=/var/lib/ozon-production/uploads
BACKUP_DIR=/var/lib/ozon-production/backups
APP_USER=ozon-app
SERVICE=ozon-production.service
# Only isolated test/drill data may override FHS paths; never production env.
if [[ ${NATIVE_DRILL_ROOT:-} != '' ]]; then
  [[ $NATIVE_DRILL_ROOT == /tmp/ozon-native-drill-* && -d $NATIVE_DRILL_ROOT && ! -L $NATIVE_DRILL_ROOT ]] || fail 'Invalid isolated drill root.'
  APP_ROOT=$NATIVE_DRILL_ROOT/app
  STATE_DIR=$NATIVE_DRILL_ROOT/private
  ENV_FILE=$NATIVE_DRILL_ROOT/private/test.env
  UPLOAD_DIR=$NATIVE_DRILL_ROOT/uploads
  BACKUP_DIR=$NATIVE_DRILL_ROOT/backups
fi
native_require() {
  [[ $(uname -s) == Linux && $EUID == 0 ]] || fail 'Run on Linux through sudo.'
  [[ -f $ENV_FILE && ! -L $ENV_FILE && $(stat -c %u:%a "$ENV_FILE") == 0:600 ]] || fail 'Require root-owned private env mode 600.'
  for path in "$APP_ROOT" "$STATE_DIR" "$UPLOAD_DIR" "$BACKUP_DIR"; do
    [[ -d $path && ! -L $path ]] || fail "Missing/unsafe directory: $path"
  done
  if [[ ${NATIVE_LOCK_HELD:-false} != true ]]; then
    exec 9>"$STATE_DIR/operations.lock"
    flock -n 9 || fail 'Another native operation is active.'
    export NATIVE_LOCK_HELD=true
  fi
}
env_run() { python3 "$SCRIPT_DIR/native-env.py" "$ENV_FILE" run -- "$@"; }
space_check() {
  [[ $(df -B1 --output=avail "$APP_ROOT" | tail -n 1) -ge ${MIN_FREE_BYTES:-1073741824} ]] || fail 'Need 1 GiB free for staging; inspect disk/retention before retry.'
}
ready() {
  local host
  host=$(python3 "$SCRIPT_DIR/native-env.py" "$ENV_FILE" public)
  for attempt in {1..30}; do
    if curl -fsS --max-time 3 -H "Host: $host" http://127.0.0.1:8000/api/health/ready >/dev/null; then return; fi
    sleep 2
  done
  fail 'Readiness failed; API remains stopped on update failure.'
}
switch_release() {
  local next="$APP_ROOT/.current-$BASHPID-$RANDOM"
  [[ $1 == "$APP_ROOT/releases/"* && -d $1 && ! -L $1 ]] || fail 'Unsafe release target.'
  ln -s "$1" "$next"
  mv -Tf "$next" "$APP_ROOT/current"
}
