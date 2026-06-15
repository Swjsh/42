# ============================================================================
# Project Gamma -- Next Steps Orchestrator (Steps 1, 2, 3)
# ============================================================================
#
# After random_eval surfaced regime-robust candidates (seeds 6 and 9), this
# script runs the validation + refinement pipeline.
#
# Step 1 (foreground, ~10 min):  Sub-window stability test for seeds 6 and 9.
# Step 2 (background, ~1-2 hr):  Hill-climb from seed 6 and seed 9 (parallel).
# Step 3 (background, ~45-90 min): Random batches D/E/F (seeds 30..59).
#
# Step 3 launches FIRST so it runs in parallel with Step 1.
# Step 2 launches AFTER Step 1 completes (so the stability verdict can guide
# whether seed 6 or seed 9 deserves the deeper hill-climb).
#
# Usage:
#   .\setup\run-next-steps.ps1                # default
#   .\setup\run-next-steps.ps1 -SkipStep3     # only Steps 1 + 2
# ============================================================================

[CmdletBinding()]
param(
    [switch]$SkipStep3,
    [switch]$SkipStep2,
    [int]$ClimbIterations = 25
)

$ErrorActionPreference = 'Stop'
$Repo = Resolve-Path "$PSScriptRoot\.."
$Venv = "$Repo\backtest\.venv\Scripts\python.exe"
$BacktestDir = "$Repo\backtest"

if (-not (Test-Path $Venv)) {
    Write-Error "Python venv not found at $Venv"
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host " GAMMA NEXT STEPS PIPELINE" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White
Write-Host "Step 1 (now, foreground):  Sub-window stability for seeds 6 + 9" -ForegroundColor Cyan
if (-not $SkipStep3) {
    Write-Host "Step 3 (now, background):  Random batches D/E/F seeds 30..59" -ForegroundColor Yellow
}
if (-not $SkipStep2) {
    Write-Host "Step 2 (after Step 1):     Hill-climb from seed 6 and seed 9" -ForegroundColor Green
}
Write-Host ""

# ----------------------------------------------------------------------------
# STEP 3 — launch random batches D/E/F (background, in parallel with Step 1)
# ----------------------------------------------------------------------------
if (-not $SkipStep3) {
    Write-Host "Launching Step 3: random batches D/E/F seeds 30..59" -ForegroundColor Yellow

    # Use the existing launcher with -StartSeed 30 + override the batch IDs by
    # invoking random_eval directly in 3 windows (need IDs D/E/F not A/B/C).
    $batches3 = @(
        @{ Id = "D"; SeedStart = 30; SeedEnd = 39; Color = "DarkCyan"   },
        @{ Id = "E"; SeedStart = 40; SeedEnd = 49; Color = "DarkYellow" },
        @{ Id = "F"; SeedStart = 50; SeedEnd = 59; Color = "DarkGreen"  }
    )

    foreach ($b in $batches3) {
        $title = "Gamma RandomSearch [Batch $($b.Id)  seeds $($b.SeedStart)..$($b.SeedEnd)]"
        $inner = @"
`$Host.UI.RawUI.WindowTitle = '$title'
Set-Location '$BacktestDir'
Write-Host '======================================================' -ForegroundColor $($b.Color)
Write-Host ' BATCH $($b.Id)  --  seeds $($b.SeedStart)..$($b.SeedEnd)' -ForegroundColor $($b.Color)
Write-Host '======================================================' -ForegroundColor $($b.Color)
& '$Venv' -m autoresearch.random_eval --batch-id $($b.Id) --seed-start $($b.SeedStart) --seed-end $($b.SeedEnd)
Write-Host ''
Write-Host '======================================================' -ForegroundColor $($b.Color)
Write-Host ' BATCH $($b.Id) DONE  --  window stays open' -ForegroundColor $($b.Color)
Write-Host '======================================================' -ForegroundColor $($b.Color)
"@
        $proc = Start-Process powershell -ArgumentList @(
            "-NoExit","-NoLogo","-NoProfile","-Command", $inner
        ) -PassThru
        Write-Host ("  Batch {0} (PID {1}): launched, seeds {2}..{3}" -f $b.Id, $proc.Id, $b.SeedStart, $b.SeedEnd) -ForegroundColor $b.Color
        Start-Sleep -Milliseconds 500
    }
    Write-Host ""
}

# ----------------------------------------------------------------------------
# STEP 1 — sub-window stability test (foreground, blocks until done)
# ----------------------------------------------------------------------------
Write-Host "Running Step 1: sub-window stability for seeds 6 and 9..." -ForegroundColor Cyan
Write-Host "(This blocks the script for ~10-15 min while Step 3 runs in parallel.)" -ForegroundColor Gray
Write-Host ""

Set-Location $BacktestDir
$step1Start = Get-Date
& $Venv -m autoresearch.sub_window_test --seeds 6 9
$step1End = Get-Date
$step1Min = [math]::Round(($step1End - $step1Start).TotalMinutes, 1)

Write-Host ""
Write-Host "Step 1 complete in $step1Min min." -ForegroundColor Cyan
Write-Host ""

# ----------------------------------------------------------------------------
# STEP 2 — hill-climb seed 6 and seed 9 (background, after Step 1)
# ----------------------------------------------------------------------------
if (-not $SkipStep2) {
    Write-Host "Launching Step 2: hill-climb from seed 6 and seed 9..." -ForegroundColor Green

    $climbs = @(
        @{ Seed = 6; Color = "Magenta" },
        @{ Seed = 9; Color = "Blue"    }
    )

    foreach ($c in $climbs) {
        $title = "Gamma SeedClimb [seed $($c.Seed)  $ClimbIterations iters]"
        $inner = @"
`$Host.UI.RawUI.WindowTitle = '$title'
Set-Location '$BacktestDir'
Write-Host '======================================================' -ForegroundColor $($c.Color)
Write-Host ' HILL-CLIMB FROM SEED $($c.Seed)  --  $ClimbIterations iters' -ForegroundColor $($c.Color)
Write-Host '======================================================' -ForegroundColor $($c.Color)
& '$Venv' -m autoresearch.seed_climb --seed $($c.Seed) --iterations $ClimbIterations --objective validate_pnl --reset
Write-Host ''
Write-Host '======================================================' -ForegroundColor $($c.Color)
Write-Host ' SEED $($c.Seed) HILL-CLIMB DONE' -ForegroundColor $($c.Color)
Write-Host '======================================================' -ForegroundColor $($c.Color)
"@
        $proc = Start-Process powershell -ArgumentList @(
            "-NoExit","-NoLogo","-NoProfile","-Command", $inner
        ) -PassThru
        Write-Host ("  Seed {0} climb (PID {1}): launched" -f $c.Seed, $proc.Id) -ForegroundColor $c.Color
        Start-Sleep -Milliseconds 500
    }
    Write-Host ""
}

Write-Host "============================================================" -ForegroundColor White
Write-Host " ORCHESTRATION COMPLETE" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White
Write-Host "Step 1: DONE (results above + saved to _state/random_search/sub_window_*.json)"
Write-Host "Step 2: launched in 2 windows (seed 6, seed 9 hill-climb -- ~1-2 hr each)" -ForegroundColor Green
if (-not $SkipStep3) {
    Write-Host "Step 3: running in 3 windows (batches D/E/F -- ~45-90 min)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "When everything is done, run synthesis with:"
Write-Host "  & '$Venv' -m autoresearch.aggregate_random  # all 6 random batches" -ForegroundColor Gray
Write-Host "  & '$Venv' -m autoresearch.loop --status --mode seed6_climb" -ForegroundColor Gray
Write-Host "  & '$Venv' -m autoresearch.loop --status --mode seed9_climb" -ForegroundColor Gray
