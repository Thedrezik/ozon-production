#!/usr/bin/env bash
# Compatibility dispatcher; production operations are native only.
set -Eeuo pipefail
scripts=$(cd "$(dirname "$0")" && pwd)
action=${1:-status}; shift || true
case $action in
  deploy) exec bash "$scripts/deploy-native.sh" "$@" ;;
  update) exec bash "$scripts/update-native.sh" "$@" ;;
  rollback) exec bash "$scripts/rollback-native.sh" "$@" ;;
  backup) exec bash "$scripts/backup.sh" "$@" ;;
  restore) exec bash "$scripts/restore.sh" "$@" ;;
  smoke) exec bash "$scripts/smoke.sh" "$@" ;;
  status) exec systemctl status ozon-production.service caddy.service postgresql@15-main ;;
  logs) exec journalctl -u ozon-production.service -u caddy.service -n 100 --no-pager ;;
  *) echo 'Use deploy/update/rollback/backup/restore/smoke/status/logs.' >&2; exit 2 ;;
esac
