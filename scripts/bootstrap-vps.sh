#!/usr/bin/env bash
# Run locally on a fresh Debian 12 VPS through sudo; contains no credentials.
set -Eeuo pipefail
umask 077
fail() { echo "$*" >&2; exit 1; }
[[ $# == 2 || ( $# == 3 && $3 == --agent-sudo ) ]] || fail 'Usage: sudo bash bootstrap-vps.sh DEPLOY_USER SSH_PUBLIC_KEY_FILE [--agent-sudo]'
agent_sudo=${3:-}
deploy_user=$1
public_key=$2
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || fail 'Requires Linux x86_64.'
[[ $EUID == 0 ]] || fail 'Run through sudo on the VPS.'
. /etc/os-release
[[ $ID == debian && $VERSION_ID == 12 ]] || fail 'Requires Debian 12.'
[[ $deploy_user =~ ^[a-z][a-z0-9_-]{0,31}$ && $deploy_user != root ]] || fail 'Choose a separate deploy user.'
[[ -f $public_key ]] || fail 'SSH public key file missing.'
grep -Eq '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-[^ ]+|sk-ssh-ed25519@openssh.com|sk-ecdsa-sha2-nistp256@openssh.com) [A-Za-z0-9+/=]+( |$)' "$public_key" || fail 'Supply a public key, never a private key.'
ssh-keygen -l -f "$public_key" >/dev/null || fail 'Invalid SSH public key.'
[[ $(wc -l < "$public_key") -le 1 ]] || fail 'Supply one SSH public key.'
# Preserve every configured listener and the current session port before UFW.
mapfile -t ssh_ports < <(/usr/sbin/sshd -T | awk '$1 == "port" {print $2}')
[[ ${#ssh_ports[@]} -gt 0 ]] || fail 'Cannot determine SSH ports.'
if [[ -n ${SSH_CONNECTION:-} ]]; then ssh_ports+=("${SSH_CONNECTION##* }"); fi
for port in "${ssh_ports[@]}"; do
  [[ $port =~ ^[0-9]+$ && $port -ge 1 && $port -le 65535 ]] || fail 'Invalid SSH port.'
done
# Native packages only. Debian Python remains untouched; app uses managed 3.12.
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
apt-get install -y --no-install-recommends postgresql-15 postgresql-client-15 python3 python3-venv ca-certificates curl git openssh-client sudo ufw rsync util-linux xz-utils unzip logrotate
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
uv_version=0.12.20
uv_asset=uv-x86_64-unknown-linux-gnu.tar.gz
uv_base="https://releases.astral.sh/github/uv/releases/download/$uv_version"
curl -fsSL "$uv_base/$uv_asset" -o "$work/$uv_asset"
curl -fsSL "$uv_base/$uv_asset.sha256" -o "$work/uv.sha256"
python3 - "$work/$uv_asset" "$work/uv.sha256" <<'PY'
import hashlib,pathlib,sys
archive,check=map(pathlib.Path,sys.argv[1:])
assert hashlib.sha256(archive.read_bytes()).hexdigest() == check.read_text().split()[0]
PY
tar -xzf "$work/$uv_asset" -C "$work"
install -m 755 "$work/uv-x86_64-unknown-linux-gnu/uv" /usr/local/bin/uv
install -d -m 755 /opt/ozon-production /opt/ozon-production/python
# Build-only Node/npm. Debian 12 Node 18 cannot satisfy this frontend lockfile.
node_version=22.23.3
node_asset="node-v${node_version}-linux-x64.tar.xz"
node_base="https://nodejs.org/dist/v$node_version"
if [[ ! -x /opt/ozon-production/node/bin/node ]]; then
  [[ ! -e /opt/ozon-production/node && ! -L /opt/ozon-production/node ]] || fail 'Review existing Node directory.'
  curl -fsSL "$node_base/$node_asset" -o "$work/$node_asset"
  curl -fsSL "$node_base/SHASUMS256.txt" -o "$work/node-checksums"
  python3 - "$work/$node_asset" "$work/node-checksums" <<'PY'
import hashlib,pathlib,sys
archive,check=map(pathlib.Path,sys.argv[1:])
entries=dict((line.split()[1].lstrip('*'),line.split()[0]) for line in check.read_text().splitlines() if line.strip())
assert hashlib.sha256(archive.read_bytes()).hexdigest() == entries[archive.name]
PY
  mkdir /opt/ozon-production/node
  tar -xJf "$work/$node_asset" --strip-components=1 -C /opt/ozon-production/node
fi
[[ $(/opt/ozon-production/node/bin/node --version) == "v$node_version" ]] || fail 'Review different installed build Node version.'
for command in node npm npx; do
  if [[ -e /usr/local/bin/$command && ! -L /usr/local/bin/$command ]]; then fail "Review existing /usr/local/bin/$command."; fi
  ln -sfn "/opt/ozon-production/node/bin/$command" "/usr/local/bin/$command"
done
export UV_PYTHON_INSTALL_DIR=/opt/ozon-production/python UV_NO_CACHE=1
uv python install 3.12
find /opt/ozon-production/python -type d -exec chmod a+rx {} +
find /opt/ozon-production/python -type f -exec chmod a+r {} +
# Caddy upstream pinned binary, checksum verified; no Go toolchain required.
caddy_version=2.11.6
caddy_asset="caddy_${caddy_version}_linux_amd64.tar.gz"
caddy_base="https://github.com/caddyserver/caddy/releases/download/v$caddy_version"
curl -fsSL "$caddy_base/$caddy_asset" -o "$work/$caddy_asset"
curl -fsSL "$caddy_base/caddy_${caddy_version}_checksums.txt" -o "$work/caddy-checksums"
python3 - "$work/$caddy_asset" "$work/caddy-checksums" <<'PY'
import hashlib,pathlib,sys
archive,check=map(pathlib.Path,sys.argv[1:])
entries=dict((line.split()[1].lstrip('*'),line.split()[0]) for line in check.read_text().splitlines() if line.strip())
assert hashlib.sha512(archive.read_bytes()).hexdigest() == entries[archive.name]
PY
tar -xzf "$work/$caddy_asset" -C "$work" caddy
install -m 755 "$work/caddy" /usr/local/bin/caddy
for service_user in ozon-app caddy; do
  if ! id "$service_user" >/dev/null 2>&1; then
    useradd --system --home-dir "/var/lib/$service_user" --shell /usr/sbin/nologin "$service_user"
  fi
  [[ $(id -u "$service_user") -ne 0 ]] || fail 'Service user must be unprivileged.'
done
install -d -m 755 /var/lib/ozon-production /etc/caddy /opt/ozon-production/releases
install -d -m 700 /etc/ozon-production /var/lib/ozon-production/private /var/lib/ozon-production/backups
install -d -m 700 -o ozon-app -g ozon-app /var/lib/ozon-production/uploads
install -d -m 700 -o caddy -g caddy /var/lib/caddy
install -d -m 755 /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/ozon.conf <<'CONF'
[Journal]
SystemMaxUse=64M
RuntimeMaxUse=16M
MaxRetentionSec=7day
SystemKeepFree=512M
CONF
systemctl restart systemd-journald
# Debian's PostgreSQL logs are separate from journald; replace package rotation.
cat > /etc/logrotate.d/postgresql-common <<'CONF'
/var/log/postgresql/*.log {
    daily
    rotate 3
    maxsize 16M
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    su root root
}
CONF
# Bootstrap is self-contained; full tuning is installed from release on deploy.
cat > /etc/postgresql/15/main/conf.d/ozon.conf <<'CONF'
listen_addresses = '127.0.0.1'
password_encryption = 'scram-sha-256'
max_connections = 20
shared_buffers = 64MB
work_mem = 2MB
maintenance_work_mem = 32MB
CONF
systemctl enable --now postgresql
systemctl restart postgresql@15-main
printf 'vm.swappiness=10\n' > /etc/sysctl.d/99-ozon-swappiness.conf
sysctl -p /etc/sysctl.d/99-ozon-swappiness.conf
apt-get clean
if [[ -z $(swapon --show --noheadings) ]]; then
  if awk '$1 !~ /^#/ && $3 == "swap" && $1 != "/swapfile" {found=1} END {exit !found}' /etc/fstab; then
    fail 'Configured inactive swap exists; review/activate it instead of adding swap.'
  fi
  swapfile=/swapfile
  if [[ -e $swapfile || -L $swapfile ]]; then
    # Resume only a valid, root-owned secure swap file; never overwrite it.
    [[ -f $swapfile && ! -L $swapfile && $(stat -c %u:%a "$swapfile") == 0:600 ]] || fail 'Review existing swapfile.'
    [[ $(blkid -p -s TYPE -o value "$swapfile") == swap ]] || fail 'Existing file is not swap; retained.'
  else
    case $(findmnt -no FSTYPE -T /) in ext4|xfs) ;; *) fail 'Review filesystem-specific swap setup.' ;; esac
    [[ $(df -B1 --output=avail / | tail -n 1) -ge 2147483648 ]] || fail 'Need at least 2 GiB free before swap creation.'
    (set -o noclobber; : > "$swapfile")
    dd if=/dev/zero of="$swapfile" bs=1M count=1024 conv=notrunc status=none
    chmod 600 "$swapfile"
    mkswap "$swapfile"
  fi
  swapon "$swapfile"
  fstab_backup=$(mktemp /etc/fstab.ozon.XXXXXX)
  cp /etc/fstab "$fstab_backup"
  if ! awk '$1 == "/swapfile" {found=1} END {exit !found}' /etc/fstab; then
    printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
  fi
  if ! findmnt --verify --tab-file /etc/fstab; then
    cp "$fstab_backup" /etc/fstab
    fail 'fstab reverted; active swap retained. Review before reboot.'
  fi
else
  echo 'Existing swap retained; review size (target 1 GiB).'
fi
if ! id "$deploy_user" >/dev/null 2>&1; then
  adduser --disabled-password --gecos '' "$deploy_user"
fi
[[ $(id -u "$deploy_user") -ne 0 ]] || fail 'Deploy user must not be UID 0.'
usermod -aG sudo "$deploy_user"
if [[ $agent_sudo == --agent-sudo ]]; then
  # Explicit administrative authorization; revoke this file after deployment.
  printf '%s ALL=(ALL) NOPASSWD: ALL\n' "$deploy_user" > "/etc/sudoers.d/ozon-$deploy_user"
  chmod 440 "/etc/sudoers.d/ozon-$deploy_user"
  visudo -cf "/etc/sudoers.d/ozon-$deploy_user"
fi
user_home=$(getent passwd "$deploy_user" | cut -d: -f6)
[[ -d $user_home && ! -L $user_home ]] || fail 'Review deploy home.'
install -d -m 700 -o "$deploy_user" -g "$deploy_user" "$user_home/.ssh"
authorized="$user_home/.ssh/authorized_keys"
[[ ! -L $authorized ]] || fail 'Refusing symlink authorized_keys.'
touch "$authorized"
if ! grep -qxF -- "$(cat "$public_key")" "$authorized"; then
  printf '\n' >> "$authorized"
  cat "$public_key" >> "$authorized"
  printf '\n' >> "$authorized"
fi
chmod 600 "$authorized"
chown "$deploy_user:$deploy_user" "$authorized"
[[ ! -L /opt/ozon-production ]] || fail 'Review symlink application directory.'
install -d -m 755 -o "$deploy_user" -g "$deploy_user" /opt/ozon-production/repo
for port in "${ssh_ports[@]}"; do ufw allow "$port/tcp"; done
ufw allow 80/tcp
ufw allow 443/tcp
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
echo 'Bootstrap complete. Verify a second deploy-user SSH session before closing this one.'
echo 'For agent sudo use the explicit --agent-sudo option; revoke its sudoers file after use.'
echo 'Existing UFW rules retained; inspect ufw status and provider firewall for extra exposure.'
/usr/local/bin/caddy version
/usr/local/bin/uv --version
swapon --show
ufw status verbose
