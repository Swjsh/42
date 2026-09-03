#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_GoalAutopilot -- the deterministic (no-LLM) walker that opens the
  next automation/state/goals/LADDER.md entry whenever active-goal.json is
  inactive/expired/terminal, and closes a goal whose QUEUE has gone fully terminal
  or whose expiry has passed. Task A1, GOAL-GAMMA-AUTONOMY-2026-09-03.

.DESCRIPTION
  THE GAP THIS CLOSES: the durable-goal mechanism already had two free consumers
  wired up -- setup/hooks/doctrine.py's goal_next_open_item/goal_expired feed
  conductor.md STAGE 1 clause 2a (routes each fire to the goal's top open item) and
  the Stop hook's _check_goal_continuation (keeps one session going a few extra
  turns) -- but the ONE producer, .claude/skills/gamma-goal/SKILL.md, is
  `disable-model-invocation: true`. Only J can open a goal by literally typing
  `/gamma-goal open`, so active-goal.json sat `active:false` from 2026-08-30 to
  2026-09-03 (J: "your /goal is gamma autonomy") and every conductor fire fell
  through to tier-3 janitorial work -- busy, not learning.

  setup/scripts/goal_autopilot.py is the producer that does not need J: a pure,
  deterministic walk down LADDER.md (authored by Claude sessions or J -- THAT is
  where judgment enters, never this script). No LLM decides which goal opens next.

  RTH SAFETY: the script's own internal gate (Mon-Fri 09:30-15:55 ET) makes every
  fire inside market hours a pure no-op with ZERO file writes -- this task can run
  every 30 minutes 24/7 without any risk of colliding with the trading engine on
  the shared Max rate-limit pool (there is no LLM call here at all -- pure stdlib
  file IO -- but the same clock discipline as every other producer applies).

  WIRING PATTERN (flash-free, cloned from install-task-staleness.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> goal_autopilot.py ensure
  System pythonw (pure stdlib, no third-party deps -- goal_autopilot.py imports
  only setup/hooks/doctrine.py + setup/scripts/et_clock.py, both stdlib-only).

  CADENCE: every 30 min, 24/7 (matches install-window-leak-detector-keepalive.ps1's
  `-Once` + repetition + ~10-year duration idiom) -- most fires are a noop (the
  common case: a goal is already active with an open item) or a RTH no-op; the
  cadence just needs to be frequent enough that a closed/expired goal doesn't sit
  dark for long, and the conductor's own pre-spawn call (run-conductor.ps1) covers
  the "must be current before a conductor fire" case independently.

  Output:
    automation/state/goal-autopilot.json  -- latest status snapshot
    automation/state/goal-autopilot.jsonl -- append-only action log

  To verify: Get-ScheduledTask -TaskName Gamma_GoalAutopilot | Get-ScheduledTaskInfo
  To test now: Start-ScheduledTask -TaskName Gamma_GoalAutopilot
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_GoalAutopilot" -Confirm:$false
          (active-goal.json / LADDER.md / queue.md are left exactly as they are --
          nothing needs to be touched to revert; the conductor's routing clause and
          the Stop hook both simply stop seeing new opens/closes.)

  Per CLAUDE.md OP-3 ($0, pure Python, no new vendor) + OP-25 (fail loud/open,
  never silent) + OP-33 (visibility is the product). Guard:
  backtest/tests/test_goal_autopilot_2026_09_03.py.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$taskName     = "Gamma_GoalAutopilot"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\goal_autopilot.py"

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- system pythonw -> goal_autopilot.py ensure
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`" ensure"

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# Every 30 min, 24/7 -- the script's own RTH guard handles market hours (zero
# writes 09:30-15:55 ET weekdays); most other fires are a noop too (goal already
# active with an open item).
$startBoundary = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Gamma's own goal producer (task A1, GOAL-GAMMA-AUTONOMY-2026-09-03): " + `
    "deterministic (no LLM) walk of automation/state/goals/LADDER.md via goal_autopilot.py " + `
    "ensure. Opens the next queued goal whenever active-goal.json is inactive/expired/" + `
    "terminal; closes a goal whose QUEUE has gone fully terminal or whose expiry has passed. " + `
    "Every 30 min, 24/7 -- own internal RTH gate (Mon-Fri 09:30-15:55 ET) makes market-hours " + `
    "fires a zero-write noop. Pure stdlib Python, `$0, no network, no broker, no subprocess. " + `
    "Fail-open on any exception (always exit 0 unless --strict). Writes only under " + `
    "automation/state/ + one row of automation/overnight/queue.md; never touches " + `
    "doctrine.FROZEN_TRADING_PATH. Guard: backtest/tests/test_goal_autopilot_2026_09_03.py. " + `
    "REVERT: Unregister-ScheduledTask -TaskName Gamma_GoalAutopilot -Confirm:`$false " + `
    "(no other file needs touching to revert).") `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $taskName, every 30 min 24/7"
Write-Output "    Status:   automation\state\goal-autopilot.json"
Write-Output "    Log:      automation\state\goal-autopilot.jsonl"
Write-Output "    Test now: Start-ScheduledTask -TaskName $taskName"
Write-Output "    Next run: $($info.NextRunTime)"
