# ============================================================================
# Project Gamma -- Multi-Seed Random Parameter Search Launcher
# ============================================================================
#
# Spawns three PowerShell windows in parallel, each running a disjoint batch
# of random parameter seeds against TRAIN + VALIDATE windows.
#
# Batch A: seeds  0..9   -> _state/random_search/batch_A.jsonl
# Batch B: seeds 10..19  -> _state/random_search/batch_B.jsonl
# Batch C: seeds 20..29  -> _state/random_search/batch_C.jsonl
#
# Each window stays open after its batch finishes so you can see results.
# Aggregate results across all batches with:
#     .\backtest\.venv\Scripts\python.exe -m autoresearch.aggregate_random
#
# Usage:
#   .\setup\run-random-search.ps1                  # default 30 seeds (3 x 10)
#   .\setup\run-random-search.ps1 -SeedsPerBatch 20  # 60 seeds total (3 x 20)
#   .\setup\run-random-search.ps1 -DryRun          # show plan only, don't launch
# ============================================================================

[CmdletBinding()]
param(
    [int]$SeedsPerBatch = 10,
    [int]$StartSeed = 0,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$Repo = Resolve-Path "$PSScriptRoot\.."
$Venv = "$Repo\backtest\.venv\Scripts\python.exe"
$BacktestDir = "$Repo\backtest"
$StateDir = "$BacktestDir\autoresearch\_state\random_search"

if (-not (Test-Path $Venv)) {
    Write-Error "Python venv not found at $Venv"
    exit 1
}

if (-not (Test-Path $StateDir)) {
    New-Item -Path $StateDir -ItemType Directory -Force | Out-Null
}

# ----------------------------------------------------------------------------
# Build batch plan
# ----------------------------------------------------------------------------
$batches = @(
    @{ Id = "A"; Color = "Cyan"   },
    @{ Id = "B"; Color = "Yellow" },
    @{ Id = "C"; Color = "Green"  }
)

$plan = @()
$cursor = $StartSeed
foreach ($b in $batches) {
    $plan += [PSCustomObject]@{
        BatchId   = $b.Id
        Color     = $b.Color
        SeedStart = $cursor
        SeedEnd   = $cursor + $SeedsPerBatch - 1
    }
    $cursor += $SeedsPerBatch
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host " GAMMA RANDOM PARAMETER SEARCH -- 3-batch parallel launch"   -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White
foreach ($p in $plan) {
    Write-Host ("  Batch {0}:  seeds {1}..{2}  ({3} seeds)" -f $p.BatchId, $p.SeedStart, $p.SeedEnd, $SeedsPerBatch) -ForegroundColor $p.Color
}
Write-Host ""
Write-Host "Total seeds:    $($SeedsPerBatch * 3)"
Write-Host "Train window:   2025-01-01 .. 2026-02-13"
Write-Host "Validate window:2026-02-14 .. 2026-05-07"
Write-Host "Output dir:     $StateDir"
Write-Host ""

if ($DryRun) {
    Write-Host "DryRun -- no windows launched." -ForegroundColor Magenta
    exit 0
}

# ----------------------------------------------------------------------------
# Spawn one PowerShell window per batch
# ----------------------------------------------------------------------------
$processes = @()
foreach ($p in $plan) {
    $batchId   = $p.BatchId
    $seedStart = $p.SeedStart
    $seedEnd   = $p.SeedEnd
    $color     = $p.Color

    # Title for the spawned window so you can identify it on the taskbar.
    $title = "Gamma RandomSearch [Batch $batchId  seeds $seedStart..$seedEnd]"

    # Inner command run in the spawned window:
    #   1. cd to backtest dir (so `python -m autoresearch.random_eval` finds the package)
    #   2. set the host title
    #   3. set the foreground color
    #   4. invoke the venv python with the random_eval module
    #   5. on completion, print "[BATCH X DONE]" and stay open (-NoExit)
    $inner = @"
`$Host.UI.RawUI.WindowTitle = '$title'
Set-Location '$BacktestDir'
Write-Host '======================================================' -ForegroundColor $color
Write-Host ' BATCH $batchId  --  seeds $seedStart..$seedEnd' -ForegroundColor $color
Write-Host '======================================================' -ForegroundColor $color
& '$Venv' -m autoresearch.random_eval --batch-id $batchId --seed-start $seedStart --seed-end $seedEnd
Write-Host ''
Write-Host '======================================================' -ForegroundColor $color
Write-Host ' BATCH $batchId DONE  --  window stays open' -ForegroundColor $color
Write-Host '======================================================' -ForegroundColor $color
"@

    Write-Host "Launching batch $batchId..." -ForegroundColor $color
    $proc = Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-NoLogo",
        "-NoProfile",
        "-Command", $inner
    ) -PassThru
    $processes += [PSCustomObject]@{
        BatchId = $batchId
        PID     = $proc.Id
        Color   = $color
    }
    Start-Sleep -Milliseconds 500
}

# ----------------------------------------------------------------------------
# Verify all three windows are alive after a short delay
# ----------------------------------------------------------------------------
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host " LAUNCH STATUS"                                                -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White
$allOk = $true
foreach ($p in $processes) {
    $alive = Get-Process -Id $p.PID -ErrorAction SilentlyContinue
    if ($alive) {
        Write-Host ("  Batch {0}  PID {1,-6}  ALIVE" -f $p.BatchId, $p.PID) -ForegroundColor $p.Color
    } else {
        Write-Host ("  Batch {0}  PID {1,-6}  DEAD" -f $p.BatchId, $p.PID) -ForegroundColor Red
        $allOk = $false
    }
}
Write-Host ""

if ($allOk) {
    Write-Host "All three batches running. You should see three new PowerShell windows." -ForegroundColor Green
    Write-Host ""
    Write-Host "While they run, you can aggregate partial results anytime with:" -ForegroundColor Gray
    Write-Host "  & '$Venv' -m autoresearch.aggregate_random" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Live progress files:" -ForegroundColor Gray
    Write-Host "  $StateDir\batch_A_progress.json" -ForegroundColor Gray
    Write-Host "  $StateDir\batch_B_progress.json" -ForegroundColor Gray
    Write-Host "  $StateDir\batch_C_progress.json" -ForegroundColor Gray
} else {
    Write-Host "One or more batches failed to launch. Check the spawned windows for errors." -ForegroundColor Red
    exit 1
}
