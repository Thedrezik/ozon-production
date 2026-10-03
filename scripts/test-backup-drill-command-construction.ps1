# Runs without Docker/Git Bash. Execute the actual runner's command expressions
# through a recording docker function, including both normal and failure cleanup.
$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'backup-restore-drill.ps1'
$restoreSource = Get-Content -Raw (Join-Path $PSScriptRoot 'restore-compose.sh')
if ($restoreSource -notmatch 'pg_restore --list\s*<"\$stage/database\.dump"' -or
    $restoreSource -match 'pg_restore[^\r\n]*\s-\s') {
    throw 'pg_restore validation must read stdin without an input filename (especially not -)'
}
if ($restoreSource -notmatch 'pg_restore --single-transaction --exit-on-error --clean --if-exists' -or
    $restoreSource -match '\b(dropdb|createdb)\b') {
    throw 'Database restore must be transactional and must not destroy the database before success'
}
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($runner, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw ($parseErrors | Out-String) }

foreach ($definition in $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    . ([scriptblock]::Create($definition.Extent.Text))
}
$prefixAssignment = $ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $node.Left.Extent.Text -eq '$script:ComposeArgs'
}, $true)
if (@($prefixAssignment).Count -ne 1) { throw 'Expected one shared Compose argument prefix' }
. ([scriptblock]::Create($prefixAssignment[0].Extent.Text))

function docker {
    $script:RecordedArguments = @($args)
    $script:CommandHistory += ,@($args)
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'compose' -and 'config' -in $args -and $script:MockConfig) {
        return ($script:MockConfig | ConvertTo-Json -Depth 8 -Compress)
    }
    return 'mock-output'
}

$script:CommandHistory = @()
$script:MockConfig = $null
$script:BackupName = 'backup-20261002T120000Z.tar.gz'
$sql = "SELECT 'a value with spaces';"
$bundleCheck = 'test -s "/data/backups/$1"'
$uploadCheck = 'tar -tzf "/data/backups/$1" | grep -Fx "./probe.txt"'
$name = 'ozon-production_uploads'
$composeOperations = @()
$composeCallCount = 0
$rootCallCount = 0
$calls = $ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.CommandAst] -and
    $node.GetCommandName() -in @('Invoke-Docker', 'Invoke-DockerCapture')
}, $true)
foreach ($call in $calls) {
    $script:RecordedArguments = $null
    . ([scriptblock]::Create($call.Extent.Text)) | Out-Null
    $argv = $script:RecordedArguments
    if (-not $argv) { throw "No docker invocation recorded for $($call.Extent.Text)" }
    if ($call.Extent.Text.Contains('$script:ComposeArgs')) {
        $expectedPrefix = @('compose', '-f', 'docker-compose.yml', '-f', 'docker-compose.backup-drill.yml')
        if (($argv[0..4] -join '|') -cne ($expectedPrefix -join '|')) {
            throw "Incorrect docker Compose command: $($argv -join ' ')"
        }
        $composeOperations += $argv[5]
        $composeCallCount++
        if ($sql -in $argv -and @($argv | Where-Object { $_ -ceq $sql }).Count -ne 1) {
            throw 'SQL argument was split during forwarding'
        }
    } else {
        if ($argv[0] -notin @('info', 'volume')) { throw "Unexpected root Docker command: $($argv -join ' ')" }
        $rootCallCount++
    }
}
foreach ($operation in @('config', 'up', 'exec', 'run', 'stop', 'down')) {
    if ($operation -notin $composeOperations) { throw "No regression coverage for compose $operation" }
}
if (@($composeOperations | Where-Object { $_ -eq 'down' }).Count -ne 2) {
    throw 'Both success cleanup and failure cleanup must be covered'
}

$savedPrefix = $env:DRILL_VOLUME_PREFIX
$savedProject = $env:COMPOSE_PROJECT_NAME
$productionVolumes = @('ozon-production_postgres_data', 'ozon-production_uploads', 'ozon-production_backups')
try {
    $env:DRILL_VOLUME_PREFIX = 'ozon-backup-drill-regression'
    $env:COMPOSE_PROJECT_NAME = $env:DRILL_VOLUME_PREFIX
    $script:MockConfig = @{ volumes = @{} }
    foreach ($key in @('postgres_data', 'uploads', 'backups', 'caddy_data', 'caddy_config')) {
        $script:MockConfig.volumes[$key] = @{ name = "${env:DRILL_VOLUME_PREFIX}_$key" }
    }
    Assert-SafeDrillConfig
    foreach ($key in @('postgres_data', 'uploads', 'backups')) {
        $safeName = $script:MockConfig.volumes[$key].name
        $script:MockConfig.volumes[$key].name = "ozon-production_$key"
        $rejected = $false
        try { Assert-SafeDrillConfig } catch { $rejected = $true }
        if (-not $rejected) { throw "Production volume accepted: $key" }
        $script:MockConfig.volumes[$key].name = $safeName
    }
    $env:COMPOSE_PROJECT_NAME = 'ozon-production'
    $callsBefore = $script:CommandHistory.Count
    $rejected = $false
    try { Assert-SafeDrillConfig } catch { $rejected = $true }
    if (-not $rejected -or $script:CommandHistory.Count -ne $callsBefore) {
        throw 'Unsafe project was not rejected before external commands'
    }
} finally {
    $env:DRILL_VOLUME_PREFIX = $savedPrefix
    $env:COMPOSE_PROJECT_NAME = $savedProject
}
Write-Host "PASS: $composeCallCount Compose calls and $rootCallCount root Docker calls; both cleanup paths and production-volume guards verified without Docker."
