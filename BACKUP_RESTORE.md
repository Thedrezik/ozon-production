# Native backup and restore — task 040

Production uses host PostgreSQL utilities and ordinary Linux directories; Docker
is not required. See [deployment runbook](docs/DEPLOYMENT.md). Task 034 remains
pending until a complete native Linux drill succeeds on the VPS.

## Backup

`sudo bash scripts/backup.sh` takes the common operations lock, checks staging
space, stops an active API for a consistent DB/uploads snapshot, runs local
`pg_dump --format=custom`, validates it with `pg_restore --list`, archives private
uploads, and atomically publishes a root-only bundle in
`/var/lib/ozon-production/backups`. It restarts an API it stopped, even on backup
failure: backup has not changed business data. During update the API is already
stopped and remains stopped. No database/Ozon/master secrets enter command argv,
archive or manifest; password is supplied through the child process environment.

Members: `database.dump`, `uploads.tar.gz`, `README.txt`. Default newest 3 archives
plus any rollback-referenced snapshot, overridden by RETENTION_COUNT. UTC names
include random collision protection; operations are serialized. Watch archive
bytes, not just count. Stage and final archive coexist temporarily; require free
disk. Daily `ozon-backup.timer` runs at 02:00 UTC; failure appears in journald.
Alert/inspect failures; a same-VPS backup does not protect against disk/VPS loss.
Copy verified bundles off-host using authenticated encrypted transport/storage.
Store master key and env separately in encrypted operator storage; a restored
credential database is useless without the matching encryption master key.

```sh
sudo ls -lh /var/lib/ozon-production/backups
sudo tar -tzf /var/lib/ozon-production/backups/backup-TIMESTAMP-RANDOM.tar.gz
sudo systemctl list-timers ozon-backup.timer
sudo journalctl -u ozon-backup.service -n 50 --no-pager
```

## Destructive restore

```sh
sudo systemctl stop ozon-production.service
sudo bash scripts/restore.sh backup-TIMESTAMP-RANDOM.tar.gz
# Restore script validates both archive layers and dump, then asks for RESTORE.
sudo systemctl start ozon-production.service
sudo bash scripts/smoke.sh
```

Requires a stopped API. Manual invocation always requires a terminal and RESTORE;
explicit `--yes`/`--non-interactive` is available for an authorized automated
acceptance/recovery. Filename must be a local bundle name, not a path/symlink.
Both tar layers reject traversal, links, devices and duplicate entries before
upload extraction. `--database-only` / `--uploads-only` are available.

DB uses `pg_restore --single-transaction --exit-on-error --clean --if-exists
--no-owner --no-privileges`; it does not drop/recreate the live DB and validates
connectivity afterward. Uploads stage in a sibling directory on the same
filesystem; old directory is retained until new directory promotion succeeds.
Ownership returns to ozon-app, private mode. Process/power loss between renames
may leave `.uploads-restore.*`; inspect/restore its old directory before restart.
Backend remains stopped after restore; verify restored migration head and read
queries against the intended code before manually starting. For normal matching
release use readiness/smoke; apply newer migrations only as a deliberate update.

DB and uploads are not jointly atomic. A failure after DB commit requires recovery
while writers remain stopped. `--clean` only removes objects included in the dump;
post-update extra tables can remain. For incompatible schema rollback restore to
a separate database, validate with old code, then change the private URL. Never
blindly downgrade/recreate production data. Normal application rollback uses
`scripts/rollback-native.sh`, which restores the saved release/env/snapshot and
requires its own confirmation; post-update writes are lost.

## Mandatory isolated Linux drill

After a native release/virtualenv exists:

```sh
sudo bash scripts/backup-restore-native-drill.sh
```

Aliases: `backup-restore-drill.sh` now dispatches to this native drill. It creates
an entirely separate PostgreSQL 15 initdb cluster under a fresh
`/tmp/ozon-native-drill-*`, accepts only a private Unix socket and rejects host
connections. Its env is synthetic with Ozon/Telegram/background integrations off.
It applies real migrations with the release interpreter, writes DB/upload probes,
backs up, changes/adds rows/files, restores, verifies original row/file and removal
of added row/file, runs migrations again, verifies exact newest-2 retention, then
stops/removes only its generated cluster/root. Production env/DB/uploads are never
opened. On failure the cluster is stopped and evidence retained for inspection.
An incomplete stop prevents cleanup. Supply DRILL_CODE/DRILL_VENV only to use an
existing candidate release before the first service deployment. Avoid concurrently
running the production API/build and this extra cluster on the 1 GB target.

Synthetic `test-backups.sh` and `test-production-flow.sh` exercise local tar/files,
confirmation/retention/failure ordering with fake PostgreSQL/systemd commands.
They do not prove a Linux/PostgreSQL restore. `*-compose.sh`, the Windows PowerShell
runner and Compose overlays remain development/test fixtures only; historical
Windows backup creation is not production acceptance.
