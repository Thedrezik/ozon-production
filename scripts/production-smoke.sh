#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
env_file=${PRODUCTION_ENV_FILE:-.env.production}
command -v curl >/dev/null
command -v python3 >/dev/null
# Parse one public field; never source/execute env content or print other values.
domain=$(python3 - "$env_file" <<'PY'
import pathlib, re, sys
values = dict(line.split('=',1) for line in pathlib.Path(sys.argv[1]).read_text().splitlines() if line and not line.startswith('#') and '=' in line)
domain = values['DOMAIN']
assert re.fullmatch(r'[a-z0-9.-]+', domain) and '.' in domain
print(domain)
PY
)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
curl --max-time 15 --silent --show-error --dump-header "$work/redirect" --output /dev/null "http://$domain/"
grep -Eiq '^HTTP/[^ ]+ (301|302|307|308)' "$work/redirect"
grep -Eiq "^location: https://$domain/" "$work/redirect"
for path in / /queue /sw.js /manifest.webmanifest /api/health /api/health/ready; do
  curl --max-time 20 --fail --silent --show-error --dump-header "$work/headers" --output "$work/body" "https://$domain$path"
  for header in 'x-content-type-options: nosniff' 'x-frame-options: DENY' 'referrer-policy: no-referrer' 'strict-transport-security:' 'content-security-policy:'; do
    grep -Fiq "$header" "$work/headers" || { echo "Missing $header on $path" >&2; exit 1; }
  done
  if [[ "$path" == /api/health ]]; then
    python3 - "$work/body" <<'PY'
import json,sys
data=json.load(open(sys.argv[1])); assert data['status']=='ok' and data['mock_mode'] is False
PY
  fi
done
# Edge denial must ignore a forged Ozon/XFF address from ordinary internet peers.
code=$(curl --max-time 15 --silent --show-error --output "$work/body" --write-out '%{http_code}' -H 'Content-Type: application/json' -H 'X-Ozon-Source-IP: 195.34.21.1' -H 'X-Forwarded-For: 195.34.21.1' --data '{}' "https://$domain/api/ozon/webhook")
[[ "$code" == 403 ]] || { echo "Expected public webhook source denial; got $code" >&2; exit 1; }
code=$(curl --max-time 15 --silent --show-error --output "$work/body" --write-out '%{http_code}' -H 'Origin: https://untrusted.invalid' -H 'Content-Type: application/json' --data '{}' "https://$domain/api/auth/login")
[[ "$code" == 403 ]]
! grep -Ei 'traceback|stack trace|sqlalchemy|postgresql\+psycopg://' "$work/body"
echo 'PASS: verified certificate, HTTP redirect, SPA/PWA routes, health/readiness, production mode, headers, browser origin and webhook source denial.'
echo 'Authenticated/device/provider and PostgreSQL performance gates remain in docs/DEPLOYMENT.md.'
