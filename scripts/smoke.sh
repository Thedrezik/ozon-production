#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
env_file=${PRODUCTION_ENV_FILE:-/etc/ozon-production/production.env}
domain=$(python3 "$SCRIPT_DIR/native-env.py" "$env_file" public)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
curl --max-time 15 -sS -D "$work/redirect" -o /dev/null "http://$domain/"
grep -Eiq '^HTTP/[^ ]+ (301|302|307|308)' "$work/redirect"
grep -Fiq "location: https://$domain/" "$work/redirect"
# Public trust validation stays enabled. Automatic renewal belongs to Caddy.
curl --retry 12 --retry-delay 5 --retry-all-errors --retry-max-time 180 --max-time 20 -fsS -o /dev/null "https://$domain/api/health/ready"
for path in / /queue /sw.js /manifest.webmanifest /api/health /api/health/ready; do
  curl --max-time 20 -fsS -D "$work/headers" -o "$work/body" "https://$domain$path"
  for header in 'x-content-type-options: nosniff' 'x-frame-options: DENY' 'referrer-policy: no-referrer' 'strict-transport-security:' 'content-security-policy:'; do
    grep -Fiq "$header" "$work/headers" || { echo "Missing $header on $path" >&2; exit 1; }
  done
  if [[ $path == /api/health ]]; then
    python3 - "$work/body" <<'PY'
import json,sys
data=json.load(open(sys.argv[1])); assert data['status']=='ok' and data['mock_mode'] is False
PY
  fi
  if [[ $path == / ]]; then cp "$work/body" "$work/index"; fi
  if [[ $path == /queue ]]; then cmp "$work/body" "$work/index"; fi
done
code=$(curl --max-time 15 -sS -o "$work/body" -w '%{http_code}' -H 'Content-Type: application/json' -H 'X-Ozon-Source-IP: 195.34.21.1' -H 'X-Forwarded-For: 195.34.21.1' --data '{}' "https://$domain/api/ozon/webhook")
[[ $code == 403 ]]
code=$(curl --max-time 15 -sS -o "$work/body" -w '%{http_code}' -H 'Origin: https://untrusted.invalid' -H 'Content-Type: application/json' --data '{}' "https://$domain/api/auth/login")
[[ $code == 403 ]]
! grep -Ei 'traceback|stack trace|sqlalchemy|postgresql\+psycopg://' "$work/body"
# Both the edge (21 MB) and application mutation limits must reject this body.
dd if=/dev/zero of="$work/oversize" bs=1M count=22 status=none
code=$(curl --max-time 30 -sS -o "$work/body" -w '%{http_code}' -H 'Content-Type: application/octet-stream' --data-binary "@$work/oversize" "https://$domain/api/auth/login")
[[ $code == 413 ]]
# Optional private cookie jar from an authorized test user, never logged/argv secrets.
# Enables actual SSE checks without weakening production authentication.
if [[ -n ${SMOKE_COOKIE_JAR:-} ]]; then
  [[ -f $SMOKE_COOKIE_JAR && $(stat -c %a "$SMOKE_COOKIE_JAR") == 600 ]]
  curl --max-time 25 -fsS -b "$SMOKE_COOKIE_JAR" -D "$work/sse-headers" -o "$work/sse" "https://$domain/api/orders/events"
  grep -Fiq 'content-type: text/event-stream' "$work/sse-headers"
  grep -Eq '^event:|^data:' "$work/sse"
else
  echo 'Authenticated SSE not run; provide private SMOKE_COOKIE_JAR for task 034.'
fi
echo 'PASS: trusted HTTPS, HTTP redirect, SPA/PWA, API readiness/production mode, headers, body limit, origin and source denial.'
