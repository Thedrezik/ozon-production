#!/usr/bin/env bash
# Fixed project/file selection; never prints resolved Compose/env configuration.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/.."
[[ $(uname -s) == Linux ]] || { echo 'Run production operations on Linux.' >&2; exit 1; }
export COMPOSE_PROJECT_NAME=ozon-production COMPOSE_FILE=docker-compose.production.yml
export APP_ENV_FILE=${PRODUCTION_ENV_FILE:-.env.production}
export COMPOSE_ENV_FILES="$APP_ENV_FILE"
unset COMPOSE_OVERRIDE_FILE
[[ -f "$APP_ENV_FILE" ]] || { echo 'Create the private production env first.' >&2; exit 1; }
[[ $(stat -c %a "$APP_ENV_FILE") == 600 ]] || { echo 'Require chmod 600 on production env.' >&2; exit 1; }
command -v docker >/dev/null
command -v python3 >/dev/null
mkdir -p deployment-results/private
chmod 700 deployment-results/private
exec 9>deployment-results/private/operations.lock
flock -n 9 || { echo 'Another production operation is active.' >&2; exit 1; }
compose=(docker compose --env-file "$APP_ENV_FILE" -p ozon-production -f "$COMPOSE_FILE")
"${compose[@]}" config --quiet
action=${1:-status}
trap 'echo "Production operation failed; inspect status/logs. A stopped API remains stopped; no automatic database downgrade or volume removal." >&2' ERR

images() {
  case "${IMAGE_MODE:-pull}" in
    pull) "${compose[@]}" pull backend caddy postgres ;;
    build) "${compose[@]}" build backend caddy; "${compose[@]}" pull postgres ;;
    existing) : ;;
    *) echo 'IMAGE_MODE must be pull, build or existing.' >&2; exit 1 ;;
  esac
}
ready() {
  "${compose[@]}" exec -T backend python -c 'import os, urllib.request; urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8000/api/health/ready", headers={"Host":os.environ["DOMAIN"]}), timeout=5)'
}
start_release() {
  "${compose[@]}" up -d --wait --wait-timeout 90 postgres
  "${compose[@]}" run --rm --no-deps -T backend python -c 'from app.config import Settings; Settings(); print("Production settings validated")'
  # A migration failure prevents either new API or Caddy from starting.
  "${compose[@]}" run --rm --no-deps -T backend alembic upgrade head
  "${compose[@]}" run --rm --no-deps -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
  "${compose[@]}" up -d --wait --wait-timeout 120 backend caddy
  ready
  bash scripts/production-smoke.sh
}
snapshot() {
  # Stop all writers BEFORE capture; do not restart automatically on failure.
  "${compose[@]}" stop caddy backend
  "${compose[@]}" up -d --wait --wait-timeout 90 postgres
  BACKUP_STOPPED_BACKEND=true bash scripts/backup.sh | tee deployment-results/private/backup-output.txt
}
case "$action" in
  deploy)
    if docker volume inspect ozon-production_postgres_data >/dev/null 2>&1; then
      echo 'Existing database volume: use update (with backup), not initial deploy.' >&2; exit 1
    fi
    images
    start_release ;;
  update)
    [[ $# == 2 ]] || { echo 'Usage: production.sh update RELEASE_REF' >&2; exit 2; }
    [[ -z $(git status --porcelain --untracked-files=no) ]] || { echo 'Tracked working tree must be clean before update.' >&2; exit 1; }
    # Fetch without changing running code; backup still precedes checkout/build.
    git fetch --tags origin
    # Resolve an immutable release BEFORE stopping the old API.
    release=$(git rev-parse --verify "$2^{commit}")
    previous_ref=$(git rev-parse HEAD)
    snapshot
    # Publish code/env/archive as ONE atomic state only after backup succeeds.
    # A failed capture must not associate an older archive with a newer ref/env.
    python3 - "$APP_ENV_FILE" "$previous_ref" <<'PY'
import json, os, pathlib, re, sys
directory = pathlib.Path('deployment-results/private')
output = (directory / 'backup-output.txt').read_text()
match = re.search(r'^Backup created: /data/backups/(backup-[0-9]{8}T[0-9]{6}Z\.tar\.gz) ', output, re.M)
if not match:
    raise SystemExit('Backup filename missing; API remains stopped')
state = {'ref': sys.argv[2], 'env': pathlib.Path(sys.argv[1]).read_text(), 'backup': match[1]}
temporary = directory / 'previous-release.json.tmp'
temporary.write_text(json.dumps(state))
os.chmod(temporary, 0o600)
os.replace(temporary, directory / 'previous-release.json')
PY
    git checkout --detach "$release"
    python3 - "$APP_ENV_FILE" "$release" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
values = {'BACKEND_IMAGE': 'ozon-backend:' + sys.argv[2], 'CADDY_IMAGE': 'ozon-caddy:' + sys.argv[2]}
path.write_text('\n'.join(f'{line.split("=",1)[0]}={values[line.split("=",1)[0]]}' if line.split('=',1)[0] in values else line for line in path.read_text().splitlines()) + '\n')
PY
    images
    start_release ;;
  rollback)
    [[ -s deployment-results/private/previous-release.json ]]
    [[ -z $(git status --porcelain --untracked-files=no) ]]
    previous=$(python3 - <<'PY'
import json, re
state=json.load(open('deployment-results/private/previous-release.json'))
assert re.fullmatch(r'[0-9a-f]{40,64}', state['ref'])
assert re.fullmatch(r'backup-[0-9]{8}T[0-9]{6}Z\.tar\.gz', state['backup'])
print(state['ref']); print(state['backup'])
PY
)
    "${compose[@]}" stop caddy backend
    git checkout --detach "${previous%%$'\n'*}"
    python3 - "$APP_ENV_FILE" <<'PY'
import json, pathlib, sys
state=json.load(open('deployment-results/private/previous-release.json'))
pathlib.Path(sys.argv[1]).write_text(state['env'])
PY
    chmod 600 "$APP_ENV_FILE"
    # Restore asks for RESTORE. Keep the API stopped if SQL/uploads fail.
    bash scripts/restore.sh "${previous##*$'\n'}"
    start_release ;;
  backup) snapshot; echo 'Consistent backup complete; API stopped. Run production.sh start after checking the archive.' ;;
  restore)
    [[ $# == 2 ]] || { echo 'Usage: production.sh restore BACKUP_FILENAME' >&2; exit 2; }
    "${compose[@]}" stop caddy backend
    bash scripts/restore.sh "$2"
    echo 'Restore complete; API stopped. Verify matching release/schema before start.' ;;
  start) "${compose[@]}" stop caddy backend; start_release ;;
  stop) "${compose[@]}" stop caddy backend postgres ;;
  restart) "${compose[@]}" restart backend caddy; ready; bash scripts/production-smoke.sh ;;
  status) "${compose[@]}" ps ;;
  smoke) bash scripts/production-smoke.sh ;;
  logs) "${compose[@]}" logs --tail 100 "${2:-backend}" ;;
  health|readiness)
    endpoint=health; [[ "$action" != readiness ]] || endpoint=health/ready
    "${compose[@]}" exec -T backend python -c 'import os,sys,urllib.request; print(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8000/api/"+sys.argv[1], headers={"Host":os.environ["DOMAIN"]}), timeout=5).read().decode())' "$endpoint" ;;
  *) echo 'Commands: deploy, update REF, rollback, status, logs [service], smoke, health, readiness, backup, restore FILE, start, stop, restart' >&2; exit 2 ;;
esac
