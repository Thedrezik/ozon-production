param([ValidateRange(100, 100000)][int]$Orders = 10000, [switch]$WithoutAllocationTracing)
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $repoPath 'backend')
$previousSize = $env:PERFORMANCE_SIZE
$previousTrace = $env:PERFORMANCE_TRACE
try {
    $env:PERFORMANCE_SIZE = "$Orders"
    $env:PERFORMANCE_TRACE = if ($WithoutAllocationTracing) { '0' } else { '1' }
    & .venv/Scripts/python.exe -m pytest tests/test_performance.py::test_synthetic_key_pages -s -q
    if ($LASTEXITCODE -ne 0) { throw 'Performance regression check failed' }
} finally {
    $env:PERFORMANCE_SIZE = $previousSize
    $env:PERFORMANCE_TRACE = $previousTrace
    Pop-Location
}
