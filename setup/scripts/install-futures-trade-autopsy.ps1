#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_FuturesTradeAutopsy -- the futures-side post-trade autopsy (read-only).

  PURPOSE: queue.md FUTURES-LANE-WIRING-2 (a), folding FUTURES-POST-TRADE-AUTOPSY-MISSING
  (queue.md, filed 2026-08-29 Fable futures parity audit) closed. `futures_trade_autopsy.py`
  was built and verified working (see its own module docstring) but deliberately left
  UNSCHEDULED -- "no scheduled task tonight -- registration is off-limits" -- with the
  cadence spec written into the file for "whoever wires the scheduled task next": right
  after Gamma_FuturesEod2 (16:12 ET), same 5-6pm ET after-hours window, $0 marginal cost.
  This is that wiring, tonight.

  WHAT IT DOES: reads journal/futures/trades.csv (the ONE canonical closed-round-trip
  ledger), reports per-fills-class (SIMULATED/BROKER/UNKNOWN, never aggregated) entry/exit,
  exit_reason, $pnl (straight from the ledger, never recomputed), and best-effort MAE/MFE
  from the lane's own live 5m bar cache. Descriptive only -- mirrors winner_autopsy.py's
  own small-n discipline: writes NO hypothesis-queue.jsonl entry, appends to NOTHING else.
  Writes analysis/futures/autopsy-latest.md + autopsy-latest.json (both OVERWRITTEN each
  run, not appended -- same "one artifact per date" shape as the SPY autopsies).

  READ-ONLY. Places nothing, cancels nothing, modifies no trading state.

  WIRING PATTERN (flash-free, IDENTICAL to install-futures-eod.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo> --
      backtest\.venv\Scripts\pythonw.exe futures\futures_trade_autopsy.py

  TIMING: Gamma_FuturesEod2 fires 14:12 MT (16:12 ET) weekdays -- confirmed live via
  Get-ScheduledTask before writing this script (StartBoundary 2026-08-25T14:12:00-06:00,
  DaysOfWeek weekday mask, LastTaskResult 0). This task fires 10 minutes later: 14:22 MT
  (16:22 ET) weekdays, well clear of Eod2's own <5min ExecutionTimeLimit.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 16:22 ET -> 14:22 MT.
  NEVER pass an ET literal to -At.

  MISSED-TRIGGER SELF-HEAL: same 15-min-interval/30-min-duration repetition window shipped
  tonight across every single-fire daily trigger in this rig (2026-09-03
  SINGLE-FIRE-TRIGGER-BLANKET-AUDIT, e.g. Gamma_FuturesEod2/Gamma_TrendCacheProducer) --
  built in from day one here rather than retrofitted later. futures_trade_autopsy.py is
  read-only and idempotent (each run OVERWRITES the same two output files), so an extra
  self-heal fire changes nothing on a normal day.

  VERIFY:  Get-ScheduledTask -TaskName Gamma_FuturesTradeAutopsy | Get-ScheduledTaskInfo
  REVERT:  Unregister-ScheduledTask -TaskName "Gamma_FuturesTradeAutopsy" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script       = Join-Path $root "backtest\futures\futures_trade_autopsy.py"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_FuturesTradeAutopsy"

foreach ($p in @($vbs, $pythonwVenv, $script, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonwVenv`" `"$script`""

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# 14:22 MT = 16:22 ET, 10 minutes after Gamma_FuturesEod2's 16:12 ET fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:22"
# -Weekly triggers come back with a null .Repetition CIM instance -- steal one from a
# throwaway -Once trigger built with the repetition params (same documented workaround as
# install-futures-eod.ps1 / install-macro-calendar.ps1). Self-heals a single missed fire
# within 30 min.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "14:22" -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description ("Futures post-trade autopsy (READ-ONLY, descriptive only). 16:22 ET weekdays " + `
    "-- 10 min after Gamma_FuturesEod2. futures_trade_autopsy.py reads journal/futures/trades.csv " + `
    "and writes analysis/futures/autopsy-latest.md + .json: per-fills-class (SIMULATED/BROKER/" + `
    "UNKNOWN, never aggregated) entry/exit, exit_reason, `$pnl (straight from the ledger), best-" + `
    "effort MAE/MFE from the live bar cache. Mirrors winner_autopsy.py's small-n discipline -- " + `
    "no hypothesis-queue.jsonl entry, appends to nothing else. Places nothing, modifies no " + `
    "trading state. Closes queue.md FUTURES-POST-TRADE-AUTOPSY-MISSING / FUTURES-LANE-WIRING-2 " + `
    "(a). REVERT: Unregister-ScheduledTask -TaskName 'Gamma_FuturesTradeAutopsy' -Confirm:`$false") | Out-Null

Write-Host "Registered $taskName"
$info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
if ($info -and $info.NextRunTime) {
    Write-Host ("  NextRun ET: {0}" -f ([System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)).ToString("yyyy-MM-dd HH:mm"))
}
(Get-ScheduledTask -TaskName $taskName).State
