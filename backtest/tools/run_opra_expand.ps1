# Launcher for expand_opra_cache.py — full backtest window.
# Runs in background; writes log to backtest/tools/_state/opra_ingest.log
# Progress JSON: backtest/tools/_state/opra_ingest_progress.json
#
# Usage:
#   pwsh -File backtest/tools/run_opra_expand.ps1
#   pwsh -File backtest/tools/run_opra_expand.ps1 -Start 2025-06-01 -End 2025-12-31

param(
    [string]$Start = "2025-01-01",
    [string]$End = "2026-05-12",
    [double]$Sleep = 0.30,
    [int]$StrikesHalf = 5
)

$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$tool = Join-Path $repo "backtest\tools\expand_opra_cache.py"
$stateDir = Join-Path $repo "backtest\tools\_state"
$logFile = Join-Path $stateDir "opra_ingest.log"
$perContractLog = Join-Path $stateDir "opra_ingest_contracts.log"

New-Item -ItemType Directory -Path $stateDir -Force -Confirm:$false | Out-Null

Write-Output "Launching OPRA cache expansion..."
Write-Output "  start=$Start end=$End strikes_half=$StrikesHalf sleep=$Sleep"
Write-Output "  script=$tool"
Write-Output "  log=$logFile"

# Start the Python process detached, stdout+stderr to log
$arguments = @(
    $tool,
    "--start", $Start,
    "--end", $End,
    "--strikes-half", "$StrikesHalf",
    "--sleep", "$Sleep",
    "--log-file", $perContractLog,
    "--progress-every", "25"
)
$proc = Start-Process -FilePath "python" `
    -ArgumentList $arguments `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError ($logFile + ".err") `
    -NoNewWindow `
    -PassThru

Write-Output "Spawned PID: $($proc.Id)"
$proc.Id | Out-File -FilePath (Join-Path $stateDir "opra_ingest.pid") -Encoding utf8
Write-Output "PID written to $($stateDir)\opra_ingest.pid"
