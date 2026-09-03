#requires -Version 5.1
<#
.SYNOPSIS
  Re-register Gamma_Premarket with a self-heal Repetition window (GAMMA-PREMARKET-SELF-HEAL-
  WINDOW, MED, queue.md, filed as the last single-daily-fire trading-critical producer with
  no retry window).

.DESCRIPTION
  Gamma_Premarket (08:30 ET, writes automation/state/today-bias.json + circuit-breaker.json,
  seeds journal/{today}.md) was the last remaining single-daily-fire producer feeding a
  freshness consumer WITHOUT a retry window -- a bare CalendarTrigger, no Repetition,
  registered by a shared harden-tasks.ps1 / fix-trading-tasks.ps1 pass with no isolated
  installer of its own. This is the SAME silent-single-fire class already closed on
  Gamma_MacroCalendar / Gamma_EarningsCalendar / Gamma_FuturesEod2 (2026-08-25/26) and
  Gamma_PremarketReadiness / Gamma_Tp1R50ForwardShadow (2026-09-03): a correctly-registered
  recurring trigger can still silently skip one day's fire (Windows gives no forensic trail
  why, StartWhenAvailable does not catch it, Microsoft-Windows-TaskScheduler/Operational is
  disabled non-elevated on this box) -- the fix is a bounded self-heal repetition window
  (every 15 min for 30 min after the primary fire) so a single missed trigger self-heals
  within 30 min instead of the engine opening the day on a stale premarket.

  IDEMPOTENCY (verified by reading setup/scripts/run-premarket.ps1 + automation/prompts/
  premarket.md before adding this trigger, GAMMA-PREMARKET-SELF-HEAL-WINDOW step 2): the
  script was NOT idempotent across separate invocations -- Invoke-PremarketAttempt spends a
  fresh $3 LLM budget call every run, premarket.md Step 4 fully REWRITES today-bias.json
  (not a merge) and Step 6 CREATEs journal/{today}.md (a full overwrite, not an append). An
  unconditional 08:45 re-fire after a clean 08:30 success would waste budget and could stomp
  the good bias/journal with a second LLM pass. Fixed with the smallest diff: a done-marker
  skip at the top of run-premarket.ps1 (today-bias.json dated today AND file mtime ET >=
  08:00 -> log + exit 0) so the self-heal window only ever recovers a genuine miss, never
  re-runs a already-successful morning. Guard: backtest/tests/
  test_run_premarket_done_marker_skip_2026_09_03.py.

  EXEC ACTION -- IDENTICAL to the live task exported before this change (Export-ScheduledTask
  -TaskName Gamma_Premarket, saved this session): same interpreter chain (wscript.exe ->
  run_exe_hidden.vbs -> system pythonw.exe -> run_ps1_hidden.py -> run-premarket.ps1), same
  arguments, no WorkingDirectory (the export carried none -- run-premarket.ps1 sources
  $PSScriptRoot-relative paths itself via _shared.ps1, it does not need an external cwd).

  TZ RULE: this rig runs Mountain Time (ET = local + 2h, year-round -- both zones share the
  same DST calendar). 08:30 ET -> 06:30 MT. The exported live trigger uses a bare
  <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay> CalendarTrigger (literal
  DAILY, not weekday-restricted at the OS level -- Test-WeekDay inside run-premarket.ps1 is
  the weekday filter), so this installer uses -Daily (not -Weekly) to reproduce that exact
  trigger shape -- a -Weekly Mon-Fri trigger would serialize as <ScheduleByWeek> and diff
  more than just the Repetition block.

  To verify after running:
    Get-ScheduledTask -TaskName Gamma_Premarket | Get-ScheduledTaskInfo
  REVERT (restore the pre-change single-fire trigger, no Repetition):
    Export-ScheduledTask -TaskName Gamma_Premarket   # compare against the saved before-XML
    -- or simply re-run this repo's original harden-tasks.ps1 / fix-trading-tasks.ps1 pass,
    or `git revert` this commit and re-run this installer against the reverted state.
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPs1Hidden = Join-Path $root "setup\scripts\run_ps1_hidden.py"
$script       = Join-Path $root "setup\scripts\run-premarket.ps1"
$taskName     = "Gamma_Premarket"
$atMT         = "06:30"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

foreach ($p in @($vbs, $sysPythonw, $runPs1Hidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# IDENTICAL exec action to the exported live XML: wscript -> run_exe_hidden.vbs ->
# system pythonw.exe -> run_ps1_hidden.py -> run-premarket.ps1. No -WorkingDirectory
# (the export carried none).
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runPs1Hidden`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs

# -Daily (not -Weekly) to reproduce the exported live trigger's bare
# <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay> shape exactly -- weekday
# filtering is done INSIDE run-premarket.ps1 (Test-WeekDay), not by the OS trigger.
# -Daily triggers come back with a null .Repetition CIM instance -- steal one from a
# throwaway -Once trigger built with the repetition params (documented PS workaround, same
# idiom as install-premarket-readiness.ps1 / install-tp1-r50-forward-shadow.ps1). Self-heals
# a single missed fire within 30 min. (StartBoundary's DATE component is re-registration day,
# not the original 2026-05-05 -- immaterial to a DAILY recurrence; only the time-of-day and
# DaysInterval matter, both preserved.)
$trigger = New-ScheduledTaskTrigger -Daily -At $atMT
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $atMT `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

# Settings reconstructed to match the exported live <Settings> block: DisallowStartIfOn
# Batteries=false, StopIfGoingOnBatteries=false, ExecutionTimeLimit=PT14M, Hidden=true,
# MultipleInstancesPolicy=IgnoreNew, RestartOnFailure Count=1/Interval=PT2M,
# StartWhenAvailable=true, WakeToRun=true, IdleSettings.StopOnIdleEnd=false (the module
# default is true -- -DontStopOnIdleEnd is required or this one flips silently, verified via
# a first Export-ScheduledTask diff this session).
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 14) `
    -Hidden `
    -MultipleInstances IgnoreNew `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -StartWhenAvailable `
    -WakeToRun `
    -DontStopOnIdleEnd

# Principal reconstructed to match the export: LogonType InteractiveToken (the
# New-ScheduledTaskPrincipal "Interactive" value serializes to InteractiveToken), current
# user, no explicit RunLevel (the export carried none -> default LeastPrivilege/Limited).
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Gamma: Pre-market routine (level audit, today-bias.json, falsifiable " + `
    "hypothesis, draw levels, seed journal)") `
    -Force | Out-Null
# NOTE: Description is left byte-identical to the pre-change export on purpose, so an
# Export-ScheduledTask diff against the pre-change XML shows ONLY the new Repetition block
# (GAMMA-PREMARKET-SELF-HEAL-WINDOW step 4's explicit verification target). Full rationale
# for the self-heal window + the idempotency fix lives in this file's own .SYNOPSIS/
# .DESCRIPTION comment block above, and in run-premarket.ps1's done-marker comment.

Write-Host "Registered $taskName ($atMT MT = 08:30 ET, daily; weekday filter is in-script)"
$info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
if ($info -and $info.NextRunTime) {
    $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
    Write-Host ("  NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
} else {
    Write-Host "  NextRun ET: (none / on-demand)"
}
Write-Host ""
Write-Host "Verify with: Get-ScheduledTask -TaskName Gamma_Premarket | Get-ScheduledTaskInfo"
