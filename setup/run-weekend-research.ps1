# ============================================================================
# Project Gamma -- Weekend Research Driver
# ============================================================================
#
# Runs autoresearch sweeps continuously across multiple wave configs (mode,
# experiment, objective) until the time budget is exhausted. Designed to
# fire-and-forget Saturday morning and exit cleanly Sunday before the weekly
# review fires at 18:00 ET.
#
# Each wave is a (mode, experiment, objective, iterations) tuple. Waves run
# sequentially. If a wave fails, the script logs and continues to the next
# wave (don't lose Sunday because Saturday hit a transient bug).
#
# Progress is written to backtest/autoresearch/_state/weekend-progress.json
# every wave for the dashboard to read.
#
# Usage:
#   .\setup\run-weekend-research.ps1
#   .\setup\run-weekend-research.ps1 -StopAtUtc "2026-05-10T22:00:00Z"
#   .\setup\run-weekend-research.ps1 -DryRun     # show plan, don't run
#
# Designed to be called by a Windows scheduled task (Gamma_WeekendResearch)
# OR launched manually from a Claude session.
# ============================================================================

[CmdletBinding()]
param(
    # Stop time. Defaults to Sunday 17:30 ET (= 21:30 UTC during DST), giving
    # the weekly review at 18:00 ET a clean window with no sweep contention.
    [string]$StopAtUtc = "",

    # Skip execution, just print the plan and exit.
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'  # Python logs to stderr; don't treat as fatal
$Repo = Resolve-Path "$PSScriptRoot\.."
$Venv = "$Repo\backtest\.venv\Scripts\python.exe"
$LogDir = "$Repo\backtest\autoresearch\_state"
$LogFile = "$LogDir\weekend-research.log"
$ProgressFile = "$LogDir\weekend-progress.json"
$LockFile = "$LogDir\weekend-research.lock"

if (-not (Test-Path $LogDir)) { New-Item -Path $LogDir -ItemType Directory -Force | Out-Null }

# ----------------------------------------------------------------------------
# Lock guard -- prevent two weekend drivers from running simultaneously.
# ----------------------------------------------------------------------------
if (Test-Path $LockFile) {
    $existing = Get-Content $LockFile -Raw -ErrorAction SilentlyContinue
    try {
        $existingPid = [int]$existing.Trim()
        $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Output "weekend driver already running (pid $existingPid). Exiting."
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

try {

# ----------------------------------------------------------------------------
# Stop time computation
# ----------------------------------------------------------------------------
if ([string]::IsNullOrEmpty($StopAtUtc)) {
    # Compute Sunday 17:30 ET as a UTC instant.
    $now = Get-Date
    $daysUntilSunday = (7 - [int]$now.DayOfWeek) % 7
    if ($daysUntilSunday -eq 0 -and $now.Hour -ge 17) {
        $daysUntilSunday = 7  # already past Sunday 17:30 -- schedule next week
    }
    $sundayLocal = $now.Date.AddDays($daysUntilSunday).AddHours(17).AddMinutes(30)
    $stopAt = $sundayLocal.ToUniversalTime()
} else {
    $stopAt = [DateTime]::Parse($StopAtUtc).ToUniversalTime()
}
$timeBudget = $stopAt - (Get-Date).ToUniversalTime()

# ----------------------------------------------------------------------------
# Wave plan
# ----------------------------------------------------------------------------
# Order matters -- start with highest-leverage configs in case we run out of time.
# Each wave is roughly 30-90 minutes (depends on iterations + mode).
$waves = @(
    @{ Wave = "W1"; Modes = @("aggressive");                       Experiment = "full";         Objective = "validate_pnl";        Iterations = 40; Notes = "push the strongest baseline ($1,882 validate)" }
    @{ Wave = "W2"; Modes = @("balanced");                         Experiment = "full";         Objective = "validate_pnl";        Iterations = 40; Notes = "fix v14 underperformance on validate" }
    @{ Wave = "W3"; Modes = @("aggressive", "balanced");            Experiment = "exits";        Objective = "validate_sharpe";     Iterations = 25; Notes = "exits-only sweep -- memory note: 'exits in search space'" }
    @{ Wave = "W4"; Modes = @("strict", "balanced", "aggressive");  Experiment = "lean";         Objective = "train_sharpe";        Iterations = 25; Notes = "core-only cross-check (low overfit risk)" }
    @{ Wave = "W5"; Modes = @("aggressive");                        Experiment = "kitchen_sink"; Objective = "validate_pnl";        Iterations = 30; Notes = "kitchen-sink + VIX knobs on aggressive" }
    @{ Wave = "W6"; Modes = @("balanced");                          Experiment = "entries";      Objective = "validate_expectancy"; Iterations = 25; Notes = "entry filters tuned for expectancy" }
    @{ Wave = "W7"; Modes = @("strict");                            Experiment = "full";         Objective = "validate_pnl";        Iterations = 25; Notes = "strict mode push (low n baseline -- flag if no progress)" }
    @{ Wave = "W8"; Modes = @("aggressive", "balanced", "strict");  Experiment = "full";         Objective = "validate_sharpe";     Iterations = 20; Notes = "final cross-mode validate-sharpe pass" }
)

# ----------------------------------------------------------------------------
# Header + dry-run path
# ----------------------------------------------------------------------------
$startTime = Get-Date
"=== WEEKEND RESEARCH DRIVER ===" | Tee-Object -FilePath $LogFile
"Started:    $($startTime.ToString('u'))" | Tee-Object -FilePath $LogFile -Append
"Stop at:    $($stopAt.ToString('u'))" | Tee-Object -FilePath $LogFile -Append
"Budget:     $([math]::Round($timeBudget.TotalHours, 1)) hours" | Tee-Object -FilePath $LogFile -Append
"Wave plan ($($waves.Count) waves):" | Tee-Object -FilePath $LogFile -Append
foreach ($w in $waves) {
    $modeStr = $w.Modes -join ","
    "  $($w.Wave): $modeStr / $($w.Experiment) / $($w.Objective) / $($w.Iterations) iters | $($w.Notes)" | Tee-Object -FilePath $LogFile -Append
}
"" | Tee-Object -FilePath $LogFile -Append

if ($DryRun) {
    Write-Output "DRY RUN -- exiting without executing."
    exit 0
}

# ----------------------------------------------------------------------------
# Initial progress write
# ----------------------------------------------------------------------------
$progress = [ordered]@{
    started_at = $startTime.ToUniversalTime().ToString("o")
    stop_at    = $stopAt.ToString("o")
    pid        = $PID
    waves_total = $waves.Count
    waves_done  = 0
    current_wave = $null
    waves = @()
}
$progress | ConvertTo-Json -Depth 6 | Out-File -FilePath $ProgressFile -Encoding utf8

Set-Location "$Repo\backtest"

# ----------------------------------------------------------------------------
# Wave loop
# ----------------------------------------------------------------------------
$waveIdx = 0
foreach ($w in $waves) {
    $waveIdx++
    $now = (Get-Date).ToUniversalTime()
    if ($now -ge $stopAt) {
        "[$($w.Wave)] SKIPPED -- past stop time ($stopAt)" | Tee-Object -FilePath $LogFile -Append
        continue
    }

    $waveStart = Get-Date
    $modesArg = $w.Modes -join ' '
    "" | Tee-Object -FilePath $LogFile -Append
    "[$($w.Wave)] $($waveStart.ToString('HH:mm:ss')) START -- modes=[$modesArg] exp=$($w.Experiment) obj=$($w.Objective) iters=$($w.Iterations)" | Tee-Object -FilePath $LogFile -Append
    "[$($w.Wave)] $($w.Notes)" | Tee-Object -FilePath $LogFile -Append

    $progress.current_wave = [ordered]@{
        wave        = $w.Wave
        started_at  = $waveStart.ToUniversalTime().ToString("o")
        modes       = $w.Modes
        experiment  = $w.Experiment
        objective   = $w.Objective
        iterations  = $w.Iterations
        notes       = $w.Notes
    }
    $progress | ConvertTo-Json -Depth 6 | Out-File -FilePath $ProgressFile -Encoding utf8

    # Run the wave. NO --reset so we accumulate across waves with same mode.
    & $Venv -m autoresearch.loop `
        --modes @($w.Modes) `
        --experiment $w.Experiment `
        --objective $w.Objective `
        --iterations $w.Iterations `
        2>&1 | Tee-Object -FilePath $LogFile -Append

    $waveEnd = Get-Date
    $waveElapsed = $waveEnd - $waveStart
    "[$($w.Wave)] $($waveEnd.ToString('HH:mm:ss')) END -- elapsed $($waveElapsed.TotalMinutes.ToString('F1')) min" | Tee-Object -FilePath $LogFile -Append

    $progress.waves += [ordered]@{
        wave        = $w.Wave
        modes       = $w.Modes
        experiment  = $w.Experiment
        objective   = $w.Objective
        iterations  = $w.Iterations
        started_at  = $waveStart.ToUniversalTime().ToString("o")
        ended_at    = $waveEnd.ToUniversalTime().ToString("o")
        elapsed_min = [math]::Round($waveElapsed.TotalMinutes, 1)
    }
    $progress.waves_done = $waveIdx
    $progress.current_wave = $null
    $progress | ConvertTo-Json -Depth 6 | Out-File -FilePath $ProgressFile -Encoding utf8

    # Refresh watchdog report after each wave so dashboard reflects new KEEPs.
    & $Venv -m autoresearch.watchdog_report 2>&1 | Tee-Object -FilePath $LogFile -Append
}

# ----------------------------------------------------------------------------
# Wrap up
# ----------------------------------------------------------------------------
$endTime = Get-Date
$totalElapsed = $endTime - $startTime
"" | Tee-Object -FilePath $LogFile -Append
"=== DONE ===" | Tee-Object -FilePath $LogFile -Append
"Finished: $($endTime.ToString('u'))" | Tee-Object -FilePath $LogFile -Append
"Total elapsed: $($totalElapsed.TotalHours.ToString('F2')) hours" | Tee-Object -FilePath $LogFile -Append
"Waves completed: $($progress.waves_done) / $($progress.waves_total)" | Tee-Object -FilePath $LogFile -Append

$progress.finished_at = $endTime.ToUniversalTime().ToString("o")
$progress.total_elapsed_hours = [math]::Round($totalElapsed.TotalHours, 2)
$progress | ConvertTo-Json -Depth 6 | Out-File -FilePath $ProgressFile -Encoding utf8

}
finally {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
