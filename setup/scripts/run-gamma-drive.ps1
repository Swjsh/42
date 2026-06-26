#requires -Version 5.1
<#
.SYNOPSIS
  Gamma_Drive nightly bounded driver loop -- the "Gamma drives like J" engine.

.DESCRIPTION
  Fires once daily (after-hours). Runs a BOUNDED loop: up to MAX_INITIATIVES
  fresh `claude --print` fires, each doing ONE gamma-drive initiative
  (run-gamma-drive.ps1 -> automation/prompts/gamma-drive.md, opus, --agent gamma).
  The wrapper -- NOT the model -- owns every hard cap, because a looping model
  cannot enforce its own iteration count, wall clock, or budget (prose caps are
  advisory; THESE are real).

  ANTI-RUN-INFINITELY (the hard stops, all enforced here):
    * MAX_INITIATIVES fires per run.
    * CONVERGENCE: stop after N consecutive NO-OP fires (a fire that drained 0 /
      added 0 / shipped 0 lessons / 0 tests, OR recorded nothing at all). A dry
      vein stops the loop instead of BRAINSTORMing tokens forever.
    * WALL-CLOCK DEADLINE: never launch a new fire at/after 08:15 ET (clean start
      for the 08:30 premarket task).
    * STOP-FLAG off-switch: J drops automation/state/gamma-drive-stop.flag to halt.
    * SINGLE-INSTANCE LOCK: gamma-drive.lock prevents two loops racing the queue.

  ANTI-EAT-TOKENS:
    * Per-fire --max-budget-usd cap; total ceiling = MAX_INITIATIVES x per-fire cap.
    * RAIL 1 after-hours gate (re-checked EVERY iteration) -- never fans out during
      RTH on the shared Max pool (L54: a market-hours fan-out starves the heartbeat).

  ANTI-MEMORY-LEAK:
    * FRESH context per fire (each `claude --print` is a new process) -- the loop
      lives in this wrapper, NOT an in-session /loop, so context never accumulates
      (the 97%-bloat foot-gun is eliminated by construction).
    * Retention: status_retention.py (STATUS.md) + loop_retention.py
      (conductor-outcomes.jsonl) run idempotently before the loop.

  ANTI-RUNAWAY backstop also at the OS level: the task's ExecutionTimeLimit and
  each fire's -TimeoutSec.

  FAIL-OPEN (rail 2 / OP-32 scar): never kills/blocks any process; only spawns its
  own claude --print and exits. The lock is released in a finally block.

  Invoked via the OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-gamma-drive.ps1 -> claude --print
#>

$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

. "$PSScriptRoot\_shared.ps1"

$task = "gamma-drive"
$stateDir   = Join-Path $projectRoot "automation\state"
$lockFile   = Join-Path $stateDir "gamma-drive.lock"
$stopFlag   = Join-Path $stateDir "gamma-drive-stop.flag"
$promptFile = Join-Path $projectRoot "automation\prompts\gamma-drive.md"
$outcomes   = Join-Path $stateDir "conductor-outcomes.jsonl"

# --- HARD CAPS (the real anti-runaway / anti-token guards; tune deliberately) ---
$MAX_INITIATIVES  = 3        # fires per run; ceiling cost = MAX x PER_FIRE_BUDGET
$PER_FIRE_BUDGET  = 8.00     # USD per fire (conductor learned 1.50 aborts w/ zero work)
$CONVERGENCE_STOP = 2        # consecutive NO-OP fires -> dry vein -> stop
$DEADLINE_HOUR_ET = 8        # do not launch a new fire at/after 08:15 ET ...
$DEADLINE_MIN_ET  = 15       # ... (premarket guard; the 09:30 RTH gate is separate)
$FIRE_TIMEOUT_SEC = 600      # per-fire wall clock
$LOCK_STALE_HOURS = 4        # an older lock is treated as a dead instance

# ---------------------------------------------------------------------------
# Helpers: detect whether a fire actually accomplished anything recordable.
# Convergence reads the freshest conductor-outcomes.jsonl row the fire wrote.
# A fire that wrote NO new row, or a row with zero drained+added+lessons+tests,
# is a NO-OP. Unparseable -> treat as NO-OP (conservative: stop sooner).
# ---------------------------------------------------------------------------
function Get-LastOutcomeLine {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return "" }
    try {
        $lines = Get-Content -Path $Path -ErrorAction Stop | Where-Object { $_.Trim() -ne "" }
        if (-not $lines -or $lines.Count -eq 0) { return "" }
        return [string]$lines[-1]
    } catch { return "" }
}

function Test-OutcomeNoop {
    param([string]$Before, [string]$After)
    if ([string]::IsNullOrWhiteSpace($After)) { return $true }   # nothing recorded
    if ($After -eq $Before) { return $true }                     # no NEW row this fire
    try {
        $o = $After | ConvertFrom-Json
        $sum = [int]($o.items_drained) + [int]($o.items_added) `
             + [int]($o.lessons_shipped) + [math]::Abs([int]($o.tests_delta))
        if ($sum -le 0) { return $true }
        return $false
    } catch { return $true }
}

function Test-PastDeadline {
    # The deadline is the EARLY-MORNING premarket guard ONLY: do not launch a new
    # fire in [08:15, 09:30) ET (the 09:30+ RTH gate is handled separately). It must
    # NOT trip in the evening after-hours window -- a 20:00 ET fire has Hour 20 > 8
    # but is nowhere near the morning deadline.
    param([DateTime]$Et)
    $afterDeadline = ($Et.Hour -gt $DEADLINE_HOUR_ET) -or `
                     ($Et.Hour -eq $DEADLINE_HOUR_ET -and $Et.Minute -ge $DEADLINE_MIN_ET)
    $beforeOpen = ($Et.Hour -lt 9) -or ($Et.Hour -eq 9 -and $Et.Minute -lt 30)
    return ($afterDeadline -and $beforeOpen)
}

# --- RAIL 1: after-hours gate (defense in depth; the prompt re-checks too) ------
$et = Get-EtNow
if ((Test-WeekDay -Et $et) -and (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 15 -EndMin 55)) {
    Write-TaskLog -TaskName $task -Message ("gamma-drive: SKIP -- market open (" + $et.ToString("HH:mm") + " ET), deferring to heartbeat (rail 1 / L54)")
    exit 0
}

# --- STOP-FLAG off-switch (J drops the file to halt; consume + exit) -------------
if (Test-Path $stopFlag) {
    Write-TaskLog -TaskName $task -Message ("gamma-drive: SKIP -- stop-flag present; consuming " + $stopFlag + " and exiting")
    Remove-Item $stopFlag -Force -ErrorAction SilentlyContinue
    exit 0
}

# --- SINGLE-INSTANCE LOCK (a fresh lock = a live peer; stale = dead, overwrite) --
if (Test-Path $lockFile) {
    $lockAge = (Get-Date) - (Get-Item $lockFile).LastWriteTime
    if ($lockAge.TotalHours -lt $LOCK_STALE_HOURS) {
        Write-TaskLog -TaskName $task -Message ("gamma-drive: SKIP -- another instance holds the lock (age " + [math]::Round($lockAge.TotalMinutes) + "m)")
        exit 0
    }
    Write-TaskLog -TaskName $task -Message ("gamma-drive: stale lock (age " + [math]::Round($lockAge.TotalHours, 1) + "h) -- overwriting")
}
try { (Get-Date).ToString("o") | Out-File -FilePath $lockFile -Encoding utf8 -Force } catch { }

try {
    Write-TaskLog -TaskName $task -Message ("gamma-drive: START (" + $et.ToString("yyyy-MM-dd HH:mm") + " ET)  caps: max=" + $MAX_INITIATIVES + " budget/fire=`$" + $PER_FIRE_BUDGET + " converge=" + $CONVERGENCE_STOP)

    if (-not (Test-Path $promptFile)) {
        Write-TaskLog -TaskName $task -Message "gamma-drive: ERROR gamma-drive.md missing at $promptFile"
        exit 1
    }

    # --- ANTI-LEAK retention (idempotent, fail-open, before the loop) ------------
    try { $null = Invoke-PythonHidden -ScriptPath "setup\scripts\status_retention.py" -ArgList @() -TaskName "status-retention" -TimeoutSec 30 } catch { }
    try { $null = Invoke-PythonHidden -ScriptPath "setup\scripts\loop_retention.py"   -ArgList @() -TaskName "loop-retention"   -TimeoutSec 30 } catch { }

    $noopStreak = 0
    for ($i = 1; $i -le $MAX_INITIATIVES; $i++) {

        # Re-gate EVERY iteration -- market may open, the deadline may pass, J may
        # drop the stop-flag, all DURING the loop.
        $et = Get-EtNow
        if ((Test-WeekDay -Et $et) -and (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 15 -EndMin 55)) {
            Write-TaskLog -TaskName $task -Message ("gamma-drive: STOP -- market opened mid-loop (" + $et.ToString("HH:mm") + " ET, rail 1)")
            break
        }
        if (Test-PastDeadline -Et $et) {
            Write-TaskLog -TaskName $task -Message ("gamma-drive: STOP -- past wall-clock deadline 0" + $DEADLINE_HOUR_ET + ":" + $DEADLINE_MIN_ET + " ET (premarket guard)")
            break
        }
        if (Test-Path $stopFlag) {
            Write-TaskLog -TaskName $task -Message "gamma-drive: STOP -- stop-flag dropped mid-loop; consuming and exiting"
            Remove-Item $stopFlag -Force -ErrorAction SilentlyContinue
            break
        }

        $beforeLast = Get-LastOutcomeLine -Path $outcomes

        Write-TaskLog -TaskName $task -Message ("gamma-drive: fire " + $i + "/" + $MAX_INITIATIVES + " (one initiative)")
        $exitCode = Invoke-ClaudeWithRetry `
            -PromptFile $promptFile `
            -TaskName $task `
            -MaxBudgetUsd $PER_FIRE_BUDGET `
            -Model "opus" `
            -Effort "high" `
            -AgentName "gamma" `
            -TimeoutSec $FIRE_TIMEOUT_SEC `
            -MaxRateLimitWaitSec 3600
        Write-TaskLog -TaskName $task -Message ("gamma-drive: fire " + $i + " exit=" + $exitCode)

        # --- CONVERGENCE: did this fire accomplish anything recordable? ----------
        $afterLast = Get-LastOutcomeLine -Path $outcomes
        if (Test-OutcomeNoop -Before $beforeLast -After $afterLast) {
            $noopStreak++
            Write-TaskLog -TaskName $task -Message ("gamma-drive: fire " + $i + " = NO-OP (streak " + $noopStreak + "/" + $CONVERGENCE_STOP + ")")
            if ($noopStreak -ge $CONVERGENCE_STOP) {
                Write-TaskLog -TaskName $task -Message ("gamma-drive: STOP -- convergence (" + $CONVERGENCE_STOP + " consecutive no-ops); vein dry, leaving the queue for the next run")
                break
            }
        } else {
            $noopStreak = 0
        }
    }

    Write-TaskLog -TaskName $task -Message "gamma-drive: END (loop complete)"
}
finally {
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
}
exit 0
