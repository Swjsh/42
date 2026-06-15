# Autoresearch modes sweep — runs STRICT/BALANCED/AGGRESSIVE in sequence.
#
# Usage (default = 30 iterations per mode, ~5 hours, RESETS prior state):
#   .\setup\run-modes-sweep.ps1
#
# Quick first pass (10 iters per mode = ~1.5 hours, RESETS prior state):
#   .\setup\run-modes-sweep.ps1 -Iterations 10
#
# Resume an existing run without resetting (continues from current state):
#   .\setup\run-modes-sweep.ps1 -Iterations 10 -NoReset
#
# Output:
#   - Live log:   backtest/autoresearch/_state/sweep.log
#   - Per-mode:   backtest/autoresearch/_state/{strict,balanced,aggressive}/state.json
#   - Per-mode:   backtest/autoresearch/_state/{strict,balanced,aggressive}/history.jsonl
#   - Summary:    analysis/autoresearch_results.md (after the sweep completes)

param(
    [int]$Iterations = 30,
    [switch]$NoReset,
    [string]$TrainStart = "2025-01-01",
    [string]$TrainEnd = "2026-02-13",
    [string]$ValidateStart = "2026-02-14",
    [string]$ValidateEnd = "2026-05-07"
)

# Python's logging module writes to stderr by default; PowerShell with
# ErrorActionPreference=Stop treats those as fatal errors. Use Continue.
$ErrorActionPreference = 'Continue'
$Repo = Resolve-Path "$PSScriptRoot\.."
$Venv = "$Repo\backtest\.venv\Scripts\python.exe"
$LogDir = "$Repo\backtest\autoresearch\_state"
$LogFile = "$LogDir\sweep.log"
$SummaryDir = "$Repo\analysis"
$SummaryFile = "$SummaryDir\autoresearch_results.md"

if (-not (Test-Path $LogDir)) { New-Item -Path $LogDir -ItemType Directory | Out-Null }
if (-not (Test-Path $SummaryDir)) { New-Item -Path $SummaryDir -ItemType Directory | Out-Null }

Set-Location "$Repo\backtest"

$ResetArgs = @()
if (-not $NoReset) { $ResetArgs += '--reset' }
$startTime = Get-Date
$estMin = [math]::Round($Iterations * 3 * 3.5, 0)

"=== AUTORESEARCH MODES SWEEP ===" | Tee-Object -FilePath $LogFile
"Started: $startTime" | Tee-Object -FilePath $LogFile -Append
"Iterations per mode: $Iterations (3 modes total)" | Tee-Object -FilePath $LogFile -Append
"Train window: $TrainStart -> $TrainEnd" | Tee-Object -FilePath $LogFile -Append
"Validate window: $ValidateStart -> $ValidateEnd" | Tee-Object -FilePath $LogFile -Append
"Reset state at start: $(-not $NoReset)" | Tee-Object -FilePath $LogFile -Append
"Estimated runtime: $estMin min ($([math]::Round($estMin / 60.0, 1)) hours)" | Tee-Object -FilePath $LogFile -Append
"" | Tee-Object -FilePath $LogFile -Append

& $Venv -m autoresearch.loop `
    --modes strict balanced aggressive `
    --iterations $Iterations `
    --train-start $TrainStart --train-end $TrainEnd `
    --validate-start $ValidateStart --validate-end $ValidateEnd `
    @ResetArgs 2>&1 | Tee-Object -FilePath $LogFile -Append

$endTime = Get-Date
$elapsed = $endTime - $startTime
"" | Tee-Object -FilePath $LogFile -Append
"Finished: $endTime (elapsed $($elapsed.TotalMinutes.ToString('F1')) min)" | Tee-Object -FilePath $LogFile -Append

"" | Tee-Object -FilePath $LogFile -Append
"Generating summary..." | Tee-Object -FilePath $LogFile -Append
& $Venv -m autoresearch.summarize --out $SummaryFile 2>&1 | Tee-Object -FilePath $LogFile -Append

Write-Host ""
Write-Host "DONE." -ForegroundColor Green
Write-Host "Log:     $LogFile"
Write-Host "Summary: $SummaryFile"
