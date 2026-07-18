#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_FuturesEdge3Sim -- the own-book SIM lane for EDGE #3 (MES-leads->MNQ-lags
  divergence catch-up, automation/state/fleet/edge3_mesmnq_div.py FROZEN_CONFIG). The frozen
  cell (OOS +$71.46/tr, n=118, 8/8 gates) sat DORMANT since 2026-06-21 behind enabled=False +
  a Trading Technologies sandbox credential that was never wired (docs/futures/ never existed).
  Alpaca does not support futures (verified live 2026-07-18: asset_class="us_future" returns
  zero assets; Alpaca's documented AssetClass enum is {us_equity, us_option, crypto} only) --
  no real-broker paper path exists, so this task runs the honest equivalent: real MES/MNQ
  quotes (yfinance ES=F/NQ=F), the REAL frozen detector, a SIM fill ledger, every row labeled
  sim_fill_vs_real_quote. No broker, no credentials, no real orders anywhere.

  PURPOSE: every 5 minutes during RTH (09:30-16:00 ET -- the frozen edge is RTH-scoped by its
  own construction, b4.RTH_OPEN/RTH_CLOSE; polling the overnight Globex session would never
  change a decision the detector itself ignores), futures_edge3_sim.py --once fetches live
  ES=F/NQ=F 5m bars, calls edge3_mesmnq_div.signal_for_tick (byte-identical frozen threshold/
  persistence), manages any open SIM position (ATR chandelier + chart-stop, EOD-flat), and
  appends every lifecycle event to automation/state/futures/edge3-sim-fills.jsonl. Falsifi-
  cation rail: once >=20 closed round trips exist, edge3-sim-progress.json compares mean pnl
  to the validated $71.46/tr and flags INVESTIGATE_QUOTE_QUALITY on a material shortfall.

  WIRING PATTERN (flash-free, matches install-futures-mirror.ps1 exactly):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> futures_edge3_sim.py --once
  Runs on the BACKTEST venv (pandas + yfinance) -- automatically reaper-exempt, since
  `backtest\.venv` is already in _shared.ps1's EXEMPT_DAEMONS substring list.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 09:30 ET -> 07:30 MT. NEVER pass an ET
  literal to -At. A REPEATING trigger (Once + 5-min RepetitionInterval + RepetitionDuration
  spanning the window), never a one-shot TimeTrigger (goes dark the next day --
  project_scheduled_task_onetime_trigger_dark).

  To verify after running: Get-ScheduledTask -TaskName Gamma_FuturesEdge3Sim | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_FuturesEdge3Sim" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root        = "C:\Users\jackw\Desktop\42"
$vbs         = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script      = Join-Path $root "setup\scripts\futures_edge3_sim.py"
$etz         = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName    = "Gamma_FuturesEdge3Sim"

foreach ($p in @($vbs, $pythonwVenv, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

function Show-NextET {
    param([string]$Name)
    $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction SilentlyContinue
    if ($info -and $info.NextRunTime) {
        $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
        Write-Host ("  NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
    } else {
        Write-Host "  NextRun ET: (none / on-demand)"
    }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> backtest venv pythonw -> futures_edge3_sim.py --once
$wscriptArgs = "//nologo `"$vbs`" `"$pythonwVenv`" `"$script`" --once"

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 07:30 MT = 09:30 ET start; repeat every 5 min for 6h30m -> covers 09:30-16:00 ET (RTH only --
# the frozen edge never acts outside RTH, so polling past 16:00 buys nothing).
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
    -Description ("EDGE #3 (MES->MNQ divergence) own-book SIM lane -- the TT-credential " + `
    "path was retired 2026-07-18 (never wired; Alpaca confirmed no futures support). Every " + `
    "5 min, 09:30-16:00 ET weekdays (RTH only -- the frozen edge is RTH-scoped by " + `
    "construction). futures_edge3_sim.py --once: fetches live ES=F/NQ=F quotes, calls the " + `
    "REAL frozen edge3_mesmnq_div.signal_for_tick detector, manages the ATR-chandelier/" + `
    "chart-stop SIM position, flattens at RTH close, logs every lifecycle event to " + `
    "automation/state/futures/edge3-sim-fills.jsonl (fidelity=sim_fill_vs_real_quote on " + `
    "every row). Places NOTHING real, no broker, no creds. Fail-open (exits 0 always, logs " + `
    "to automation/state/logs/futures-edge3-sim-*.log). Falsification rail: >=20 closed " + `
    "round trips -> edge3-sim-progress.json compares mean pnl to the validated $71.46/tr.") `
    -Force | Out-Null

Write-Host "Registered $taskName (07:30 MT = 09:30 ET start, every 5 min for 6h30m, Mon-Fri)"
Show-NextET $taskName
Write-Host ""
Write-Host "EDGE #3 own-book SIM lane wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_FuturesEdge3Sim | Get-ScheduledTaskInfo"
