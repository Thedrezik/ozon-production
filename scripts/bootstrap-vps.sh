#!/usr/bin/env bash
# Run locally on a fresh Debian 12 VPS through sudo; contains no credentials.
set -Eeuo pipefail
umask 077
fail() { echo "$*" >&2; exit 1; }
[[ $# == 2 ]] || fail 'Usage: sudo bash bootstrap-vps.sh DEPLOY_USER SSH_PUBLIC_KEY_FILE'
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
# Refuse incompatible Docker installs rather than removing packages/data.
for package in docker.io docker-compose podman-docker containerd runc; do
  if [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true) == 'install ok installed' ]]; then
    fail "Review conflicting package $package before bootstrap; nothing removed."
  fi
done
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
apt-get install -y ca-certificates curl git openssh-client sudo ufw python3 rsync util-linux
install -m 0755 -d /etc/apt/keyrings
if [[ ! -s /etc/apt/keyrings/docker.asc ]]; then
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
fi
chmod 0644 /etc/apt/keyrings/docker.asc
repo=$(mktemp)
trap 'rm -f -- "$repo"' EXIT
cat > "$repo" <<'APT'
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: bookworm
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
APT
if [[ -e /etc/apt/sources.list.d/docker.list ]]; then
  fail 'Review existing docker.list to avoid duplicate apt repositories.'
fi
if [[ -e /etc/apt/sources.list.d/docker.sources ]]; then
  cmp -s "$repo" /etc/apt/sources.list.d/docker.sources || fail 'Existing Docker repository differs; review manually.'
else
  install -m 0644 "$repo" /etc/apt/sources.list.d/docker.sources
fi
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
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
usermod -aG sudo,docker "$deploy_user"
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
install -d -m 750 -o "$deploy_user" -g "$deploy_user" /opt/ozon-production
for port in "${ssh_ports[@]}"; do ufw allow "$port/tcp"; done
ufw allow 80/tcp
ufw allow 443/tcp
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
echo 'Bootstrap complete. Verify a second deploy-user SSH session before closing this one.'
echo 'Set deploy sudo password locally with: passwd DEPLOY_USER (never send it to an agent).'
echo 'Existing UFW rules retained; inspect ufw status and provider firewall for extra exposure.'
docker compose version
swapon --show
ufw status verbose
