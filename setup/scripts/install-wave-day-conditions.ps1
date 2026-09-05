#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_WaveDayConditions -- daily $0 premarket instrument (GOAL-WAVE-DAY-
  CONDITIONS-2026-09-05, W3). Fires 09:20 ET weekdays (07:20 MT local -- this box is
  Mountain time, ET = local+2h), before the 09:30 ET open.

.DESCRIPTION
  Runs `setup/scripts/wave_day_conditions.py` (no --date arg -- the script itself
  defaults to today via et_clock.et_today_str) for today's session, computing the
  pre-09:41-ET market-conditions row (overnight gap %, first-15-min range/ATR20 where
  the day has already opened, opening VIX vs prior close, VIX 5-day slope, prior-day
  close vs prior-day VWAP, day of week, distance of the 09:30 print/premarket spot to
  the nearest key-levels zone, premarket bias) and appending it to
  `analysis/right-tail/wave-day-conditions.jsonl`. The wave/no-wave label itself joins
  in LATER, by date, once the existing 16:20 ET Gamma_RightTailCapture fire has scored
  the closed day (analysis/right-tail/CAPTURE-<date>.json) -- this 09:20 fire cannot
  know the day's outcome yet and correctly writes that field null with a reason
  (fail-open, C7 -- never a crash, never a fabricated number).

  Read-only, $0 instrument. NEVER touches a FROZEN_TRADING_PATH file (params.json,
  aggressive/params.json, fleet/accounts.json, fleet/*.py, backtest/lib/filters.py,
  backtest/lib/risk_gate.py, setup/scripts/heartbeat_core.py) -- only reads cached SPY/
  VIX bars, key-levels-history snapshots, and journal premarket bias lines. INFORMATIONAL
  class only (per its own prereg) -- nothing here touches a gate.

  WIRING PATTERN (cloned from install-right-tail-capture.ps1's proven shape):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --env
      PYTHONPATH=<repo>\backtest\.venv\Lib\site-packages --cwd <repo>
      -- system pythonw -> wave_day_conditions.py
  Both hops run SYSTEM pythonw (never the venv stub, which is console-subsystem
  underneath -- 2026-09-05 SILENT-RIG convention); venv deps (pandas, for the SPY/VIX
  CSV parsing) reach the script via --env PYTHONPATH, same pattern as
  Gamma_RightTailCapture and Gamma_CryptoTwinKeepalive.

  DISABLED AT REGISTRATION (this goal's operating rules -- workers never enable a
  scheduled task): this script registers the task then immediately calls
  Disable-ScheduledTask in the SAME run. Fable enables it after reviewing this goal's
  W3 item.

  Output: analysis/right-tail/wave-day-conditions.jsonl (rolling append, one row/day).
  Logs: automation/state/logs/run-cmd-hidden-<date>.log

  To verify after running: Get-ScheduledTask -TaskName Gamma_WaveDayConditions
    (State should read Disabled until Fable enables it)
  To test now (while disabled): Start-ScheduledTask -TaskName Gamma_WaveDayConditions
  Enable (Fable only, after reviewing W3): Enable-ScheduledTask -TaskName Gamma_WaveDayConditions
  REVERT (undo this install entirely): Unregister-ScheduledTask -TaskName "Gamma_WaveDayConditions" -Confirm:$false

  Per CLAUDE.md OP-3 ($0, pure Python) + the goal's CONFIG FREEZE OPERATING RULES
  (read-only instrument, no FROZEN_TRADING_PATH writes). Guard:
  backtest/tests/test_wave_day_conditions_2026_09_05.py.
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\wave_day_conditions.py"
$taskName     = "Gamma_WaveDayConditions"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# --date defaults to today (ET, via et_clock.et_today_str -- never Bash/system-local TZ)
# inside wave_day_conditions.py itself when omitted, so the fire command is a plain
# fixed argument list -- no fragile at-fire-time date injection needed.
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 07:20 MT = 09:20 ET, weekdays Mon-Fri -- before the 09:30 ET open.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:20"

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
    -Description ("Daily premarket wave-day-conditions instrument (GOAL-WAVE-DAY-" + `
    "CONDITIONS-2026-09-05 W3). Runs wave_day_conditions.py --date <today> -> " + `
    "analysis/right-tail/wave-day-conditions.jsonl. Read-only, INFORMATIONAL class; " + `
    "never touches a FROZEN_TRADING_PATH file. Fires 09:20 ET weekdays, before the " + `
    "09:30 open. Pure Python (backtest venv, pandas), `$0. Registered DISABLED -- " + `
    "workers never enable a scheduled task; Fable enables after review. Guard: " + `
    "backtest/tests/test_wave_day_conditions_2026_09_05.py.") `
    -Force | Out-Null

# DISABLE IMMEDIATELY -- workers never enable a scheduled task (this goal's operating
# rules). Fable reviews W3 and flips it on.
Disable-ScheduledTask -TaskName $taskName | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Output "OK: Registered $taskName for weekdays 07:20 MT (09:20 ET). State=$state."
Write-Output "    Action:   wscript.exe $wscriptArgs"
Write-Output "    Output:   analysis\right-tail\wave-day-conditions.jsonl"
Write-Output "    Enable:   Enable-ScheduledTask -TaskName $taskName  (Fable only)"
Write-Output "    Test now: Start-ScheduledTask -TaskName $taskName"
Write-Output "    Next run (while disabled, informational only): $($info.NextRunTime)"
