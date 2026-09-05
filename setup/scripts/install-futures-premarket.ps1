#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_FuturesPremarket2 -- the deterministic futures premarket level +
  bias producer (READ-ONLY over bars, writes only its own two state files).

.DESCRIPTION
  THE GAP THIS CLOSES (queue item FUTURES-PREMARKET-PRODUCER-MISSING, filed 2026-08-29
  Fable futures parity audit): `Gamma_FuturesPremarket` has **NEVER FIRED** -- live Task
  Scheduler showed `LastRunTime=11/30/1999`, `LastResult=267011`
  (`SCHED_S_TASK_HAS_NOT_RUN`), Disabled since 2026-07-08 -- and its action is an LLM
  persona (`automation/prompts/futures-premarket.md`) that reads June-era corpse state
  (`automation/state/futures/position.json`/`account.json`/`risk.json`, all last written
  2026-06-17..07-14). Unlike `Gamma_FuturesEod` (which has a working successor,
  `Gamma_FuturesEod2`), Premarket had NO successor at all -- the futures lane had NO
  equivalent of the SPY engine's 08:30 ET level/bias prep.

  This registers `backtest/futures/futures_premarket.py` -- deterministic, $0, no LLM,
  no chart read. It reuses `futures_live_data.append_live` + `.load_series(mode="live")`
  (the SAME live bar spine `futures_trader_core.py`/`futures_heartbeat_core.py` already
  consume) to compute prior-RTH-day high/low/close, overnight GLOBEX high/low, and a
  MECHANICAL overnight-change-vs-prior-range bias (numeric confidence + explicit
  formula, zero narrative prose) for MES and MNQ, writing
  `automation/state/futures/key-levels.json` + `today-bias.json` in a schema family that
  shares its top-level shape (`schema_version`/`as_of`/`for_session`/`computed_from`)
  with the SPY producer. Never fabricates: any instrument the live cache cannot support
  (no bars, no prior session, no overnight bar yet, or a garbled out-of-band price) is
  written as `status: "DATA_MISSING"` with a `reason`, no numeric field guessed.

  NO CONSUMER YET -- neither futures execution lane reads these files today (both
  compute levels internally via `lib.levels._detect_from_history` on the live bar frame
  directly). This task is a producer only; wiring a consumer in is a deliberate lane
  BEHAVIOUR change, out of scope here. Treat the two files as visibility/journaling
  output until a consumer is built on purpose.

  WIRING PATTERN (flash-free, matches install-futures-eod.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo> --
      backtest\.venv\Scripts\pythonw.exe futures_premarket.py

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 08:35 ET -> 06:35 MT -- after the
  SPY-side `Gamma_Premarket` (08:30 ET) and well before the 09:30 ET open. NEVER pass an
  ET literal to -At.

  VERIFY:  Get-ScheduledTask -TaskName Gamma_FuturesPremarket2 | Get-ScheduledTaskInfo
  REVERT:  Unregister-ScheduledTask -TaskName "Gamma_FuturesPremarket2" -Confirm:$false

  MISSED-TRIGGER SELF-HEAL (same pattern as install-futures-eod.ps1's 2026-08-26 fix,
  itself cloned from install-macro-calendar.ps1/install-earnings-calendar.ps1): a single
  daily trigger has silently skipped a fire before (`NumberOfMissedRuns=1` with
  `NextRunTime` already advanced past the missed day) on this exact class of task. The
  primary `-Daily -At "06:35"` trigger keeps firing once, but also carries a
  15-min-interval / 30-min-duration repetition window so a single missed fire self-heals
  before the 09:30 ET open. futures_premarket.py is idempotent (same `--now` input ->
  identical output apart from `as_of`), so extra fires inside the window change nothing.

  RETIREMENT OF THE CORPSE (companion action, same session): the never-fired
  `Gamma_FuturesPremarket` task is unregistered separately (not by this script -- a
  decision made on purpose, not a side effect of installing this one, matching the
  `Gamma_FuturesEod`/`Gamma_FuturesEod2` precedent) and its persona file moved to
  `automation/prompts/_retired/futures-premarket.md`.
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script       = Join-Path $root "backtest\futures\futures_premarket.py"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_FuturesPremarket2"

foreach ($p in @($vbs, $pythonwVenv, $script, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# 06:35 MT = 08:35 ET weekdays -- after Gamma_Premarket (08:30 ET SPY side), before the
# 09:30 ET RTH open.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "06:35"
# -Weekly triggers come back with a null .Repetition CIM instance -- steal one from a
# throwaway -Once trigger built with the repetition params (documented workaround; direct
# property assignment on the null instance throws PropertyNotFound). Self-heals a single
# missed fire within 30 min, well before the 09:30 ET open.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "06:35" -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description ("Futures premarket level + bias producer (deterministic, `$0, no LLM). " + `
    "08:35 ET weekdays -- after Gamma_Premarket, before the 09:30 ET open. " + `
    "futures_premarket.py writes automation/state/futures/key-levels.json + today-bias.json " + `
    "for MES + MNQ: prior-RTH-day high/low/close, overnight GLOBEX high/low, prior RTH VWAP " + `
    "(when the feed carries volume), and a MECHANICAL bias (numeric confidence + explicit " + `
    "formula, no narrative prose) from overnight-change normalized by the prior day's own RTH " + `
    "range. Reuses futures_live_data's live bar spine -- the SAME data futures_trader_core.py/ " + `
    "futures_heartbeat_core.py read. Never fabricates: any instrument the cache cannot support " + `
    "is written status=DATA_MISSING with a reason, not a guessed number. NO execution lane " + `
    "reads these files yet -- producer only, by design (wiring a consumer is a separate lane " + `
    "behaviour change). Replaces the never-fired Gamma_FuturesPremarket LLM persona (retired " + `
    "to automation/prompts/_retired/futures-premarket.md). Built 2026-09-03. Queue: " + `
    "FUTURES-PREMARKET-PRODUCER-MISSING. Guard: " + `
    "backtest/tests/test_futures_premarket_2026_09_03.py. REVERT: Unregister-ScheduledTask " + `
    "-TaskName 'Gamma_FuturesPremarket2' -Confirm:`$false") | Out-Null

Write-Host "Registered $taskName"
$info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
if ($info -and $info.NextRunTime) {
    Write-Host ("  NextRun ET: {0}" -f ([System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)).ToString("yyyy-MM-dd HH:mm"))
}
(Get-ScheduledTask -TaskName $taskName).State
