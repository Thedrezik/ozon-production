# Native Debian production deployment — task 040

Prepared 2026-10-03; production **not deployed**. Task 034 remains **pending**.
Docker is allowed only for development/tests. No Docker daemon, Compose, images,
container networks/limits or named volumes are required by production.

## Target and first step after renting a VPS

Dedicated Debian 12, x86_64, 1 CPU, 1 GB RAM, approximately 7 GB SSD,
public IPv4, 1 GiB emergency swap, approximately 10 FBS orders/day.
First SSH login: perform this read-only inventory before changing anything:

```sh
cat /etc/os-release
uname -m
nproc
free -h
df -h /
swapon --show
ss -lntup
ip -br addr
```

Keep the original SSH session open; confirm a second deploy-user session after
firewall setup. Check provider firewall too. No real deployment is authorized
or performed by this preparation task.

## Architecture and layout

- Debian PostgreSQL 15 service; loopback TCP 5432 and local Unix socket only.
- Separate `ozon-app` system user without login/sudo, Python 3.12 virtualenv,
  one Uvicorn worker on 127.0.0.1:8000; logs through journald.
- Pinned Caddy 2.11.6 installed system-wide and run as `caddy.service`/user `caddy`.
  Only TCP 80/443 are public; static React PWA + `/api/*` proxy + SSE.
- Node/npm run only during frontend build. No Node/Vite runtime server.
  Redis/Celery are absent. SQLAlchemy pool stays 2 + 1, timeout 3 s.

| Path | Ownership/access | Purpose |
| --- | --- | --- |
| /opt/ozon-production/repo | deploy user, no secrets | Git release source |
| /opt/ozon-production/python | root, service-readable | Managed Python 3.12 |
| /opt/ozon-production/releases | root, service-readable | Current + previous code/venv/dist |
| /opt/ozon-production/current | root-managed symlink | Active immutable release |
| /etc/ozon-production/production.env | root:root 600, parent 700 | Backend secrets |
| /etc/ozon-production/caddy.env | root:root 600 | Public DOMAIN only |
| /var/lib/ozon-production/uploads | ozon-app 700 | Private authenticated photos |
| /var/lib/ozon-production/backups | root 700 | DB/uploads bundles |
| /var/lib/ozon-production/private | root 700 | Lock/rollback record/private env snapshot |
| /var/lib/caddy | caddy 700 | Persistent certificates/renewal state |

Systemd loads the private env as root before dropping service privileges. The
API can write uploads, not code/backups/secrets. Caddy never receives DB/Ozon keys.
Env is plain `KEY=value`, no shell quotes/expansion; scripts parse it as data.
Do not `source` it, enable `set -x`, or attach its contents to chat/logs.

Debian 12's system Python 3.11 stays intact. Bootstrap installs checksum-verified
[pinned uv 0.12.20](https://github.com/astral-sh/uv/releases/tag/0.12.20), then a
[managed Python 3.12](https://docs.astral.sh/uv/guides/install-python/). This uses
Astral's standalone distribution; uv has no daemon and is used only for setup.
Bootstrap verifies upstream Caddy SHA512 too. No Python/Go source build on VPS.
A successful release records `installed-requirements.txt`; rollback keeps that
release's actual virtualenv, without resolving dependencies again. Dependencies
in requirements are ranges, so a new release build is not byte-reproducible;
inspect recorded versions and audit before launch. OS/Caddy/Python binary upgrades
are separate maintenance and are not reverted by application rollback.

## Agent SSH deployment

Give the agent a separate public SSH key authorization, never a root password or
private key in chat. Generate a temporary ed25519 key **locally outside the repo**,
mode 600 (Windows: restrict ACL to the current user). Agent uses the local key path
with SSH `IdentityFile`/`IdentitiesOnly yes`; do not paste key material. Verify the
VPS host fingerprint through the provider console before accepting it. Do not
use `StrictHostKeyChecking=no` or forward a personal SSH agent to the VPS.

Bootstrap accepts one public key. A passwordless deploy user has sudo group but
needs locally configured sudo authentication. For an authorized non-interactive
coding-agent session explicitly pass `--agent-sudo`: this creates
`/etc/sudoers.d/ozon-deploy` with NOPASSWD administrative access. This is root-level
maintenance authority, separate from the unprivileged runtime account. Use a
short-lived key/user, restrict source IP in provider firewall/authorized_keys
where practical. Agent runs `sudo -n`, so missing authorization fails promptly.

After acceptance, remove the exact temporary public-key line from deploy's
`authorized_keys`, delete its sudoers file and local temporary private key, and
close active agent SSH sessions (key deletion does not terminate existing ones).
Keep a tested operator SSH key/provider console. A permanent deploy identity can
instead retain a dedicated key and explicit administrative authorization.

Private repository: create a separate read-only GitHub deploy key on the VPS,
add only its public half in repository Settings → Deploy keys, without write
access. Configure `Host github-ozon`, HostName github.com, User git,
IdentityFile to that VPS-private key, IdentitiesOnly yes. Verify
[GitHub host fingerprints](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints).
No GitHub password/token is put in scripts/env/repository. Clone as deploy user:

```sh
git clone git@github-ozon:OWNER/REPO.git /opt/ozon-production/repo
```

Offline delivery alternative: scp/rsync a clean Git bundle + release artifacts
excluding `.env*`, `.venv`, node_modules, uploads, backups and operational data;
clone the bundle into the same repo path and provide an accessible `origin` for
fetch. A plain archive without Git history cannot drive these update scripts.
For a private origin, agent SSH access and GitHub read-only access are two
separate keys; revoke temporary SSH access independently.

## Automated bootstrap and first deploy

Transfer `bootstrap-vps.sh` plus the **public** key with scp. Bootstrap is
self-contained, verifies Debian 12/x86_64, updates apt, installs PostgreSQL,
Python/runtime utilities, Git, curl, UFW, rsync and
util-linux; installs Caddy/uv and build-only Node 22.23.3/npm with verified checksums.
Debian Node 18 does not satisfy the lockfile; the official standalone
[Node binary](https://nodejs.org/download/release/latest-v22.x/) avoids the apt npm
dependency tree. Python dependencies use binary wheels; a C/Go compiler is not installed. It creates separate users,
FHS directories, 1 GiB swap only if none exists, preserves configured SSH ports
and existing UFW rules, opens 80/443, caps logs, and never installs Docker.
It retains existing swap/files; filesystem or ambiguous swap needs review.
Repeated bootstrap is maintenance: apt upgrade/PostgreSQL restart are intentional;
run in a maintenance window and inspect existing firewall rules.

```sh
sudo -n bash /tmp/bootstrap-vps.sh deploy /tmp/deploy.pub --agent-sudo
# After read-only Git clone as deploy:
cd /opt/ozon-production/repo
sudo -n bash scripts/deploy-native.sh RELEASE_SHA PUBLIC_IPV4
```

The initial command generates secrets directly into the root-only private env,
provisions a nonsuperuser `ozon` role/owned database, builds a fresh virtualenv and
frontend, validates production settings, runs Alembic before startup, validates
Caddy/systemd, starts services, probes readiness, runs public smoke, and enables
the daily backup timer. No secrets are needed for frontend build. DB role has
DDL on its own schema for Alembic, no CREATEDB/CREATEROLE/replication/superuser;
this deliberately uses one application/migration role for this small instance.
Do not open 5432/8000/2019 in either firewall. Inspect listeners externally.

Create the first administrator locally, with hidden password entry:

```sh
cd /opt/ozon-production/current/backend
sudo python3 ../scripts/native-env.py /etc/ozon-production/production.env run -- \
  /opt/ozon-production/current/.venv/bin/python -m app.cli create-admin
```

This one-time user secret prompt is outside deploy/update; no account password
should be sent to the agent. Set Telegram values only by editing the private env
on VPS, configure all required fields together, and restart API. Back up the
Ozon master key separately in encrypted operator storage before credential entry.

## Trusted HTTPS directly on IPv4 (task 039 preserved)

Explicit Let's Encrypt ACME `shortlived` issuer and `default_sni` preserve trusted
IP HTTPS without purchasing a domain. No internal CA, separate ACME timer, or
`curl -k`. [Let's Encrypt IP certificates](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability)
are short lived; persistent `/var/lib/caddy` and Caddy's automatic renewal are
mandatory. [Systemd operation](https://caddyserver.com/docs/running) supports
Caddy's graceful reload. HTTP redirects to HTTPS; SPA fallback serves index.html;
API preserves `/api`, flushes SSE immediately, sets security headers and caps
request bodies at 21 MB. Application JSON/photo limits remain stricter; uploads
are never exposed as static files.

Verify normal browser/curl trust, IP SAN/issuer/notAfter, redirect, then smoke
again after an actual automatic renewal. `journalctl -u caddy` must show no
renewal failures. Issuance/renewal has **not** been tested against a public VPS.

Admin enters Client ID/API key in existing Admin → Ozon; encrypted DB storage,
read/minimal roles and FBS list/get import, confirmed tariff snapshots remain
unchanged. No Ozon API changes or live account tests in task 040. Webhook bare-IP
acceptance still requires Seller Check; it is neither promised nor ruled out.
Reconciliation remains a fallback every 900 s. See [OZON_API.md](OZON_API.md).
If Seller Check rejects IP, a free DuckDNS name pointed directly to the VPS is
an option: change DOMAIN/APP_PUBLIC_URL together and caddy.env, restart/reload,
smoke and repeat Seller Check. Reinstall PWA/login for the new origin. No CDN or
changes to source trust: native backend trusts only 127.0.0.1/32; Caddy overwrites
X-Ozon-Source-IP. Recheck official provider source ranges during acceptance.

## Update, failure and rollback

```sh
sudo -n bash /opt/ozon-production/repo/scripts/update-native.sh RELEASE_SHA
```

One command: lock → stop API → consistent backup → save old code/env recovery
record → git fetch/checkout immutable release → fresh dependencies → frontend
build → config check → Alembic upgrade → current symlink switch → restart API →
readiness → Caddy reload → public smoke → cleanup. Brief maintenance outage is
intentional: on 1 GB, build runs with API stopped. Node heap is capped at 384 MiB;
1 GiB swap is emergency reserve. Check target build peak before acceptance; if
build exceeds capacity, prebuild frontend off-host in a separately reviewed flow.
The script requires >=1 GiB free before staging; capacity is measured, not assumed.

Failure leaves API stopped and reports recovery instructions. Failed backup does
not change code or overwrite the prior rollback record. After successful backup,
`update-pending` blocks a second update until recovery; a failing migration cannot
start the API. Inspect `journalctl -u ozon-production`, disk and backup first.
A partially migrated DB must never be restarted with old code without recovery.

```sh
sudo bash scripts/rollback-native.sh
# Authorized agent recovery (destructive, explicit opt-in):
sudo -n bash scripts/rollback-native.sh --yes
```

Manual rollback requires ROLLBACK; automation can explicitly choose --yes.
It stops writers, restores the pre-update DB/uploads snapshot, restores saved
private env/config/old virtualenv, switches code, restarts and runs smoke.
This loses post-update writes; review the snapshot before confirmation. It does
not guess Alembic downgrade compatibility. DB credentials/master key must not
be rotated during an application update; rotate them as separate maintenance.
DB/uploads restoration is not jointly atomic and `pg_restore --clean` does not
remove objects absent from the dump. On schema incompatibility restore into a
separate database and verify before changing the private connection URL. Failures
keep API stopped and evidence for operator recovery. First-deploy failure has no
previous release: inspect/repair in place, preserving DB/env/uploads/Caddy data.

## Backup, retention and disk budget

```sh
sudo -n bash scripts/backup.sh
sudo systemctl stop ozon-production.service
sudo bash scripts/restore.sh backup-TIMESTAMP-RANDOM.tar.gz
sudo systemctl start ozon-production.service
sudo -n bash scripts/smoke.sh
```

See [BACKUP_RESTORE.md](../BACKUP_RESTORE.md). Daily native timer at 02:00 UTC
(05:00 Moscow), root-only bundles, newest 3 plus a protected rollback snapshot.
It creates a short maintenance outage. Off-host encrypted copies are mandatory
operator responsibility; local retention alone cannot protect disk loss.
The timer shares the update/restore lock; lock failure is logged as failure,
not a second concurrent backup. Inspect/alert on failed timers.

On approximately 7 GB SSD, 1 GiB is swap; OS/packages/DB/WAL/uploads/two virtualenvs
and restore staging consume the rest. This is a tight capacity target, not a
promise. No measured native RAM/disk totals exist yet. Journald max 64 MB persistent,
16 MB runtime, seven-day retention, 512 MB keep-free; PostgreSQL logrotate daily,
three compressed rotations, maxsize 16 MB checked by logrotate (not a hard cap).
DB WAL max_wal_size=256 MB is a target and may be exceeded. No replication slots.
Backup count does not bound archive bytes: monitor their size, reduce retention
or move verified copies off-host if necessary. Protect the rollback snapshot.

Successful deployment retains only current/previous releases, removes candidate
node_modules/npm cache/__pycache__; pip uses --no-cache-dir and uv no cache.
Failure also removes candidate node_modules/npm cache; failed release evidence
may remain until recovery. Never blindly delete current/previous code, env,
DB/uploads or `/var/lib/caddy`. Git retains release history; periodically inspect
`.git` size and perform reviewed `git gc` during maintenance. apt cache is cleaned
at bootstrap. Build Node/npm can be removed after a verified build only if reinstalled for
subsequent builds; scripts assume their presence.

```sh
df -h
sudo du -sh /opt/ozon-production/* /var/lib/ozon-production/* /var/lib/postgresql /var/lib/caddy /var/log
journalctl --disk-usage
free -h
vmstat 1
sudo systemctl status ozon-production.service caddy.service postgresql@15-main
sudo journalctl -u ozon-production.service -u caddy.service -n 100 --no-pager
```

## Docker versus native

| Aspect | Previous Docker deployment | Current native deployment |
| --- | --- | --- |
| RAM | Application + Docker/containerd/daemon overhead | Same app components; daemon overhead removed; measure RSS |
| Disk | Images/layers/build caches/volumes | Packages + two venv/dist releases; cache/release cleanup explicit |
| Idle processes | Containers plus daemon/shims | PostgreSQL/API/Caddy, no Node daemon |
| Startup | Engine, networks, volume mapping and Compose ordering | Debian packages, systemd and explicit migration/readiness |
| Update | Images and env orchestration | Single backup/build/migrate/restart/smoke command |
| Rollback | Prior image plus data compatibility recovery | Retained prior venv/code and guarded DB/uploads snapshot restore |
| Tradeoff | Better packaging/isolation | Fewer moving parts; OS/runtime upkeep and build peaks need care |

No fabricated MB savings, idle-process counts or capacity guarantee. Container
memory/swap/CPU/PID caps are removed from production; no equivalent unmeasured
hard systemd caps are imposed. Conservative PostgreSQL settings, one worker,
small pool and measured host headroom are the initial operating policy.

## Live acceptance — task 034 pending

Run the native drill before importing real data; after first deploy use:

```sh
sudo -n bash scripts/backup-restore-native-drill.sh
sudo -n bash scripts/smoke.sh
```

Drill uses a fresh PostgreSQL 15 initdb cluster with private Unix socket, synthetic
credentials/env, current virtualenv/migrations and isolated uploads/backups; no
TCP listener, production env/DB/volumes. On failure evidence is retained. Check
migrations, archive, DB/files mutation then restoration, newest retention and
isolated cleanup. This Linux drill remains a mandatory launch blocker.

Further gates: external port scan; trusted IP certificate/automatic renewal;
PostgreSQL audit trigger/concurrency; service restart/reboot persistence; measured
RSS/CPU/disk/swap/build and real concurrency/p95; authenticated two-browser SSE;
Ozon Seller Check/real minimal-role import/webhook/reconciliation/tariff; Telegram;
physical Android/PWA. Optional camera/Push gates only when enabled.
`SMOKE_COOKIE_JAR=/private/mode600-cookiejar sudo ...` should instead be passed via
`sudo env SMOKE_COOKIE_JAR=/private/mode600-cookiejar bash scripts/smoke.sh` so sudo
preserves only the explicit path; authenticated SSE probe is otherwise reported
not run. Provider/device tests need authorized accounts, never production load
or automated business tests against a live Ozon account. Docker live validation
is no longer a production acceptance criterion.

Operator work is about four one-time groups: verified SSH/public key access,
read-only repo/release delivery, private admin/provider configuration, and live
acceptance. Agent can run bootstrap/deploy/drill/smoke; normal update is one
command. User still owns account secrets and acceptance decisions.
