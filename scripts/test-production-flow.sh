#!/usr/bin/env bash
# Command-recording native flow regression; never invokes host systemd/DB.
source "$(dirname "$0")/native-test-fixture.sh"
ln -s "$work/app/releases/old" "$work/app/current"
printf '%s' '{"marker":"prior-state"}' > "$work/private/previous.json"
mkdir -p "$work/fixture/backend" "$work/fixture/frontend" "$work/fixture/deployment"
cp "$root/deployment/"*.service "$root/deployment/Caddyfile" "$root/deployment/postgresql-small.conf" "$work/fixture/deployment/"
touch "$work/fixture/backend/requirements.txt"
export FLOW_FIXTURE="$work/fixture"
cat > "$work/bin/runuser" <<'SH'
#!/usr/bin/env bash
shift 3; exec "$@"
SH
cat > "$work/bin/git" <<'SH'
#!/usr/bin/env bash
shift 2
echo "git $*" >> "$COMMAND_LOG"
case $1 in
  status|fetch|checkout) : ;;
  rev-parse) echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa ;;
  archive) tar -cf - -C "$FLOW_FIXTURE" . ;;
  *) exit 44 ;;
esac
SH
cat > "$work/bin/uv" <<'SH'
#!/usr/bin/env bash
path=${@: -1}; mkdir -p "$path/bin"; cp "$FLOW_PYTHON" "$path/bin/python"; chmod +x "$path/bin/python"
SH
cat > "$work/bin/release-python" <<'SH'
#!/usr/bin/env bash
echo "release-python $*" >> "$COMMAND_LOG"
if [[ $* == *'alembic upgrade head'* && ${FAIL_MIGRATION:-false} == true ]]; then exit 42; fi
SH
cat > "$work/bin/npm" <<'SH'
#!/usr/bin/env bash
echo "npm $*" >> "$COMMAND_LOG"
mkdir -p dist; echo synthetic > dist/index.html
SH
printf '#!/usr/bin/env bash\nexit 0\n' > "$work/bin/chown"
printf '#!/usr/bin/env bash\nexit 0\n' > "$work/bin/chmod"
printf '#!/usr/bin/env bash\nexit 0\n' > "$work/bin/systemd-analyze"
printf '#!/usr/bin/env bash\nexit 0\n' > "$work/bin/caddy"
chmod +x "$work/bin/"*
export FLOW_PYTHON="$work/bin/release-python"
status=0
FAIL_BACKUP=true bash "$work/scripts/native-release.sh" update synthetic > "$work/result" 2>&1 || status=$?
[[ $status != 0 && $(cat "$work/private/previous.json") == '{"marker":"prior-state"}' ]]
! grep -Eq 'git fetch|git checkout|alembic|systemctl restart' "$COMMAND_LOG"
: > "$COMMAND_LOG"
status=0
FAIL_MIGRATION=true bash "$work/scripts/native-release.sh" update synthetic > "$work/result" 2>&1 || status=$?
if [[ $status != 42 ]]; then cat "$work/result" >&2; fi
[[ $status == 42 && -f $work/private/update-pending ]]
grep -q 'alembic upgrade head' "$COMMAND_LOG"
! grep -q 'systemctl restart ozon-production' "$COMMAND_LOG"
[[ $(readlink "$work/app/current") == "$work/app/releases/old" ]]
[[ -s $work/private/previous.json && -s $work/private/previous.env ]]
! find "$work/app/releases" -name node_modules -o -name .npm-cache | grep -q .
echo 'PASS: failed backup preserves recovery state; failed migrations prevent API start/current switch and retain pre-update backup.'
rm -rf -- "$work/app/current"
rm -f -- "$work/private/update-pending"
: > "$COMMAND_LOG"
status=0
FAIL_MIGRATION=true bash "$work/scripts/native-release.sh" deploy synthetic factory.example.org > "$work/result" 2>&1 || status=$?
if [[ $status != 42 ]]; then cat "$work/result" >&2; fi
[[ $status == 42 ]]
grep -q 'alembic upgrade head' "$COMMAND_LOG"
! grep -q 'systemctl restart ozon-production' "$COMMAND_LOG"
echo 'PASS: first deploy reaches migrations without an existing API service and does not start after migration failure.'
