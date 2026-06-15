# ============================================================================
# Project Gamma -- PARALLEL Weekend Research Driver (Multi-Agent Gamma 2.0)
# ============================================================================
#
# Supersedes run-weekend-research.ps1 with a 4-phase parallel pipeline:
#
#   PHASE 0  Random sampling      (parallel_eval, 4 workers, broad coverage)
#   PHASE 1  Aggregate + rank     (single-shot Python)
#   PHASE 2  Hill-climb top seeds (multiple climbs in parallel via Start-Job)
#   PHASE 3  Sub-window stability (parallel via Start-Job over top seeds)
#   PHASE 4  Synthesize v15       (single-shot Python -> analysis/recommendations/v15.json)
#
# Why this is faster than the sequential driver:
#   - PHASE 0: 4-worker pool replaces 1-thread serial per batch (~4x)
#   - PHASE 2: parallel hill-climb across N seeds replaces sequential climbs (~Nx)
#   - PHASE 3: parallel sub-window tests across N seeds replace serial (~Nx)
#
# Why this is SAFE on Windows:
#   - All Python work uses multiprocessing.Pool (process-based)
#   - lib.filters constant-mutation (runner._patched_filter_constants) is per-process
#   - Hard cap MAX_PARALLEL_WORKERS=4 (CLAUDE.md operating principle 15)
#   - Existing run-weekend-research.ps1 stays as fallback
#
# Usage:
#   .\setup\run-weekend-research-parallel.ps1
#   .\setup\run-weekend-research-parallel.ps1 -StopAtUtc "2026-05-10T22:00:00Z"
#   .\setup\run-weekend-research-parallel.ps1 -DryRun
#   .\setup\run-weekend-research-parallel.ps1 -RandomSeeds 100 -ClimbTopN 5
#
# Doctrine: docs/plans/multi-agent-gamma.md, Big Win #1
# ============================================================================

[CmdletBinding()]
param(
    [string]$StopAtUtc = "",
    [switch]$DryRun,

    # PHASE 0 sizing.
    [int]$RandomSeeds = 60,           # 60 seeds across batch_P0 with 4 workers ~= 45 min
    [int]$RandomSeedStart = 200,      # 200+ to avoid colliding with existing batch_A/B/C (0-29)

    # PHASE 2 sizing.
    [int]$ClimbTopN = 4,              # parallel climbs (= worker pool size)
    [int]$ClimbIterations = 25,       # iterations per climb

    # PHASE 3 sizing.
    [int]$SubWindowTopN = 8,          # how many seeds to stability-test

    # Concurrency cap (matches MAX_PARALLEL_WORKERS in parallel_eval.py).
    [int]$MaxWorkers = 4
)

$ErrorActionPreference = 'Continue'
$Repo = Resolve-Path "$PSScriptRoot\.."
$Venv = "$Repo\backtest\.venv\Scripts\python.exe"
$LogDir = "$Repo\backtest\autoresearch\_state"
$LogFile = "$LogDir\weekend-research-parallel.log"
$ProgressFile = "$LogDir\weekend-progress.json"
$LockFile = "$LogDir\weekend-research-parallel.lock"

if (-not (Test-Path $LogDir)) { New-Item -Path $LogDir -ItemType Directory -Force | Out-Null }
if (-not (Test-Path $Venv)) {
    Write-Error "venv python missing at $Venv -- run setup/install.ps1 first"
    exit 1
}

# ----------------------------------------------------------------------------
# Lock guard -- prevent two parallel drivers from running simultaneously.
# ----------------------------------------------------------------------------
if (Test-Path $LockFile) {
    $existing = Get-Content $LockFile -Raw -ErrorAction SilentlyContinue
    try {
        $existingPid = [int]$existing.Trim()
        $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Output "parallel weekend driver already running (pid $existingPid). Exiting."
            exit 0
        } else {
            Write-Output "stale lock (pid $existingPid not alive); reclaiming"
            Remove-Item $LockFile -Force
        }
    } catch {
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    }
}
$PID | Out-File -FilePath $LockFile -Encoding utf8 -NoNewline

function Write-Phase {
    param([string]$Msg)
    $ts = (Get-Date).ToString('HH:mm:ss')
    "[$ts] $Msg" | Tee-Object -FilePath $LogFile -Append
}

function Update-Progress {
    param([hashtable]$Patch)
    $existing = if (Test-Path $ProgressFile) {
        try { Get-Content $ProgressFile -Raw | ConvertFrom-Json -AsHashtable } catch { @{} }
    } else { @{} }
    foreach ($k in $Patch.Keys) { $existing[$k] = $Patch[$k] }
    $existing | ConvertTo-Json -Depth 8 | Out-File -FilePath $ProgressFile -Encoding utf8
}

try {

# ----------------------------------------------------------------------------
# Stop time
# ----------------------------------------------------------------------------
if ([string]::IsNullOrEmpty($StopAtUtc)) {
    $now = Get-Date
    $daysUntilSunday = (7 - [int]$now.DayOfWeek) % 7
    if ($daysUntilSunday -eq 0 -and $now.Hour -ge 17) { $daysUntilSunday = 7 }
    $sundayLocal = $now.Date.AddDays($daysUntilSunday).AddHours(17).AddMinutes(30)
    $stopAt = $sundayLocal.ToUniversalTime()
} else {
    $stopAt = [DateTime]::Parse($StopAtUtc).ToUniversalTime()
}
$timeBudget = $stopAt - (Get-Date).ToUniversalTime()

$startTime = Get-Date
"=== PARALLEL WEEKEND RESEARCH DRIVER (Multi-Agent Gamma 2.0) ===" | Tee-Object -FilePath $LogFile
Write-Phase "Started:  $($startTime.ToString('u'))"
Write-Phase "Stop at:  $($stopAt.ToString('u'))"
Write-Phase "Budget:   $([math]::Round($timeBudget.TotalHours, 1)) hours"
Write-Phase "Random:   $RandomSeeds seeds (start at $RandomSeedStart) across $MaxWorkers workers"
Write-Phase "Climb:    top-$ClimbTopN seeds, $ClimbIterations iters each (parallel)"
Write-Phase "Sub-win:  top-$SubWindowTopN seeds (parallel)"

if ($DryRun) {
    Write-Phase "DRY RUN -- exiting without executing"
    exit 0
}

Update-Progress @{
    started_at  = $startTime.ToUniversalTime().ToString("o")
    stop_at     = $stopAt.ToString("o")
    pid         = $PID
    driver      = "parallel"
    phase       = "starting"
    random_seeds = $RandomSeeds
    climb_top_n  = $ClimbTopN
    sub_window_top_n = $SubWindowTopN
    max_workers  = $MaxWorkers
}

Set-Location "$Repo\backtest"

# ============================================================================
# PHASE 0 -- PARALLEL RANDOM SEARCH
# ============================================================================
Write-Phase ""
Write-Phase "=== PHASE 0: PARALLEL RANDOM SEARCH ==="
Update-Progress @{ phase = "P0_random_search"; phase_started_at = (Get-Date).ToUniversalTime().ToString("o") }

$seedEnd = $RandomSeedStart + $RandomSeeds - 1
$p0Start = Get-Date
Write-Phase "Launching parallel_eval batch P0 seeds=$RandomSeedStart..$seedEnd workers=$MaxWorkers"

& $Venv -m autoresearch.parallel_eval `
    --batch-id "P0" `
    --seed-start $RandomSeedStart `
    --seed-end $seedEnd `
    --workers $MaxWorkers `
    2>&1 | Tee-Object -FilePath $LogFile -Append

$p0Elapsed = (Get-Date) - $p0Start
Write-Phase "PHASE 0 done in $([math]::Round($p0Elapsed.TotalMinutes, 1)) min"
Update-Progress @{ phase_p0_elapsed_min = [math]::Round($p0Elapsed.TotalMinutes, 1) }

if ((Get-Date).ToUniversalTime() -ge $stopAt) {
    Write-Phase "OUT OF TIME after PHASE 0 -- aggregating + exiting"
    & $Venv -m autoresearch.aggregate_random 2>&1 | Tee-Object -FilePath $LogFile -Append
    exit 0
}

# ============================================================================
# PHASE 1 -- AGGREGATE + RANK
# ============================================================================
Write-Phase ""
Write-Phase "=== PHASE 1: AGGREGATE + RANK ==="
Update-Progress @{ phase = "P1_aggregate" }
$p1Start = Get-Date

& $Venv -m autoresearch.aggregate_random --top 20 2>&1 | Tee-Object -FilePath $LogFile -Append

# Read top-N seeds for hill-climb. aggregate_random writes random_search_summary.json.
$summaryPath = "$Repo\backtest\autoresearch\_state\random_search\random_search_summary.json"
if (-not (Test-Path $summaryPath)) {
    Write-Phase "ERROR: summary not written -- aborting"
    exit 1
}
$summary = Get-Content $summaryPath -Raw | ConvertFrom-Json
$topRecords = $summary.top_candidates
if ($null -eq $topRecords -or $topRecords.Count -eq 0) {
    Write-Phase "ERROR: random_search_summary.json has no top_candidates -- aborting"
    exit 1
}
$topSeeds = @()
foreach ($rec in $topRecords | Select-Object -First $ClimbTopN) {
    $topSeeds += $rec.seed
}
$subWindowSeeds = @()
foreach ($rec in $topRecords | Select-Object -First $SubWindowTopN) {
    $subWindowSeeds += $rec.seed
}
$p1Elapsed = (Get-Date) - $p1Start
Write-Phase "PHASE 1 done in $([math]::Round($p1Elapsed.TotalSeconds, 1)) sec -- climb seeds: $($topSeeds -join ',') ; sub-window seeds: $($subWindowSeeds -join ',')"
Update-Progress @{
    phase_p1_elapsed_sec = [math]::Round($p1Elapsed.TotalSeconds, 1)
    climb_seeds = $topSeeds
    sub_window_seeds = $subWindowSeeds
}

if ((Get-Date).ToUniversalTime() -ge $stopAt) {
    Write-Phase "OUT OF TIME after PHASE 1 -- skipping climb + sub-window"
    & $Venv -m autoresearch.synthesize_v15 2>&1 | Tee-Object -FilePath $LogFile -Append
    exit 0
}

# ============================================================================
# PHASE 2 -- PARALLEL HILL-CLIMB
# ============================================================================
Write-Phase ""
Write-Phase "=== PHASE 2: PARALLEL HILL-CLIMB ($($topSeeds.Count) seeds) ==="
Update-Progress @{ phase = "P2_hill_climb" }
$p2Start = Get-Date

# Spin up one background job per seed; cap at MaxWorkers concurrent.
$jobs = @()
foreach ($seed in $topSeeds) {
    while (($jobs | Where-Object { $_.State -eq 'Running' }).Count -ge $MaxWorkers) {
        Start-Sleep -Seconds 5
    }
    $job = Start-Job -ScriptBlock {
        param($Repo, $Venv, $Seed, $Iters)
        Set-Location "$Repo\backtest"
        & $Venv -m autoresearch.seed_climb --seed $Seed --iterations $Iters 2>&1
    } -ArgumentList $Repo, $Venv, $seed, $ClimbIterations
    $jobs += $job
    Write-Phase "  launched climb job for seed $seed (job id $($job.Id))"
}

# Wait for all climbs to finish; stream output to log as each job completes.
foreach ($job in $jobs) {
    Wait-Job -Job $job | Out-Null
    $output = Receive-Job -Job $job
    Write-Phase "  --- seed climb output (job $($job.Id)) ---"
    $output | Out-File -FilePath $LogFile -Append -Encoding utf8
    Remove-Job -Job $job
}

$p2Elapsed = (Get-Date) - $p2Start
Write-Phase "PHASE 2 done in $([math]::Round($p2Elapsed.TotalMinutes, 1)) min"
Update-Progress @{ phase_p2_elapsed_min = [math]::Round($p2Elapsed.TotalMinutes, 1) }

if ((Get-Date).ToUniversalTime() -ge $stopAt) {
    Write-Phase "OUT OF TIME after PHASE 2 -- skipping sub-window"
    & $Venv -m autoresearch.synthesize_v15 2>&1 | Tee-Object -FilePath $LogFile -Append
    exit 0
}

# ============================================================================
# PHASE 3 -- PARALLEL SUB-WINDOW STABILITY
# ============================================================================
Write-Phase ""
Write-Phase "=== PHASE 3: PARALLEL SUB-WINDOW STABILITY ($($subWindowSeeds.Count) seeds) ==="
Update-Progress @{ phase = "P3_sub_window" }
$p3Start = Get-Date

$jobs = @()
foreach ($seed in $subWindowSeeds) {
    while (($jobs | Where-Object { $_.State -eq 'Running' }).Count -ge $MaxWorkers) {
        Start-Sleep -Seconds 5
    }
    $job = Start-Job -ScriptBlock {
        param($Repo, $Venv, $Seed)
        Set-Location "$Repo\backtest"
        & $Venv -m autoresearch.sub_window_test --seed $Seed 2>&1
    } -ArgumentList $Repo, $Venv, $seed
    $jobs += $job
    Write-Phase "  launched sub-window job for seed $seed (job id $($job.Id))"
}

foreach ($job in $jobs) {
    Wait-Job -Job $job | Out-Null
    $output = Receive-Job -Job $job
    Write-Phase "  --- sub-window output (job $($job.Id)) ---"
    $output | Out-File -FilePath $LogFile -Append -Encoding utf8
    Remove-Job -Job $job
}

$p3Elapsed = (Get-Date) - $p3Start
Write-Phase "PHASE 3 done in $([math]::Round($p3Elapsed.TotalMinutes, 1)) min"
Update-Progress @{ phase_p3_elapsed_min = [math]::Round($p3Elapsed.TotalMinutes, 1) }

# ============================================================================
# PHASE 4 -- SYNTHESIZE v15 SCORECARD
# ============================================================================
Write-Phase ""
Write-Phase "=== PHASE 4: SYNTHESIZE v15 ==="
Update-Progress @{ phase = "P4_synthesize" }
$p4Start = Get-Date

& $Venv -m autoresearch.synthesize_v15 2>&1 | Tee-Object -FilePath $LogFile -Append

$p4Elapsed = (Get-Date) - $p4Start
Write-Phase "PHASE 4 done in $([math]::Round($p4Elapsed.TotalSeconds, 1)) sec"

# ----------------------------------------------------------------------------
# Wrap-up
# ----------------------------------------------------------------------------
$endTime = Get-Date
$totalElapsed = $endTime - $startTime
Write-Phase ""
Write-Phase "=== DONE ==="
Write-Phase "Total elapsed: $($totalElapsed.TotalHours.ToString('F2')) hours"
Update-Progress @{
    phase = "completed"
    finished_at = $endTime.ToUniversalTime().ToString("o")
    total_elapsed_hours = [math]::Round($totalElapsed.TotalHours, 2)
}

}
finally {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
