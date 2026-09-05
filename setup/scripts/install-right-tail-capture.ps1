#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_RightTailCapture -- daily right-tail wave capture-scoring
  instrument (GOAL-RIGHT-TAIL-CAPTURE-2026-09-05, R3). Fires 16:20 ET weekdays
  (14:20 MT local -- this box is Mountain, ET=local+2h), after
  Gamma_ZeroEnterAutopsy (16:10 ET) so both read a fully-closed trading day.

.DESCRIPTION
  Runs `setup/scripts/right_tail_capture.py` (no --date arg -- the script
  itself defaults to today via et_clock.et_today_str) for today's trading
  day, writing `analysis/right-tail/CAPTURE-<date>.json` and appending to the
  rolling `analysis/right-tail/ledger.jsonl`: per arm, per >=1.3x right-tail
  wave (backtest/lib/right_tail_waves.find_waves) -- taken/missed, latency,
  held-to-TP1, runner-ran, refused-by-which-gate, second-wave presence.

  Read-only instrument. NEVER touches a FROZEN_TRADING_PATH file (params.json,
  aggressive/params.json, fleet/accounts.json, fleet/strategies.py,
  fleet/exit_manager.py, fleet/fleet_executor.py, fleet/build_shared_signal.py,
  backtest/lib/filters.py, backtest/lib/risk_gate.py,
  setup/scripts/heartbeat_core.py) -- only reads from them. Fails open: a
  missing OPRA cache, fills row, or fleet decisions file degrades that one
  field to a labeled null, never crashes.

  WIRING PATTERN (flash-free, cloned from install-zero-enter-autopsy.ps1):
    wscript -> run_exe_hidden.vbs -> backtest venv pythonw -> run_cmd_hidden.py --cwd <repo>
      -- backtest venv pythonw -> right_tail_capture.py (defaults --date to today ET)
  Uses the backtest venv's python (pandas dependency for the OPRA bar pricing
  in right_tail_waves.py), not system pythonw.

  Output: analysis/right-tail/CAPTURE-<date>.json (one per trading day) +
          analysis/right-tail/ledger.jsonl (rolling append).
  Logs: automation/state/logs/run-cmd-hidden-<date>.log

  To verify: Get-ScheduledTask -TaskName Gamma_RightTailCapture
  To test now: Start-ScheduledTask -TaskName Gamma_RightTailCapture
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_RightTailCapture" -Confirm:$false

  Per CLAUDE.md OP-3 ($0, pure Python) + the goal's CONFIG FREEZE OPERATING
  RULES (read-only instrument, no FROZEN_TRADING_PATH writes). Guard:
  backtest/tests/test_right_tail_waves.py.
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$venvPython   = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\right_tail_capture.py"
$taskName     = "Gamma_RightTailCapture"

foreach ($p in @($vbs, $venvPython, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# --date defaults to today (ET, via et_clock.et_today_str -- never Bash/system-local
# TZ) inside right_tail_capture.py itself when omitted, so the fire command is a
# plain fixed argument list -- no fragile at-fire-time date injection needed.
$wscriptArgs = "//nologo `"$vbs`" `"$venvPython`" `"$runCmdHidden`" --cwd `"$root`" -- `"$venvPython`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 14:20 MT = 16:20 ET, weekdays Mon-Fri -- after Gamma_ZeroEnterAutopsy (16:10 ET).
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:20"

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
    -Description ("Right-tail wave capture-scoring instrument (GOAL-RIGHT-TAIL-CAPTURE-" + `
    "2026-09-05 R3). Runs right_tail_capture.py --date <today> -> " + `
    "analysis/right-tail/CAPTURE-<date>.json + ledger.jsonl. Read-only; never touches a " + `
    "FROZEN_TRADING_PATH file. Fires 16:20 ET weekdays, after Gamma_ZeroEnterAutopsy. " + `
    "Pure Python (backtest venv, pandas), `$0. Guard: " + `
    "backtest/tests/test_right_tail_waves.py.") `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $taskName for weekdays 14:20 MT (16:20 ET)"
Write-Output "    Output:   analysis\right-tail\CAPTURE-<date>.json + ledger.jsonl"
Write-Output "    Test now: Start-ScheduledTask -TaskName $taskName"
Write-Output "    Next run: $($info.NextRunTime)"
