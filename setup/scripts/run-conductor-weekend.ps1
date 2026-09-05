#requires -Version 5.1
<#
.SYNOPSIS
  Gamma Conductor WEEKEND wake fire -- the full "Gamma drives" loop, weekend cadence.

.DESCRIPTION
  Fires from Gamma_ConductorWeekend (every 2h, Saturday+Sunday, all day). Runs the SAME
  full STAGE 0->5 loop as the after-hours Gamma_Conductor -- read health + STATUS + queue,
  pick the single highest-value ready item, fan out a specialist, validate, ship-or-propose,
  learn, update state -- with the WEEKEND nudge in conductor.md's STAGE 1 (crypto-twin +
  Kitchen checked first, since nobody else reads them on a weekday-biased cadence).

  J directive 2026-07-18: "crypto weekends, futures n options during the week" -- weekends
  had ZERO daytime conductor coverage before this (the old Gamma_Conductor's 18:00-07:00 ET
  window only ever covered the overnight hours, even on a Saturday/Sunday). This wrapper
  closes that gap.

  SAME rails as run-conductor.ps1: after-hours-equivalent (market is never open on a
  weekend, but the gate is re-checked anyway as defense-in-depth against a misfire),
  fail-open, one-task-per-fire, PAPER-only trading-path edits.

  Invoked via the OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-conductor-weekend.ps1 -> claude --print
#>

$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

. "$PSScriptRoot\_shared.ps1"

$task = "conductor-weekend"
$today = (Get-Date).ToString("yyyy-MM-dd")

# --- GATE: weekend ONLY (defense in depth -- the trigger is Weekly/Sat+Sun, this catches
# a misfire/manual Start-ScheduledTask on a weekday and refuses to spend on it). -----------
# NOTE (bug found + fixed live during the 2026-07-18 build/verification fire): an earlier
# version of this gate ALSO called Test-MarketHours on its own, unconjoined with
# Test-WeekDay -- that matches on CLOCK TIME alone and false-SKIPped a genuine Saturday
# fire simply because the ET hour (11:04) happened to fall inside the 09:30-15:55 numeric
# range. Test-WeekDay alone is the correct and sufficient gate here: a market is only ever
# "open" on a weekday in the first place, so ANY weekday (RTH or after-hours) correctly
# defers to Gamma_Conductor/Gamma_ConductorRTH, and no weekend clock-hour is ever RTH.
$et = Get-EtNow
if (Test-WeekDay -Et $et) {
    Write-TaskLog -TaskName $task -Message ("conductor-weekend: SKIP -- weekday (" + $et.ToString("ddd HH:mm") + " ET), this mode is weekend-only")
    exit 0
}

Write-TaskLog -TaskName $task -Message ("conductor-weekend: START (" + $et.ToString("yyyy-MM-dd HH:mm dddd") + " ET)")

# --- RAIL 0 BUDGET PRE-CHECK (2026-08-08, LANE 1 -- CONDUCTOR-GATE-PRECHECK weekend port) ---
# Ported from run-conductor.ps1's rail-0 block (same commit family). THE FINDING there applies
# HARDER here: Gamma_ConductorWeekend fires every 2h across BOTH Saturday and Sunday (far more
# scheduled slots/week than the weekday conductor), so it was the larger remaining source of
# near-zero-self-report waste once the weekday wrapper got its own precheck. Before this port,
# run-conductor.ps1's own doc comment explicitly named this file as the ONLY remaining wrapper
# that still spawned Claude before checking the budget -- conductor.md's in-prompt STAGE 0 gate
# was catching it, but only AFTER a full Claude session had already booted (CLAUDE.md +
# conductor.md + the gamma agent's whole MCP tool surface), at ~$1.25 real cost per no-op.
#
# Adapted, not blind-pasted: this wrapper's mode string is "conductor-weekend" (not
# "conductor"), so the recorded task-id/note are WEEKEND-tagged for downstream attribution
# (LANE 1 step 6 quantification) while still containing the literal word "budget" so
# autonomy_report.py's classify_noop_reason() still buckets it as budget_exhausted (checked
# in priority order ahead of any other marker -- see that function's docstring). This wrapper
# has no market-hours rail 1 of its own (the weekday-only gate above plays that role -- a
# market is never open on a weekend), so this block sits in the same architectural slot:
# after the wrapper's own "should this fire run at all" gate, before the cross-fire lock (a
# gate that decides not to run should never touch the lock file).
#
# FAIL-OPEN IS MANDATORY (identical to the weekday block): a broken meter must never silence
# the autonomous loop. Only a CONFIRMED exit code 3 (conductor_budget.py's EXIT_EXHAUSTED)
# skips the spawn; every other outcome (missing interpreter/script, timeout, thrown exception)
# falls through to the normal Claude fire below, unchanged.
# ===RAIL0-PRECHECK-BLOCK-START=== (test seam: backtest/tests/test_conductor_gate_precheck.py
# extracts the code between these two marker lines verbatim and swaps only the interpreter
# /script/outcome-recorder paths + the wait timeout for fixtures -- never touches this file).
$budgetPrecheckPy = Join-Path $projectRoot "backtest\.venv\Scripts\python.exe"
$budgetPrecheckScript = Join-Path $projectRoot "setup\scripts\conductor_budget.py"
$precheckExitCode = $null
if ((Test-Path $budgetPrecheckPy) -and (Test-Path $budgetPrecheckScript)) {
    try {
        $precheckPsi = New-Object System.Diagnostics.ProcessStartInfo
        $precheckPsi.FileName = $budgetPrecheckPy
        $precheckPsi.Arguments = '"' + $budgetPrecheckScript + '" --check'
        $precheckPsi.WorkingDirectory = $projectRoot
        $precheckPsi.UseShellExecute = $false
        $precheckPsi.CreateNoWindow = $true
        $precheckPsi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
        $precheckPsi.RedirectStandardOutput = $true
        $precheckPsi.RedirectStandardError = $true
        $precheckProc = [System.Diagnostics.Process]::Start($precheckPsi)
        # WaitForExit FIRST, THEN read stdout/stderr -- NOT the other way around.
        # ReadToEnd() blocks until the pipe's write end closes, which normally only
        # happens on process exit; calling it before WaitForExit deadlocks (blocks
        # indefinitely, ignoring the 30s timeout entirely) on a hung child that
        # produces no output -- exactly the pathological case this timeout exists to
        # catch (same defect class caught live in run-conductor.ps1's own build --
        # ported here unchanged rather than reintroduced).
        if ($precheckProc.WaitForExit(30000)) {
            $precheckExitCode = $precheckProc.ExitCode
            $precheckStdout = $precheckProc.StandardOutput.ReadToEnd()
            $precheckStderr = $precheckProc.StandardError.ReadToEnd()
            if ($precheckStdout) {
                Write-TaskLog -TaskName $task -Message ("conductor-weekend: rail-0 precheck stdout: " + $precheckStdout.Trim())
            }
            if ($precheckStderr) {
                Write-TaskLog -TaskName $task -Message ("conductor-weekend: rail-0 precheck stderr: " + $precheckStderr.Trim())
            }
        } else {
            # Kill() -- NOT Kill($true). The "entire process tree" overload
            # (Process.Kill(Boolean)) is not available on this box's Windows
            # PowerShell 5.1 / .NET Framework combo -- it throws
            # "Cannot find an overload for Kill and the argument count: 1", which a
            # bare try/catch here would silently swallow, leaving the hung child
            # ORPHANED and still running. conductor_budget.py --check is a single leaf
            # process (spawns no children of its own), so the plain single-process
            # Kill() is sufficient -- there is no subtree to reap. Ported unchanged
            # from run-conductor.ps1 rather than reintroduced.
            try { $precheckProc.Kill() } catch { }
            Write-TaskLog -TaskName $task -Message "conductor-weekend: RAIL-0 PRECHECK TIMEOUT (30s) -- failing OPEN, proceeding to Claude fire"
        }
    } catch {
        Write-TaskLog -TaskName $task -Message ("conductor-weekend: RAIL-0 PRECHECK ERROR (" + $_.Exception.Message + ") -- failing OPEN, proceeding to Claude fire")
        $precheckExitCode = $null
    }
} else {
    Write-TaskLog -TaskName $task -Message "conductor-weekend: RAIL-0 PRECHECK SKIPPED -- venv python or conductor_budget.py missing, failing OPEN"
}

if ($precheckExitCode -eq 3) {
    # NOTE: "$0.00" (literal dollar sign) inside a PS double-quoted string gets parsed
    # as a reference to variable $0 (undefined -> empty), silently swallowing the "$0"
    # and leaving ".00" -- same bug class caught live during the weekday build's own
    # end-to-end verification. Say "zero real cost" instead of risking it again.
    Write-TaskLog -TaskName $task -Message "conductor-weekend: RAIL-0 PRECHECK EXHAUSTED -- SKIP, Claude session never spawned (zero real cost)"
    $preTaskId = "PRECHECK-BUDGET-EXHAUSTED-WEEKEND-" + (Get-EtNow).ToString("yyyy-MM-ddTHHmmss")
    $preNote = "rail-0 budget gate EXHAUSTED (weekend conductor pre-check, PowerShell, before Claude spawn) -- zero real cost, Claude session never launched"
    try {
        $precheckRecordArgs = @(
            "record",
            "--task-id", $preTaskId,
            "--cost", "0",
            "--drained", "0",
            "--added", "0",
            "--lessons", "0",
            "--tests-delta", "0",
            "--regressions", "0",
            "--note", $preNote
        )
        $null = Invoke-PythonHidden -ScriptPath "setup\scripts\conductor_outcome.py" `
            -ArgList $precheckRecordArgs -TaskName "$task-precheck-record" -TimeoutSec 30
    } catch { }
    Write-TaskLog -TaskName $task -Message "conductor-weekend: END exit=0 (rail-0 precheck blocked, Claude never spawned)"
    exit 0
}
# ===RAIL0-PRECHECK-BLOCK-END===

# ===PRESENCE-GATE-BLOCK-START=== (test seam: backtest/tests/test_presence_gate_conductor_wiring_2026_09_05.py
# extracts the code between these two marker lines verbatim and swaps only the interpreter
# /script/outcome-recorder paths + the check result -- never touches this file).
# --- PRESENCE GATE (2026-09-05, GOAL-SILENT-RIG-2026-09-05 R4b) -----------------
# J: "everything must be silent... i can't have my pc bogged down." A conductor fire
# (a full Claude session + its MCP children + subagent fan-out) is exactly the load
# this goal exists to suppress while J is actively at the box. Right after the
# rail-0 budget precheck (same architectural slot: after the wrapper's own "should
# this fire run at all" gates, before the cross-fire lock -- a gate that decides not
# to run should never touch the lock file), ask presence_gate.py's --conductor-check
# mode (exit 3 == J present, mirroring conductor_budget.py's --check convention
# above) whether J is at the keyboard (input within 5 min) or in a fullscreen app
# (foreground within 10 min). If present: log, record a PRESENCE-SKIP outcome row
# (zero cost, Claude never spawned), and end the fire with exit 0 -- identical shape
# to the rail-0 budget-exhausted block. FAIL-OPEN, same discipline as rail-0: only a
# CONFIRMED exit 3 skips the spawn; a missing interpreter/script, timeout, or thrown
# exception falls through to the normal Claude fire below, unchanged. This block
# runs BEFORE `$env:GAMMA_CONDUCTOR_FIRE = "1"` is set further down, so
# conductor_outcome.py's own fire_source() naturally tags this row "interactive"
# (a scheduled conductor fire that was skipped is not a conductor "fire" for
# max_fires purposes) without needing a --source CLI flag (record's subparser
# exposes none; the CLI as-shipped already does the right thing here).
$presenceGatePy = Join-Path $projectRoot "backtest\.venv\Scripts\python.exe"
$presenceGateScript = Join-Path $projectRoot "setup\scripts\presence_gate.py"
$presenceExitCode = $null
$presenceStdout = ""
if ((Test-Path $presenceGatePy) -and (Test-Path $presenceGateScript)) {
    try {
        $presenceResult = Invoke-PythonHidden -ScriptPath $presenceGateScript `
            -ArgList @("--conductor-check") -TaskName "$task-presence-gate" -TimeoutSec 30
        $presenceExitCode = $presenceResult.ExitCode
        $presenceStdout = $presenceResult.Stdout
        if ($presenceStdout) {
            Write-TaskLog -TaskName $task -Message ("conductor-weekend: presence-gate stdout: " + $presenceStdout.Trim())
        }
    } catch {
        Write-TaskLog -TaskName $task -Message ("conductor-weekend: PRESENCE GATE ERROR (" + $_.Exception.Message + ") -- failing OPEN, proceeding to Claude fire")
        $presenceExitCode = $null
    }
} else {
    Write-TaskLog -TaskName $task -Message "conductor-weekend: PRESENCE GATE SKIPPED -- venv python or presence_gate.py missing, failing OPEN"
}

if ($presenceExitCode -eq 3) {
    Write-TaskLog -TaskName $task -Message "conductor: PRESENCE SKIP -- J at the box"
    $presTaskId = "PRESENCE-SKIP-WEEKEND-" + (Get-EtNow).ToString("yyyy-MM-ddTHHmmss")
    $presNote = "presence gate PRESENT (J at the box, rail-0 conductor pre-check, before Claude spawn) -- zero real cost, Claude session never launched. " + $presenceStdout.Trim()
    try {
        $presRecordArgs = @(
            "record",
            "--task-id", $presTaskId,
            "--cost", "0",
            "--drained", "0",
            "--added", "0",
            "--lessons", "0",
            "--tests-delta", "0",
            "--regressions", "0",
            "--note", $presNote
        )
        $null = Invoke-PythonHidden -ScriptPath "setup\scripts\conductor_outcome.py" `
            -ArgList $presRecordArgs -TaskName "$task-presence-record" -TimeoutSec 30
    } catch { }
    Write-TaskLog -TaskName $task -Message "conductor-weekend: END exit=0 (presence gate blocked, Claude never spawned)"
    exit 0
}
# ===PRESENCE-GATE-BLOCK-END===

# --- CROSS-FIRE LOCK (fail-open; SHARED with run-conductor.ps1) -----------------
# Same lock file / same Enter-ConductorFireLock helper as run-conductor.ps1 --
# conductor and conductor-weekend pick from the SAME queue.md and can (and, per
# 2026-07-18 STATUS.md evidence, DID) fire close enough together to independently
# build the byte-identical fix for the same item. See _shared.ps1's
# Enter-ConductorFireLock for the full incident writeup. Never blocks J's
# interactive session (rail 2); fails open via the stale-minutes overwrite.
$conductorLock = Enter-ConductorFireLock
$conductorLockFile = $conductorLock.lockFile
if (-not $conductorLock.acquired) {
    Write-TaskLog -TaskName $task -Message ("conductor-weekend: SKIP -- another conductor fire holds the lock (age " + [math]::Round($conductorLock.ageMinutes, 1) + "m)")
    exit 0
}
$conductorLockHeld = $true

$exitCode = 1
try {
    # Same L181 retention + B2b twin-gauntlet autowires as run-conductor.ps1 -- STATUS.md
    # silently regrows past the Read cap between fires regardless of which conductor mode
    # is writing to it, and a weekend fire is exactly the kind of trading-path-adjacent
    # session the gauntlet-gap check exists to catch.
    try {
        $null = Invoke-PythonHidden -ScriptPath "setup\scripts\status_retention.py" `
            -ArgList @() -TaskName "status-retention" -TimeoutSec 30
    } catch { }
    try {
        $null = Invoke-PythonHidden -ScriptPath "setup\scripts\twin_gauntlet_conductor_hook.py" `
            -ArgList @() -TaskName "twin-gauntlet-conductor-hook" -TimeoutSec 30
    } catch { }

    $promptFile = Join-Path $projectRoot "automation\prompts\conductor.md"
    if (-not (Test-Path $promptFile)) {
        Write-TaskLog -TaskName $task -Message "conductor-weekend: ERROR conductor.md missing at $promptFile"
        exit 1
    }

    # Sonnet, high effort, full $10 budget -- same as the after-hours full loop. The prompt's
    # `Task: conductor-weekend` header selects WEEKEND mode (STAGE 1 twin/kitchen nudge);
    # everything else is the identical STAGE 0->5 machinery.
    # Marks every conductor_outcome.py record row written by this spawn (and its
    # subagents) as source=conductor, so conductor_budget.py's max_fires counts real
    # spawns only -- not interactive-session goal records or PRECHECK rejections
    # (2026-09-05 Saturday lockout: 37 "fires" at $0.76 kept the conductor dark all day).
    $env:GAMMA_CONDUCTOR_FIRE = "1"

    $exitCode = Invoke-ClaudeWithRetry `
        -PromptFile $promptFile `
        -TaskName $task `
        -MaxBudgetUsd 10.00 `
        -Model "sonnet" `
        -Effort "high" `
        -AgentName "gamma" `
        -TimeoutSec 600 `
        -MaxRateLimitWaitSec 3600
}
finally {
    if ($conductorLockHeld) {
        Exit-ConductorFireLock -LockFile $conductorLockFile
    }
}

Write-TaskLog -TaskName $task -Message "conductor-weekend: END exit=$exitCode"
exit $exitCode
