#!/usr/bin/env bash
# Synthetic copies only: no privileged native script runs against host paths.
set -Eeuo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
export REAL_PYTHON=${REAL_PYTHON:-$root/backend/.venv/Scripts/python.exe}
[[ -x $REAL_PYTHON ]] || REAL_PYTHON="$root/backend/.venv/bin/python"
export REAL_PYTHON
mkdir -p "$work/bin" "$work/scripts" "$work/app/releases/old" "$work/app/repo/.git" "$work/private" "$work/uploads" "$work/backups" "$work/etc/ozon-production" "$work/etc/caddy" "$work/etc/systemd/system" "$work/etc/postgresql/15/main/conf.d"
for file in native-common.sh native-env.py validate-backup.py backup.sh restore.sh native-release.sh smoke.sh; do
  cp "$root/scripts/$file" "$work/scripts/$file"
done
for file in "$work/scripts/"*.sh; do
  sed -i -e "s|/opt/ozon-production|$work/app|g" -e "s|/var/lib/ozon-production/private|$work/private|g" -e "s|/var/lib/ozon-production/uploads|$work/uploads|g" -e "s|/var/lib/ozon-production/backups|$work/backups|g" -e "s|/etc/ozon-production|$work/etc/ozon-production|g" -e "s|/etc/caddy|$work/etc/caddy|g" -e "s|/etc/systemd/system|$work/etc/systemd/system|g" -e "s|/etc/postgresql/15/main/conf.d|$work/etc/postgresql/15/main/conf.d|g" -e "s|/usr/local/bin/caddy|$work/bin/caddy|g" -e 's/\$EUID == 0/1 == 1/g' "$file"
done
# MSYS cannot create native symlinks in this sandbox. Only the copied fixture
# relaxes the current-link probe; Linux production keeps the strict check.
if [[ $(uname -s) == MINGW* || $(uname -s) == MSYS* ]]; then
  sed -i 's/\[\[ -L $APP_ROOT\/current \]\]/[[ -d $APP_ROOT\/current ]]/g' "$work/scripts/native-release.sh"
  sed -i 's/mkdir -m 755/mkdir/g' "$work/scripts/native-release.sh"
  cat > "$work/bin/readlink" <<'SH'
#!/usr/bin/env bash
path=${@: -1}
if [[ $path == */app/current ]]; then echo "${path%/current}/releases/old"; else /usr/bin/readlink "$@"; fi
SH
fi
printf 'synthetic\n' > "$work/etc/ozon-production/production.env"
printf '#!/usr/bin/env bash\necho Linux\n' > "$work/bin/uname"
cat > "$work/bin/stat" <<'SH'
#!/usr/bin/env bash
case "$2" in %u:%a) echo 0:600 ;; %U) echo synthetic ;; *) echo 600 ;; esac
SH
printf '#!/usr/bin/env bash\nexit 0\n' > "$work/bin/flock"
printf '#!/usr/bin/env bash\necho available; echo 9999999999\n' > "$work/bin/df"
cat > "$work/bin/python3" <<'SH'
#!/usr/bin/env bash
if [[ $1 == */native-env.py ]]; then
  case "$3" in
    run) shift 4; exec "$@" ;;
    check|provision) exit 0 ;;
    public) echo factory.example.org; exit 0 ;;
  esac
fi
exec "$REAL_PYTHON" "$@"
SH
cat > "$work/bin/pg_dump" <<'SH'
#!/usr/bin/env bash
[[ ${FAIL_BACKUP:-false} != true ]] || exit 43
printf synthetic-dump
SH
cat > "$work/bin/pg_restore" <<'SH'
#!/usr/bin/env bash
[[ ${FAIL_VALIDATION:-false} != true ]] || exit 42
[[ $(cat "${@: -1}") == synthetic-dump ]]
SH
printf '#!/usr/bin/env bash\necho 1\n' > "$work/bin/psql"
printf '#!/usr/bin/env bash\nexit 0\n' > "$work/bin/chown"
cat > "$work/bin/systemctl" <<'SH'
#!/usr/bin/env bash
echo "systemctl $*" >> "$COMMAND_LOG"
[[ $1 != is-active ]]
SH
chmod +x "$work/bin/"*
export PATH="$work/bin:$PATH" COMMAND_LOG="$work/commands"
