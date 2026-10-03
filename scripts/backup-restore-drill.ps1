[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$script:Failed = $false
$script:DrillStarted = $false
$script:DrillCleaned = $false
$script:ConfigVerified = $false
$script:CurrentStage = 'initialization'
$script:ComposeArgs = @('compose', '-f', 'docker-compose.yml', '-f', 'docker-compose.backup-drill.yml')
$productionVolumes = @(
    'ozon-production_postgres_data',
    'ozon-production_uploads',
    'ozon-production_backups'
)
$drillVolumes = @()
$productionSnapshot = @{}
$previousEnvironment = @{}
foreach ($key in @('COMPOSE_PROJECT_NAME', 'COMPOSE_FILE', 'COMPOSE_OVERRIDE_FILE', 'DRILL_VOLUME_PREFIX', 'BACKUP_RESTORE_DRILL', 'RETENTION_COUNT', 'MSYS_NO_PATHCONV', 'MSYS2_ARG_CONV_EXCL')) {
    $previousEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}

function Write-Stage([string]$Message) {
    $script:CurrentStage = $Message
    Write-Host "`n== $Message =="
}

function Invoke-Docker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker $($Arguments -join ' ') exited with code $LASTEXITCODE" }
}

function Invoke-DockerCapture([string[]]$Arguments) {
    $result = @(& docker @Arguments)
    if ($LASTEXITCODE -ne 0) { throw "docker $($Arguments -join ' ') exited with code $LASTEXITCODE" }
    return ($result -join "`n")
}

function Get-ResolvedVolumes {
    $json = Invoke-DockerCapture ($script:ComposeArgs + @('config', '--format', 'json'))
    $config = $json | ConvertFrom-Json
    return @{
        postgres_data = [string]$config.volumes.postgres_data.name
        uploads       = [string]$config.volumes.uploads.name
        backups       = [string]$config.volumes.backups.name
        caddy_data    = [string]$config.volumes.caddy_data.name
        caddy_config  = [string]$config.volumes.caddy_config.name
    }
}

function Assert-SafeDrillConfig {
    if ($env:DRILL_VOLUME_PREFIX -notmatch '^ozon-backup-drill-[a-z0-9-]+$' -or
        $env:COMPOSE_PROJECT_NAME -cne $env:DRILL_VOLUME_PREFIX) {
        throw 'Invalid isolated drill project or volume prefix; restore and cleanup are forbidden'
    }
    $resolved = Get-ResolvedVolumes
    $expected = @{
        postgres_data = "${env:DRILL_VOLUME_PREFIX}_postgres_data"
        uploads       = "${env:DRILL_VOLUME_PREFIX}_uploads"
        backups       = "${env:DRILL_VOLUME_PREFIX}_backups"
        caddy_data    = "${env:DRILL_VOLUME_PREFIX}_caddy_data"
        caddy_config  = "${env:DRILL_VOLUME_PREFIX}_caddy_config"
    }
    foreach ($key in $expected.Keys) {
        if ($resolved[$key] -cne $expected[$key]) {
            throw "Unsafe Compose volume '$key': expected '$($expected[$key])', got '$($resolved[$key])'"
        }
        if ($resolved[$key] -in $productionVolumes) {
            throw "Production volume detected in Compose config: $($resolved[$key])"
        }
    }
    $script:drillVolumes = @($resolved.Values)
    $script:ConfigVerified = $true
    Write-Host 'Resolved drill volumes:'
    $resolved.GetEnumerator() | Sort-Object Key | ForEach-Object { Write-Host "  $($_.Key): $($_.Value)" }
}

function Get-ProductionVolumeSnapshot {
    $allVolumeNamesText = Invoke-DockerCapture @('volume', 'ls', '-q')
    $allNames = @($allVolumeNamesText -split "`n" | Where-Object { $_ })
    $snapshot = @{}
    foreach ($name in $productionVolumes) {
        if ($name -in $allNames) {
            $snapshot[$name] = Invoke-DockerCapture @('volume', 'inspect', $name, '--format', '{{.CreatedAt}}|{{.Mountpoint}}')
        } else {
            $snapshot[$name] = $null
        }
    }
    return $snapshot
}

function Invoke-GitBash([string[]]$Arguments) {
    & $script:BashPath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Git Bash command '$($Arguments -join ' ')' exited with code $LASTEXITCODE" }
}

try {
    Write-Stage 'Checking Docker Desktop and Git Bash'
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker CLI was not found in PATH' }
    Invoke-Docker @('info')
    $bashCandidates = @(@(
        (Join-Path $env:ProgramFiles 'Git\bin\bash.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Git\bin\bash.exe')
    ) | Where-Object { $_ -and (Test-Path $_) })
    if (-not $bashCandidates) { throw 'Git Bash not found under Program Files' }
    $script:BashPath = $bashCandidates[0]

    Write-Stage 'Creating unique drill project and volume names'
    $suffix = [guid]::NewGuid().ToString('N').Substring(0, 10)
    $env:DRILL_VOLUME_PREFIX = "ozon-backup-drill-$((Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss'))-$suffix"
    $env:COMPOSE_PROJECT_NAME = $env:DRILL_VOLUME_PREFIX
    $env:COMPOSE_FILE = 'docker-compose.yml'
    $env:COMPOSE_OVERRIDE_FILE = 'docker-compose.backup-drill.yml'
    $env:BACKUP_RESTORE_DRILL = 'true'
    $env:MSYS_NO_PATHCONV = '1'
    $env:MSYS2_ARG_CONV_EXCL = '*'
    Remove-Item Env:RETENTION_COUNT -ErrorAction SilentlyContinue

    Write-Stage 'Checking resolved Compose volumes before creating resources'
    Assert-SafeDrillConfig
    $productionSnapshot = Get-ProductionVolumeSnapshot

    Write-Stage 'Starting isolated PostgreSQL and backend'
    $script:DrillStarted = $true
    Invoke-Docker ($script:ComposeArgs + @('up', '-d', '--build', 'backend'))

    Write-Stage 'Applying Alembic migrations'
    Invoke-Docker ($script:ComposeArgs + @('exec', 'backend', 'alembic', 'upgrade', 'head'))

    Write-Stage 'Creating synthetic database and uploads data'
    $sql = "CREATE TABLE IF NOT EXISTS backup_drill_probe (id integer PRIMARY KEY, marker text NOT NULL); TRUNCATE backup_drill_probe; INSERT INTO backup_drill_probe VALUES (1, 'before-backup');"
    Invoke-Docker ($script:ComposeArgs + @('exec', '-T', 'postgres', 'psql', '-U', 'ozon', '-d', 'ozon', '-v', 'ON_ERROR_STOP=1', '-c', $sql))
    Invoke-Docker ($script:ComposeArgs + @('exec', '-T', 'backend', 'sh', '-ec', 'printf %s upload-before-backup > /data/uploads/backup-drill-probe.txt'))

    Write-Stage 'Creating PostgreSQL and uploads backup'
    $backupOutput = @(& $script:BashPath 'scripts/backup-compose.sh')
    if ($LASTEXITCODE -ne 0) { throw "backup.sh exited with code $LASTEXITCODE" }
    $backupOutput | ForEach-Object { Write-Host $_ }
    $backupText = $backupOutput -join "`n"
    $match = [regex]::Match($backupText, 'Backup created: /data/backups/(backup-[^ ]+\.tar\.gz)')
    if (-not $match.Success) { throw 'Could not read timestamped archive name from backup.sh output' }
    $script:BackupName = $match.Groups[1].Value

    Write-Stage 'Validating bundle and uploads archive structure'
    $bundleMembers = Invoke-DockerCapture ($script:ComposeArgs + @('exec', '-T', 'backend', 'tar', '-tzf', "/data/backups/$script:BackupName"))
    $actualMembers = @($bundleMembers -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Sort-Object)
    if (($actualMembers -join '|') -cne 'README.txt|database.dump|uploads.tar.gz') { throw 'Unexpected backup bundle members' }
    $uploadCheck = 'work=$(mktemp -d); trap ''rm -rf -- "$work"'' EXIT; tar -xzf "/data/backups/$1" -C "$work" uploads.tar.gz; tar -tzf "$work/uploads.tar.gz"'
    $uploadMembers = Invoke-DockerCapture ($script:ComposeArgs + @('exec', '-T', 'backend', 'sh', '-ec', $uploadCheck, 'sh', $script:BackupName))
    if ('./backup-drill-probe.txt' -notin @($uploadMembers -split "`n" | ForEach-Object { $_.Trim() })) { throw 'Synthetic upload missing from archive' }

    Write-Stage 'Mutating synthetic data after backup'
    $sql = "UPDATE backup_drill_probe SET marker = 'after-backup' WHERE id = 1;"
    Invoke-Docker ($script:ComposeArgs + @('exec', '-T', 'postgres', 'psql', '-U', 'ozon', '-d', 'ozon', '-v', 'ON_ERROR_STOP=1', '-c', $sql))
    Invoke-Docker ($script:ComposeArgs + @('exec', '-T', 'backend', 'sh', '-ec', 'printf %s upload-after-backup > /data/uploads/backup-drill-after.txt'))

    Write-Stage 'Rechecking isolated volume names before destructive restore'
    Assert-SafeDrillConfig
    Invoke-Docker ($script:ComposeArgs + @('stop', 'backend'))

    Write-Stage 'Restoring the isolated drill backup'
    Invoke-GitBash @('scripts/restore-compose.sh', $script:BackupName, '--yes')

    Write-Stage 'Checking migrations and starting restored backend'
    Invoke-Docker ($script:ComposeArgs + @('run', '--rm', '--no-deps', 'backend', 'alembic', 'upgrade', 'head'))
    Invoke-Docker ($script:ComposeArgs + @('up', '-d', 'backend'))

    Write-Stage 'Verifying database and uploads were restored'
    $marker = Invoke-DockerCapture ($script:ComposeArgs + @('exec', '-T', 'postgres', 'psql', '-U', 'ozon', '-d', 'ozon', '-t', '-A', '-c', 'SELECT marker FROM backup_drill_probe WHERE id = 1;'))
    if ($marker.Trim() -cne 'before-backup') { throw "Database marker was not restored; got '$($marker.Trim())'" }
    $uploadContent = Invoke-DockerCapture ($script:ComposeArgs + @('exec', '-T', 'backend', 'sh', '-ec', 'cat /data/uploads/backup-drill-probe.txt'))
    if ($uploadContent.Trim() -cne 'upload-before-backup') { throw 'Original upload content was not restored' }
    Invoke-Docker ($script:ComposeArgs + @('exec', '-T', 'backend', 'sh', '-ec', 'test ! -e /data/uploads/backup-drill-after.txt'))

    Write-Stage 'Checking retention with a limit of two archives'
    $env:RETENTION_COUNT = '2'
    1..3 | ForEach-Object {
        Start-Sleep -Seconds 1
        $output = @(& $script:BashPath 'scripts/backup-compose.sh')
        if ($LASTEXITCODE -ne 0) { throw "Retention backup run $_ failed with code $LASTEXITCODE" }
        $output | ForEach-Object { Write-Host $_ }
    }
    $count = Invoke-DockerCapture ($script:ComposeArgs + @('exec', '-T', 'backend', 'sh', '-ec', 'n=0; for f in /data/backups/backup-*.tar.gz; do [ -f "$f" ] || continue; n=$((n+1)); done; echo "$n"'))
    if ([int]$count.Trim() -ne 2) { throw "Retention expected 2 archives, found $($count.Trim())" }

    Write-Stage 'Removing only the verified drill project and volumes'
    Assert-SafeDrillConfig
    Invoke-Docker ($script:ComposeArgs + @('down', '--volumes', '--remove-orphans'))
    $script:DrillCleaned = $true
    $remainingVolumeNamesText = Invoke-DockerCapture @('volume', 'ls', '-q')
    $remaining = @($remainingVolumeNamesText -split "`n" | Where-Object { $_ })
    foreach ($name in $script:drillVolumes) {
        if ($name -in $remaining) { throw "Drill volume remains after cleanup: $name" }
    }

    Write-Stage 'Verifying production volumes are unchanged'
    $afterProductionSnapshot = Get-ProductionVolumeSnapshot
    foreach ($name in $productionVolumes) {
        if ($afterProductionSnapshot[$name] -cne $productionSnapshot[$name]) {
            throw "Production volume changed during drill: $name"
        }
    }
} catch {
    $script:Failed = $true
    Write-Error "FAILED during '$script:CurrentStage': $($_.Exception.Message)" -ErrorAction Continue
} finally {
    if ($script:DrillStarted -and -not $script:DrillCleaned -and $script:ConfigVerified) {
        try {
            Write-Stage 'Failure cleanup: removing verified drill resources'
            Assert-SafeDrillConfig
            Invoke-Docker ($script:ComposeArgs + @('down', '--volumes', '--remove-orphans'))
            $script:DrillCleaned = $true
        } catch {
            $script:Failed = $true
            Write-Error "Cleanup failed; drill resources may remain. Verify volume names manually. $($_.Exception.Message)" -ErrorAction Continue
        }
    }
    foreach ($key in $previousEnvironment.Keys) {
        if ($null -eq $previousEnvironment[$key]) {
            Remove-Item "Env:$key" -ErrorAction SilentlyContinue
        } else {
            Set-Item "Env:$key" $previousEnvironment[$key]
        }
    }
}

if ($script:Failed) { exit 1 }
Write-Host "`nSUCCESS: isolated backup/restore drill passed; migrations, PostgreSQL, uploads, retention, and production volumes verified; drill containers and volumes removed."
exit 0
