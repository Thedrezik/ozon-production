#!/usr/bin/env bash
# Synthetic command-recording regression; NOT a Linux/Docker acceptance check.
set -Eeuo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/bin" "$work/scripts" "$work/deployment-results/private"
cp "$root/scripts/production.sh" "$work/scripts/production.sh"
cp "$root/docker-compose.production.yml" "$work/docker-compose.production.yml"
printf 'synthetic only\n' > "$work/test.env"
printf 'prior-rollback-state' > "$work/deployment-results/private/previous-release.json"
cat > "$work/bin/docker" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$COMMAND_LOG"
if [[ ${FAIL_MIGRATION:-false} == true && "$*" == *'alembic upgrade head'* ]]; then exit 42; fi
SH
cat > "$work/bin/git" <<'SH'
#!/usr/bin/env bash
printf 'git %s\n' "$*" >> "$COMMAND_LOG"
case "$1" in
  status) : ;;
  fetch) : ;;
  rev-parse) printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n' ;;
  *) exit 44 ;;
esac
SH
printf '#!/usr/bin/env bash\necho Linux\n' > "$work/bin/uname"
printf '#!/usr/bin/env bash\necho 600\n' > "$work/bin/stat"
printf '#!/usr/bin/env bash\nexit 0\n' > "$work/bin/flock"
printf '#!/usr/bin/env bash\nexit 45\n' > "$work/bin/python3"
printf '#!/usr/bin/env bash\nexit 43\n' > "$work/scripts/backup.sh"
chmod +x "$work/bin/"*
export PATH="$work/bin:$PATH" PRODUCTION_ENV_FILE="$work/test.env" COMMAND_LOG="$work/commands"
status=0
FAIL_MIGRATION=true bash "$work/scripts/production.sh" start > "$work/result" 2>&1 || status=$?
[[ "$status" == 42 ]]
grep -F 'stop caddy backend' "$COMMAND_LOG" >/dev/null
grep -F 'alembic upgrade head' "$COMMAND_LOG" >/dev/null
! grep -E 'up .*backend caddy|caddy validate|health/ready' "$COMMAND_LOG"
grep -F 'stopped API remains stopped' "$work/result" >/dev/null
: > "$COMMAND_LOG"
status=0
bash "$work/scripts/production.sh" update synthetic-ref > "$work/result" 2>&1 || status=$?
[[ "$status" == 43 ]]
[[ $(cat "$work/deployment-results/private/previous-release.json") == prior-rollback-state ]]
! grep -E 'checkout|alembic|up .*backend caddy' "$COMMAND_LOG"
echo 'PASS: synthetic migration failure prevents API/proxy startup; failed backup preserves prior atomic rollback state and prevents update.'
