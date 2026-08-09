#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_FuturesTrader -- the autonomous futures intraday lane (SIM fills).

  PURPOSE: every 5 minutes during RTH (09:30-16:00 ET) weekdays, futures_trader_runner.py
  runs ONE see -> decide -> act tick on MES via futures_trader_core:
    SEE     refresh the live 5m bar cache (yfinance MES=F) + never-blind staleness verdict
    DECIDE  the validated watcher fleet -> should_take_v3 -> the DOLLAR risk rails (WS-F7)
    ACT     place/manage through the configured broker backend
  It writes a liveness beacon on EVERY fire, journals every decision, and manages open
  positions before it ever considers a new one.

  BACKEND: `fillsim` (the local gap-fill-correct paper exchange) unless FUTURES_BROKER
  says otherwise. It touches NO external account and NO credentials -- which is exactly
  why this lane can start while the broker/venue question is still open
  (analysis/deep-research/FUTURES-BROKER-RESEARCH-2026-08-09.md). Fills are SIMULATED:
  mechanism evidence, never edge evidence. Switching to a real venue is an env var, not
  a code change, and live money additionally requires J (OP-0 #1) plus a funded venue.

  CADENCE: 5 minutes matches the 5m bar the strategy reads -- a 1-minute cadence would
  re-evaluate the same unchanged bar four times and buy nothing but Yahoo requests.

  WIRING PATTERN (flash-free, matches install-ssr-shadow.ps1 / install-futures-mirror.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo> --
      backtest\.venv\Scripts\pythonw.exe futures_trader_runner.py
  Runs on the BACKTEST venv (pandas + yfinance live there, not in system Python).

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 09:30 ET -> 07:30 MT,
  16:00 ET -> 14:00 MT. NEVER pass an ET literal to -At. A REPEATING trigger (Once +
  5-min RepetitionInterval + RepetitionDuration spanning the window), never a one-shot
  TimeTrigger (which goes dark the next day -- project_scheduled_task_onetime_trigger_dark).

  VERIFY:  Get-ScheduledTask -TaskName Gamma_FuturesTrader | Get-ScheduledTaskInfo
  REVERT:  Unregister-ScheduledTask -TaskName "Gamma_FuturesTrader" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script       = Join-Path $root "setup\scripts\futures_trader_runner.py"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_FuturesTrader"

foreach ($p in @($vbs, $pythonwVenv, $script, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonwVenv`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 07:30 MT = 09:30 ET; repeat every 5 min for 6h30m -> covers 09:30-16:00 ET.
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "07:30"
$rep = (New-ScheduledTaskTrigger -Once -At "07:30" `
        -RepetitionInterval (New-TimeSpan -Minutes 5) `
        -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 30)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("Autonomous futures intraday lane (MES, SIMULATED fills). Every 5 min " + `
    "09:30-16:00 ET weekdays. futures_trader_runner.py -> futures_trader_core.run_tick: " + `
    "refreshes the live 5m MES=F bar cache with a never-blind staleness verdict, runs the " + `
    "validated watcher fleet + should_take_v3, gates every entry through the DOLLAR risk " + `
    "rails (1 MES cap, -$100/trade, -$200/session, $1,600 floor, liquidation-distance " + `
    "assertion, RTH-only, rollover block), manages exits BEFORE considering entries, and " + `
    "force-flattens before the 17:00 ET settlement stop. Backend 'fillsim' = local paper " + `
    "exchange: no broker, no credentials, no real money. Fills are SIMULATED = mechanism " + `
    "evidence, NEVER edge evidence. Writes a liveness beacon every fire to " + `
    "automation/state/futures/trader/heartbeat.json; journals to journal/futures/. " + `
    "Fail-open (always exits 0; failures land in trader/runner-failures.jsonl). " + `
    "Built 2026-08-09 per FUTURES-FIRST-PLAN WS-F1/F3/F7.") | Out-Null

Write-Host "Registered $taskName"
$info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
if ($info -and $info.NextRunTime) {
    $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
    Write-Host ("  NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
}
(Get-ScheduledTask -TaskName $taskName).State
