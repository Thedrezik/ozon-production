#!/usr/bin/env bash
set -Eeuo pipefail
[[ $# == 2 ]] || { echo 'Usage: sudo bash deploy-native.sh RELEASE_SHA_OR_TAG PUBLIC_IPV4' >&2; exit 2; }
exec bash "$(dirname "$0")/native-release.sh" deploy "$1" "$2"
