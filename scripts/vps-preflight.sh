#!/usr/bin/env bash
# Read-only inventory on a fresh dedicated Linux VPS; no deployment acceptance claim.
set -Eeuo pipefail
[[ $(uname -s) == Linux ]] || { echo 'Run on the target Linux VPS.' >&2; exit 1; }
echo 'Target: dedicated VPS, recommended minimum 1 CPU / 1 GB RAM.'
cat /etc/os-release
printf 'Architecture: '; uname -m
printf 'Available CPUs: '; nproc
free -m
awk '/^MemTotal:/ { total=int($2/1024); printf "Usable MemTotal: %d MiB; space above combined 736 MiB container RAM caps: %d MiB\n", total, total-736; if (total-736<192) print "Review actual host memory budget before startup; no limits were changed." }' /proc/meminfo
df -h /
findmnt -no FSTYPE -T /
swapon --show
echo 'Current TCP listeners (verify actual SSH port and free TCP 80/443):'
ss -lnt
if command -v docker >/dev/null 2>&1; then
  if docker info --format 'Docker server: {{.ServerVersion}}; cgroup version: {{.CgroupVersion}}; CPUs: {{.NCPU}}; memory bytes: {{.MemTotal}}'; then
    docker compose version
    docker network ls
  else
    echo 'Docker daemon not ready or access denied; this is not an acceptance PASS.'
  fi
else
  echo 'Docker not installed; install from the official OS-specific instructions.'
fi
echo 'Inventory complete; firewall, swap, Docker, HTTPS and restore acceptance still require setup/verification.'
