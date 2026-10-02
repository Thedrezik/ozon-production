#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ $(uname -s) == Linux ]] || { echo 'Linux is required.' >&2; exit 1; }
docker info >/dev/null
mkdir -p deployment-results
set -o pipefail
bash scripts/backup-restore-drill.sh 2>&1 | tee deployment-results/linux-restore-drill.txt
# Build/smoke all real workflows; isolated containers/volumes are created per case.
# Use an off-VPS Linux test host when possible: browser/build require extra memory.
cd frontend
E2E_CONTAINER=true E2E_PROBE=true npm run test:e2e 2>&1 | tee ../deployment-results/container-e2e.txt
