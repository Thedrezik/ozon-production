# Backup and restore

Compose already mounts the persistent `uploads` and `backups` volumes in the backend at `/data/uploads` and `/data/backups`. Backup archives contain a PostgreSQL custom-format dump, a gzip tar archive of the contents of `/data/uploads`, and a small manifest. Configuration files such as `.env` and external encryption keys are not archived. The complete database dump naturally includes stored password hashes and encrypted credential records; treat backups as private data and retain the credentials master key separately so restored encrypted records can be read. Archives are timestamped in UTC as `backup-YYYYMMDDTHHMMSSZ.tar.gz` and are mode-restricted when written.

Run commands from the repository root on the server. Ensure Compose is using the intended project and `.env` file; scripts never print environment values. Restore uses short-lived `docker compose run` containers to access the existing backend volumes, so the API backend can remain stopped throughout the operation.

## Manual backup

```sh
bash scripts/backup.sh
```

The script checks its required local tools, streams `pg_dump` from the PostgreSQL container and an archive from the backend container, publishes only after both succeed, then retains the newest 14 archives. Override with `RETENTION_COUNT=30 bash scripts/backup.sh`. Check the command exit code; any nonzero code means the operation did not finish cleanly.

## Daily schedule

For cron, add an entry for the deployment user (adjust the absolute checkout path):

```cron
15 2 * * * cd /opt/ozon-production && /usr/bin/flock -n /tmp/ozon-backup.lock /usr/bin/bash scripts/backup.sh >> /var/log/ozon-backup.log 2>&1
```

For a systemd timer, create a oneshot service with `WorkingDirectory=/opt/ozon-production` and `ExecStart=/usr/bin/bash scripts/backup.sh`; pair it with a timer using `OnCalendar=daily` and `Persistent=true`, then enable the timer. Keep the service's user and environment access consistent with the deployment's Docker Compose permissions. Review scheduler logs and alert on nonzero exits.

## Check a backup

List archives with `docker compose exec backend ls -lh /data/backups`. Validate the outer archive and its members:

```sh
docker compose exec backend sh -c 'tar -tzf /data/backups/backup-YYYYMMDDTHHMMSSZ.tar.gz'
```

A restore performs structural checks, validates a database dump with `pg_restore --list`, and validates the uploads tar before confirmation. Periodically perform a full restore drill against an isolated test database and uploads volume; do not use production data in automated tests.

## Restore

Stop the application first so it cannot write while files or the database are replaced. Choose a filename from `/data/backups`:

```sh
docker compose stop backend
bash scripts/restore.sh backup-YYYYMMDDTHHMMSSZ.tar.gz
docker compose run --rm --no-deps backend alembic upgrade head
docker compose start backend
```

Restore warns that selected data is destructive and requires typing `RESTORE` interactively. The `--yes` bypass is rejected except when the isolated automated drill's explicit mode, Compose overlay, generated volume prefix and project name are all present. Both dump validation and restore pass bytes through stdin without an input filename. [PostgreSQL 17 documentation](https://www.postgresql.org/docs/17/app-pgrestore.html) specifies that omitting the filename selects stdin; a literal `-` is a filename. Restore uses `--single-transaction --clean --if-exists`, so a SQL failure rolls back the database changes, without dropping the database first. Objects absent from the dump remain; unexpected dependencies can cause a safe rollback. `--database-only` restores just PostgreSQL; `--uploads-only` replaces files under `/data/uploads`. For uploads-only restore, keep the backend stopped and run:

```sh
bash scripts/restore.sh backup-YYYYMMDDTHHMMSSZ.tar.gz --uploads-only
```

Uploads are extracted into a temporary directory inside the uploads volume before existing files are moved aside. Command failures during replacement restore the saved entries; failed rollback retains recovery files and reports their path. Database-only restore does not modify uploaded files. PostgreSQL and filesystem changes cannot commit atomically together: if uploads fail after the database transaction commits, keep the app stopped and rerun restore. A process/power failure can leave recovery directories requiring manual inspection. Restore only trusted archives. Never point a restore drill at the production Compose project or its volumes.

## Isolated Windows Docker Desktop drill

The user's real Docker run on Windows confirmed isolated volumes without production mounts, successful migrations, PostgreSQL dump/uploads archive creation, publication in `/data/backups`, and failure cleanup restricted to drill resources. The harness later stopped at `Unexpected backup bundle members`. Full restore on Windows is **not authoritative** because of PowerShell/Git Bash/MSYS compatibility. Further manual Windows drill debugging is stopped; Windows SUCCESS is not required to complete task 030.

The existing runner is retained as an auxiliary tool:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup-restore-drill.ps1
```

The script is intended to choose a fresh project and volume prefix, check resolved volume names, run synthetic backup/restore verification and clean only the drill environment. Its noninteractive restore bypass is restricted to the isolated drill. Its intended final line is not evidence of a completed Linux deployment restore check:

```text
SUCCESS: isolated backup/restore drill passed; migrations, PostgreSQL, uploads, retention, and production volumes verified; drill containers and volumes removed.
```

The runner requires Docker Desktop, Git Bash installed under Program Files, and a configured repository `.env`. On failure, it prints the current stage and exits nonzero; it attempts cleanup only after the resolved volume names pass the drill-name guard again.

The Docker-free regression check evaluates every Docker command expression from the runner against a recording wrapper, including both cleanup paths, and verifies the production-volume guard:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-backup-drill-command-construction.ps1
```

## Mandatory Linux VPS restore check — task 034

Before production launch, task 034 **must** run and document a complete destructive `backup → modify → restore → verify` drill on the target Linux VPS with the actual Bash scripts. Use synthetic data, a separate Compose project and explicit unique PostgreSQL/uploads/backups volume names; check `docker compose config` before restore and cleanup. Never run the drill against operational data. A project name alone cannot isolate explicitly named production volumes.

The launch gate requires successful migrations, a published bundle containing `database.dump`, `uploads.tar.gz` and `README.txt`, confirmed changes to the synthetic DB marker and uploads after backup, a real PostgreSQL restore, the marker returned to `before-backup`, original upload content restored, and the post-backup upload removed. Verify retention keeps the newest archives, cleanup removes only drill containers/volumes, and production volumes are unchanged. Record commands and results in `DEPLOYMENT.md` and `docs/STATE.md`. Any failed assertion blocks production launch; synthetic tests and Windows backup creation do not substitute for this gate.

Linux operation remains `bash scripts/backup.sh` and `bash scripts/restore.sh BACKUP_FILENAME`; ordinary restore prompts for `RESTORE`. Linux automated checks can be run with:

```sh
bash -n scripts/backup.sh scripts/restore.sh scripts/test-backups.sh
bash scripts/test-backups.sh
```

These checks use mock PostgreSQL output and temporary synthetic uploads; they do not prove an actual PostgreSQL restore. Backup reads the database and uploads sequentially, not in one shared snapshot. For a consistent pre-update snapshot, pause application writes/uploads during backup. In a drill, make no concurrent changes during capture.

## Before an application update

Run a manual backup and confirm a new archive was published before applying migrations or replacing containers. Record its filename and ensure sufficient free disk space. Backups on the same VPS protect against operator errors but not disk loss; periodically copy archives to separately managed off-server storage using an authenticated, encrypted transfer. Keep encryption keys and application secrets in the deployment secret store, separately from the archive.
