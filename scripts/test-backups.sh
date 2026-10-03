#!/usr/bin/env bash
# Execute real shell archive/retention/confirmation behavior with synthetic PG.
source "$(dirname "$0")/native-test-fixture.sh"
printf original > "$work/uploads/probe.txt"
export RETENTION_COUNT=2
bash "$work/scripts/backup.sh" > "$work/first"
archive=$(sed -n 's/^Backup created: .*\/\(backup-[^ ]*\).*/\1/p' "$work/first")
[[ -s $work/backups/$archive ]]
if bash "$work/scripts/restore.sh" "$archive" > "$work/denied" 2>&1; then exit 1; fi
grep -q 'confirmation required' "$work/denied"
printf changed > "$work/uploads/probe.txt"
printf extra > "$work/uploads/after.txt"
bash "$work/scripts/restore.sh" "$archive" --uploads-only --yes >/dev/null
[[ $(cat "$work/uploads/probe.txt") == original && ! -e $work/uploads/after.txt ]]
if FAIL_VALIDATION=true bash "$work/scripts/restore.sh" "$archive" --yes >/dev/null 2>&1; then exit 1; fi
sleep 1; bash "$work/scripts/backup.sh" >/dev/null
sleep 1; bash "$work/scripts/backup.sh" >/dev/null
[[ $(find "$work/backups" -name 'backup-*.tar.gz' | wc -l) == 2 && ! -e $work/backups/$archive ]]
before=$(find "$work/backups" -name 'backup-*.tar.gz' | sort)
if FAIL_BACKUP=true bash "$work/scripts/backup.sh" >/dev/null 2>&1; then exit 1; fi
[[ $(find "$work/backups" -name 'backup-*.tar.gz' | sort) == "$before" ]]
[[ -z $(find "$work/backups" -name '.backup.*' -print) ]]
echo 'PASS: synthetic native backup publication/retention, guarded restore, real uploads replacement and failure cleanup.'
