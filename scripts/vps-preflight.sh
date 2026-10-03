#!/usr/bin/env bash
# Read-only target inventory; no acceptance claim.
set -Eeuo pipefail
[[ $(uname -s) == Linux ]] || { echo 'Run on target Linux VPS.' >&2; exit 1; }
cat /etc/os-release
uname -m
nproc
free -h
df -h /
swapon --show
ss -lntup
ip -br addr
journalctl --disk-usage
if [[ -d /opt/ozon-production ]]; then du -sh /opt/ozon-production /var/lib/ozon-production /var/lib/caddy; fi
echo 'Native target: Debian 12 x86_64, 1 CPU / 1 GB RAM / ~7 GB SSD / 1 GiB emergency swap.'
