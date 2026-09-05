#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_ZeroEnterAutopsy -- per-bar zero-enter-day counterfactual
  instrument (GOAL-ZERO-ENTER-DAYS-2026-09-03, Z4). Fires 16:10 ET weekdays
  (14:10 MT local -- this box is Mountain, ET=local+2h), after Gamma_EodFlatten
  (15:55 ET) so the trading day's ledger is fully closed before the autopsy reads it.

.DESCRIPTION
  Runs `setup/scripts/zero_enter_autopsy.py` (no --date arg -- the script itself
  defaults to today via et_clock.et_today_str) for today's trading day, writing
  `analysis/zero-enter/ZERO-ENTER-<date>.json`: a per-bar table
  (which blocker fired at which 5-min bar, SPY price, would-have-entered flag)
  plus a day summary (thesis, dominant blocker, thesis payoff net of the real
  cost model) for any day the core engine's own _grade_zero_enter_day
  (setup/scripts/conductor_outcome.py) grades SAT_OUT_GATED or regressing.

  Read-only autopsy. NEVER touches a FROZEN_TRADING_PATH file (params.json,
  aggressive/params.json, fleet/accounts.json, fleet/strategies.py,
  fleet/exit_manager.py, fleet/fleet_executor.py, fleet/build_shared_signal.py,
  backtest/lib/filters.py, backtest/lib/risk_gate.py,
  setup/scripts/heartbeat_core.py) -- only reads from them. Fails open: a
  quiet/no-high-score day or missing data degrades every field to a labeled
  null, never crashes or blocks anything else.

  WIRING PATTERN (flash-free, cloned from install-task-staleness.ps1):
    wscript -> run_exe_hidden.vbs -> backtest venv pythonw -> run_cmd_hidden.py --cwd <repo>
      -- backtest venv pythonw -> zero_enter_autopsy.py (defaults --date to today ET)
  Uses the backtest venv's python (pandas dependency for the real OPRA/SIP bar
  reconstruction), not system pythonw.

  Output: analysis/zero-enter/ZERO-ENTER-<date>.json (one per trading day).
  Logs: automation/state/logs/run-cmd-hidden-<date>.log

  To verify: Get-ScheduledTask -TaskName Gamma_ZeroEnterAutopsy
  To test now: Start-ScheduledTask -TaskName Gamma_ZeroEnterAutopsy
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_ZeroEnterAutopsy" -Confirm:$false

  Per CLAUDE.md OP-3 ($0, pure Python) + the goal's CONFIG FREEZE OPERATING
  RULES (read-only instrument, no FROZEN_TRADING_PATH writes). Guard:
  backtest/tests/test_zero_enter_autopsy.py.
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$venvPython   = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\zero_enter_autopsy.py"
$taskName     = "Gamma_ZeroEnterAutopsy"

foreach ($p in @($vbs, $venvPython, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# --date defaults to today (ET, via et_clock.et_today_str -- never Bash/system-local
# TZ) inside zero_enter_autopsy.py itself when omitted, so the fire command is a
# plain fixed argument list -- no fragile at-fire-time date injection needed.
$wscriptArgs = "//nologo `"$vbs`" `"$venvPython`" `"$runCmdHidden`" --cwd `"$root`" -- `"$venvPython`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 14:10 MT = 16:10 ET, weekdays Mon-Fri -- after Gamma_EodFlatten (15:55 ET).
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:10"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Zero-enter-day per-bar counterfactual autopsy (GOAL-ZERO-ENTER-DAYS-" + `
    "2026-09-03 Z4). Runs zero_enter_autopsy.py --date <today> -> " + `
    "analysis/zero-enter/ZERO-ENTER-<date>.json. Read-only; never touches a " + `
    "FROZEN_TRADING_PATH file. Fires 16:10 ET weekdays, after Gamma_EodFlatten. " + `
    "Pure Python (backtest venv, pandas), `$0. Guard: " + `
    "backtest/tests/test_zero_enter_autopsy.py.") `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $taskName for weekdays 14:10 MT (16:10 ET)"
Write-Output "    Output:   analysis\zero-enter\ZERO-ENTER-<date>.json"
Write-Output "    Test now: Start-ScheduledTask -TaskName $taskName"
Write-Output "    Next run: $($info.NextRunTime)"
