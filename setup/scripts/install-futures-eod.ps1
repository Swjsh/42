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

  2026-08-26 CONDUCTOR FIX -- MISSED-TRIGGER SELF-HEAL (3rd instance of the class fixed
  2026-08-25 on Gamma_MacroCalendar/Gamma_EarningsCalendar). Live incident: this task's
  single 14:12 MT daily trigger silently did not fire on 2026-08-25 (`Get-ScheduledTaskInfo`
  showed `LastRunTime` stuck on 2026-08-24, `NumberOfMissedRuns=1`, `NextRunTime` already
  advanced past 2026-08-25 to 2026-08-26) despite `.Repetition` being present-but-empty
  (`Duration`/`Interval` both null) -- the exact same no-repetition single-fire shape as the
  macro/earnings-calendar incident, just on a different producer. Detected via
  engine-health.json's `state_freshness` check reading `automation/state/futures/
  eod-summary.json` two calendar days stale. Fix: same self-heal pattern -- the primary
  `-Weekly -At "14:12"` trigger keeps firing once, but now also carries a 15-min-interval /
  30-min-duration repetition window (steals `.Repetition` from a throwaway `-Once` trigger,
  the only working PowerShell idiom -- direct assignment on a `-Weekly` trigger's null
  Repetition CIM instance throws PropertyNotFound). futures_eod.py is read-only and
  idempotent, so the extra fires change nothing on a normal day.
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
# -Weekly triggers come back with a null .Repetition CIM instance -- steal one from a
# throwaway -Once trigger built with the repetition params (same documented workaround as
# install-macro-calendar.ps1 / install-earnings-calendar.ps1; direct property assignment on
# the null instance throws PropertyNotFound). Self-heals a single missed fire within 30 min.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "14:12" -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

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
