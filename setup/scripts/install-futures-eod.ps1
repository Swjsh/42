#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_FuturesEod -- the futures session review (read-only).

  PURPOSE: 16:12 ET weekdays, just after the futures lane's last RTH tick,
  futures_eod.py grades the session and writes analysis/futures-eod/<date>.md plus
  automation/state/futures/eod-summary.json.

  THE HEADLINE METRIC IS TICK COVERAGE, deliberately: did the lane actually fire the
  ~78 ticks it was scheduled to? Every other number on the digest is conditional on the
  engine having been awake, and a lane that quietly stops ticking otherwise produces a
  PERFECT-looking review -- zero trades, zero errors, zero rule breaks. "No trades today"
  and "the engine was dead today" must never render identically. A DARK or RED coverage
  verdict forces the whole digest RED regardless of how clean the rest looks.

  Also grades: the signal funnel (seen -> qualified -> entered, with the RAIL that
  rejected each drop), closed round trips from ONE fill class (never mixed), and a
  POST-HOC rule audit run independently of the pre-trade gate -- because a bypassed or
  mis-wired gate is invisible to a check that only runs inside that same gate.

  READ-ONLY. Places nothing, cancels nothing, modifies no trading state.

  WIRING PATTERN (flash-free, matches install-futures-trader.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo> --
      backtest\.venv\Scripts\pythonw.exe futures_eod.py

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 16:12 ET -> 14:12 MT.
  NEVER pass an ET literal to -At.

  VERIFY:  Get-ScheduledTask -TaskName Gamma_FuturesEod2 | Get-ScheduledTaskInfo
  REVERT:  Unregister-ScheduledTask -TaskName "Gamma_FuturesEod2" -Confirm:$false

  NAME NOTE: registered as Gamma_FuturesEod2 because a DISABLED June-era `Gamma_FuturesEod`
  (retired LLM-wrapper architecture) still occupies the original name. Deliberately not
  deleted here -- removing another era's task is a decision to make on purpose, not a side
  effect of installing this one.
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script       = Join-Path $root "backtest\futures\futures_eod.py"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_FuturesEod2"

foreach ($p in @($vbs, $pythonwVenv, $script, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonwVenv`" `"$script`""

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# 14:12 MT = 16:12 ET, just after the lane's final RTH tick at 16:00 ET.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:12"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description ("Futures session review (READ-ONLY). 16:12 ET weekdays. futures_eod.py grades " + `
    "the day and writes analysis/futures-eod/<date>.md + automation/state/futures/eod-summary.json. " + `
    "HEADLINE METRIC = TICK COVERAGE: did Gamma_FuturesTrader actually fire its ~78 scheduled " + `
    "ticks? A dark lane otherwise produces a perfect-looking digest (0 trades, 0 errors, 0 rule " + `
    "breaks), so DARK/RED coverage forces the whole digest RED -- 'no trades' and 'no engine' must " + `
    "never render identically. Also grades the signal funnel with per-rail rejection counts, closed " + `
    "round trips from ONE fill class (SIMULATED and BROKER are never mixed), and a POST-HOC rule " + `
    "audit independent of the pre-trade gate (a bypassed gate is invisible to a check inside that " + `
    "same gate). Places nothing, modifies no trading state. Built 2026-08-09. Doc: " + `
    "markdown/futures/AUTONOMOUS-FUTURES-LANE.md. REVERT: Unregister-ScheduledTask -TaskName " + `
    "'Gamma_FuturesEod2' -Confirm:`$false") | Out-Null

Write-Host "Registered $taskName"
$info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
if ($info -and $info.NextRunTime) {
    Write-Host ("  NextRun ET: {0}" -f ([System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)).ToString("yyyy-MM-dd HH:mm"))
}
(Get-ScheduledTask -TaskName $taskName).State
