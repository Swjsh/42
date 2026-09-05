#requires -Version 5.1
<#
.SYNOPSIS
  Gamma Conductor wake fire -- the "Gamma drives" engine.

.DESCRIPTION
  Fires from Gamma_Conductor (after-hours cadence). Runs ONE bounded conductor
  tick: read engine-health + STATUS + the prioritized queue, pick the single
  highest-value ready item, fan out the right specialist persona, validate
  (gym/tests), SHIP if it clears the auto-ratify gate ELSE flag J via Discord,
  update STATUS + queue, exit. Prompt: automation/prompts/conductor.md.
  Persona: .claude/agents/gamma.md (Manager mode). Model: opus.

  SAFETY RAIL 1 (after-hours only, L54): this wrapper hard-gates on market hours
  as defense-in-depth. If it is a weekday and 09:30 <= ET < 15:55, the conductor
  does NOT spawn Claude -- a market-hours fan-out would starve the heartbeat on
  the shared Max rate-limit pool. The prompt re-checks this gate (STAGE 0), but
  the wrapper refusing first means zero model spend during RTH.

  SAFETY RAIL 2 (fail-open): this wrapper NEVER kills/blocks any process. It only
  spawns its own claude --print (tree-scoped self-heal in Invoke-Claude) and exits.

  Invoked via the OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-conductor.ps1 -> claude --print
#>

$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

. "$PSScriptRoot\_shared.ps1"

$task = "conductor"
$today = (Get-Date).ToString("yyyy-MM-dd")

# --- SAFETY RAIL 1: after-hours gate (defense in depth; prompt re-checks) ------
$et = Get-EtNow
if ((Test-WeekDay -Et $et) -and (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 15 -EndMin 55)) {
    Write-TaskLog -TaskName $task -Message ("conductor: SKIP -- market open (" + $et.ToString("HH:mm") + " ET), deferring to heartbeat (rail 1 / L54)")
    exit 0
}

Write-TaskLog -TaskName $task -Message ("conductor: START (" + $et.ToString("yyyy-MM-dd HH:mm") + " ET)")

# --- RAIL 0 BUDGET PRE-CHECK (2026-08-08, CONDUCTOR-GATE-PRECHECK) --------------
# THE FINDING (analysis/recommendations/conductor-cost-correction-measurement-2026-08-08.md,
# section "Near-zero-self-report fires"): conductor.md's own STAGE-0 budget gate runs
# INSIDE the spawned Claude session -- so every gated-out (EXHAUSTED) fire still boots a
# full Claude session (reads CLAUDE.md + conductor.md + the gamma agent's whole MCP tool
# surface), evaluates the gate, and exits -- measured ~$1.25 real token cost per no-op
# fire (n=54, 2026-07-26..2026-08-08), self-reporting ~$0 every single time (0 x any
# correction factor is still 0 -- no multiplicative fix can catch this, only moving the
# gate earlier can). This block runs the IDENTICAL check (conductor_budget.py --check,
# the exact module conductor.md's own STAGE 0 step 0 already calls) BEFORE Claude is ever
# spawned, and before the cross-fire lock below (same architectural slot as rail 1's
# market-hours gate above -- a gate that decides not to run should never touch the lock).
# conductor.md's in-prompt STAGE 0 gate is KEPT UNCHANGED as a belt-and-braces second
# check (see its updated prose) -- it remains the ONLY gate for `Gamma_ConductorWeekend`
# (a separate wrapper, run-conductor-weekend.ps1 -- PORTED there the same evening,
#  2026-08-08: both wrappers now precheck before spawning Claude)
# and the fail-safe if this pre-check ever mis-fires.
#
# FAIL-OPEN IS MANDATORY (rail 2 -- a broken meter must never silence the autonomous
# loop; that would be a worse bug than the one being fixed here). ANY failure of this
# block -- missing interpreter/script, a non-3 exit code, a timeout, a thrown exception
# -- falls through to the normal Claude fire below, unchanged. Only a CONFIRMED exit
# code 3 (conductor_budget.py's EXIT_EXHAUSTED) skips the spawn.
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
        # catch (caught live by backtest/tests/test_conductor_gate_precheck.py's
        # timeout test during this fix's own build). conductor_budget.py --check's
        # real output is a few bounded lines (well under the ~4KB anonymous-pipe
        # buffer), so reading only AFTER a confirmed exit is safe here -- it will
        # never itself block once the process has already exited.
        if ($precheckProc.WaitForExit(30000)) {
            $precheckExitCode = $precheckProc.ExitCode
            $precheckStdout = $precheckProc.StandardOutput.ReadToEnd()
            $precheckStderr = $precheckProc.StandardError.ReadToEnd()
            if ($precheckStdout) {
                Write-TaskLog -TaskName $task -Message ("conductor: rail-0 precheck stdout: " + $precheckStdout.Trim())
            }
            if ($precheckStderr) {
                Write-TaskLog -TaskName $task -Message ("conductor: rail-0 precheck stderr: " + $precheckStderr.Trim())
            }
        } else {
            # Kill() -- NOT Kill($true). The "entire process tree" overload
            # (Process.Kill(Boolean)) is not available on this box's Windows
            # PowerShell 5.1 / .NET Framework combo -- it throws
            # "Cannot find an overload for Kill and the argument count: 1", which a
            # bare try/catch here would silently swallow, leaving the hung child
            # ORPHANED and still running (verified live during this fix's own build:
            # Kill($true) throws + is caught, Kill() alone terminates the process
            # within ~5ms). conductor_budget.py --check is a single leaf process (it
            # spawns no children of its own), so the plain single-process Kill() is
            # sufficient -- there is no subtree to reap.
            try { $precheckProc.Kill() } catch { }
            Write-TaskLog -TaskName $task -Message "conductor: RAIL-0 PRECHECK TIMEOUT (30s) -- failing OPEN, proceeding to Claude fire"
        }
    } catch {
        Write-TaskLog -TaskName $task -Message ("conductor: RAIL-0 PRECHECK ERROR (" + $_.Exception.Message + ") -- failing OPEN, proceeding to Claude fire")
        $precheckExitCode = $null
    }
} else {
    Write-TaskLog -TaskName $task -Message "conductor: RAIL-0 PRECHECK SKIPPED -- venv python or conductor_budget.py missing, failing OPEN"
}

if ($precheckExitCode -eq 3) {
    # NOTE: "$0.00" (literal dollar sign) inside a PS double-quoted string gets parsed
    # as a reference to variable $0 (undefined -> empty), silently swallowing the "$0"
    # and leaving ".00" -- caught live in the real log during this fix's own end-to-end
    # verification. Say "zero real cost" instead of risking the same class of bug again.
    Write-TaskLog -TaskName $task -Message "conductor: RAIL-0 PRECHECK EXHAUSTED -- SKIP, Claude session never spawned (zero real cost)"
    $preTaskId = "PRECHECK-BUDGET-EXHAUSTED-" + (Get-EtNow).ToString("yyyy-MM-ddTHHmmss")
    $preNote = "rail-0 budget gate EXHAUSTED (PowerShell pre-check, before Claude spawn) -- zero real cost, Claude session never launched"
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
    Write-TaskLog -TaskName $task -Message "conductor: END exit=0 (rail-0 precheck blocked, Claude never spawned)"
    exit 0
}
# ===RAIL0-PRECHECK-BLOCK-END===

# --- CROSS-FIRE LOCK (fail-open; shared with conductor-weekend) -----------------
# See Enter-ConductorFireLock in _shared.ps1 for the full incident writeup (2026-07-18
# self-audit gap + same-day F7 duplicate-build + a `git stash` collision).
$conductorLock = Enter-ConductorFireLock
$conductorLockFile = $conductorLock.lockFile
if (-not $conductorLock.acquired) {
    Write-TaskLog -TaskName $task -Message ("conductor: SKIP -- another conductor fire holds the lock (age " + [math]::Round($conductorLock.ageMinutes, 1) + "m)")
    exit 0
}
$conductorLockHeld = $true

$exitCode = 1
try {
    # --- L181 RETENTION AUTOWIRE (self-executing, after-hours only) -------------
    # STATUS.md silently regrows past the ~25K-token Read cap between fires -- the
    # 06-22 + 06-24 manual trims each regrew within hours (commit a795fc3 BUILT the
    # durable guard; this call makes it run without a fire having to NOTICE + run it).
    # status_retention.py is idempotent (no-op when under budget), fail-open (never
    # throws), and atomic-write -- safe to call on every after-hours conductor wake.
    # Runs AFTER the rail-1 gate (after-hours only) and BEFORE the claude launch so
    # THIS fire reads a freshly-trimmed STATUS. CREATE_NO_WINDOW (no flash, OP-27 L42).
    try {
        $null = Invoke-PythonHidden -ScriptPath "setup\scripts\status_retention.py" `
            -ArgList @() -TaskName "status-retention" -TimeoutSec 30
    } catch { }

    # --- B2b TWIN-GAUNTLET-GAP CHECK (self-executing, after-hours only) ---------
    # markdown/planning/TWIN-PROGRAM.md value stream #2: "Conductor hook: trading-path
    # commits without a gauntlet pass get flagged." twin_gauntlet_conductor_hook.py is
    # pure stdlib (system-python safe, no pandas/pytest needed), fail-open (catches
    # every exception internally, ALWAYS exits 0), and ADVISORY ONLY -- it can only
    # APPEND one line to STATUS.md "## Known broken" + queue.md's Active backlog on a
    # genuinely new trading-path-without-coverage gap; it never blocks this wrapper or
    # the claude launch below. Shares a watermark file with setup/guard_runner_slow.py's
    # equivalent call (idempotent -- whichever fires first flags, the other no-ops).
    try {
        $null = Invoke-PythonHidden -ScriptPath "setup\scripts\twin_gauntlet_conductor_hook.py" `
            -ArgList @() -TaskName "twin-gauntlet-conductor-hook" -TimeoutSec 30
    } catch { }

    # --- GOAL-AUTOPILOT PRE-SPAWN (2026-09-03, task A1 GOAL-GAMMA-AUTONOMY-2026-09-03) ---
    # Ensures active-goal.json is current BEFORE the conductor reads it (STAGE 1 clause
    # 2a routes each fire to the goal's top open item) -- without this, a fire could read
    # a goal that expired or went terminal since the LAST 30-min Gamma_GoalAutopilot tick
    # and fall through to tier-3 janitorial work for up to half an hour longer than it has
    # to. Pure stdlib Python ($0, no LLM/network/broker) -- same Invoke-PythonHidden
    # pattern as the calls above, fail-open (any error/timeout logs and falls through to
    # the normal Claude fire unchanged; goal_autopilot.py itself is also fail-open
    # internally and always exits 0 unless --strict, which this call never passes).
    try {
        $goalAutopilotResult = Invoke-PythonHidden -ScriptPath "setup\scripts\goal_autopilot.py" `
            -ArgList @("ensure") -TaskName "goal-autopilot-prespawn" -TimeoutSec 30
        $firstLine = ""
        if ($goalAutopilotResult -and $goalAutopilotResult.Stdout) {
            $firstLine = ($goalAutopilotResult.Stdout -split "`r?`n" | Where-Object { $_ -ne "" } | Select-Object -First 1)
        }
        Write-TaskLog -TaskName $task -Message ("conductor: goal-autopilot " + $firstLine)
    } catch {
        Write-TaskLog -TaskName $task -Message ("conductor: goal-autopilot pre-spawn ERROR (" + $_.Exception.Message + ") -- failing OPEN, proceeding to Claude fire")
    }

    $promptFile = Join-Path $projectRoot "automation\prompts\conductor.md"
    if (-not (Test-Path $promptFile)) {
        Write-TaskLog -TaskName $task -Message "conductor: ERROR conductor.md missing at $promptFile"
        exit 1
    }

    # Opus -- the conductor's job is hard reasoning (single highest-leverage item +
    # is it safe to ship). AgentName=gamma loads Manager-mode persona context. Retry
    # wrapper handles rate-limit skip-ahead.
    # BUDGET (2026-06-20): raised 1.50 -> 10.00. The FIRST live fire aborted at t+1s
    # with "Exceeded USD budget (1.5)" having done ZERO work -- same failure class as
    # run-heartbeat.ps1:163. --max-budget-usd counts CUMULATIVE input tokens (cache
    # reads + every tool result becomes next-turn input), and an opus + high-effort
    # fire that loads CLAUDE.md + conductor.md + the gamma agent's full MCP tool
    # surface (alpaca + alpaca_aggressive + tradingview + discord) AND fans out
    # specialist sub-agents (whose tokens roll up into this session) blows past 1.50
    # immediately. 10.00 lets one bounded fan-out fire + validation actually COMPLETE;
    # the real runaway guard is -TimeoutSec 600 below, not the dollar cap.
    # MODEL (2026-07-02, J quota directive): opus -> sonnet. Conductor fires are queue-drain
    # fix-and-guard work; sonnet + the fable-judgment suite (mandatory via CLAUDE.md) handles
    # them at ~1/5 the pool cost. Reserve opus-class for frame-audit/architecture sessions only.
    # FAN-OUT BLAST RADIUS (2026-08-19). Anthropic ships depth/concurrency caps whose
    # DEFAULTS are depth 3 / concurrency 20, and one Agent call has been reported to
    # grow into 48+ background agents / ~1.5M tokens. Our doctrine is narrower: rail 3
    # says ONE bounded item per fire, and conductor.md STAGE 2 already says "spawn 2-5
    # agents in a SINGLE message" -- so pin depth=1 (specialists may not spawn their
    # own subagents) and concurrency=5 (matches the prompt's own ceiling).
    # Wired HERE, at automation's own launch point, never as a global interactive
    # default (L213 -- J's interactive sessions must not inherit automation limits).
    # Values are the registry's: automation/state/worker-registry.json .master.fanout_caps.
    # UNVERIFIED AT RUNTIME: env-var names come from Anthropic's Agent SDK docs
    # (verified 2026-08-19) and are version-gated; an unrecognised name is ignored, so
    # this fails OPEN -- it can tighten the blast radius, never break a fire.
    $env:CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH = "1"
    $env:CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS = "5"

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
    # Lock ALWAYS released here even if the block above throws/exits early --
    # matches the Invoke-TvLaunchSafe / run-gamma-drive.ps1 finally-release pattern
    # so a crashed fire never wedges the lock past the stale-minutes threshold.
    if ($conductorLockHeld) {
        Exit-ConductorFireLock -LockFile $conductorLockFile
    }
}

Write-TaskLog -TaskName $task -Message "conductor: END exit=$exitCode"
exit $exitCode
