#!/usr/bin/env bash
set -Eeuo pipefail
exec bash "$(dirname "$0")/backup-restore-native-drill.sh" "$@"
