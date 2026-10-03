#!/usr/bin/env bash
set -Eeuo pipefail
[[ $# == 1 ]] || { echo 'Usage: sudo bash update-native.sh RELEASE_SHA_OR_TAG' >&2; exit 2; }
exec bash "$(dirname "$0")/native-release.sh" update "$1"
