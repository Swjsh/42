#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_ConductorWeekend scheduled task -- the full loop, weekend daytime cadence.

.DESCRIPTION
  Registers Gamma_ConductorWeekend: every 2h, Saturday+Sunday, all day. Runs the full
  STAGE 0->5 conductor loop (same as the after-hours Gamma_Conductor) with the WEEKEND
  nudge in conductor.md's STAGE 1 (crypto-twin + Kitchen checked first). J directive
  2026-07-18: "crypto weekends" -- weekend DAYTIME had zero conductor coverage before this
  (the existing Gamma_Conductor's 18:00-07:00 ET window only ever covers overnight hours,
  even on a Saturday/Sunday).

  DAY-BOUNDARY NOTE: this trigger anchors near LOCAL midnight, and Windows' Weekly
  DaysOfWeek evaluates the LOCAL calendar day -- but the intent is ET Saturday/Sunday
  coverage, and Mountain-vs-ET's 1-3h offset means "ET Saturday 00:00" can fall on the
  LOCAL Friday evening. Rather than fight that ambiguity with exact-hour math, this
  installer deliberately triggers on a WIDER local day margin (Fri/Sat/Sun/Mon) and lets
  the wrapper's own Test-WeekDay(ET) gate (run-conductor-weekend.ps1) be the actual
  authority -- any fire that isn't genuinely ET Saturday/Sunday SKIPs for `$0. Same
  defense-in-depth posture used everywhere else in this task family.

  Uses a WEEKLY trigger (not a bare -Once) so it recurs correctly every week (project
  memory: project_scheduled_task_onetime_trigger_dark).

  Wired via OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-conductor-weekend.ps1 -> claude --print
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_ConductorWeekend"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) { Write-Error "System pythonw not found at $pythonw"; exit 1 }

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-conductor-weekend.ps1"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# Local midnight anchor, Fri/Sat/Sun/Mon margin (see day-boundary note above), 2h
# repetition across ~24h so a real ET Saturday/Sunday gets full-day coverage regardless
# of exactly which local day the ET-midnight instant lands on.
$startLocal = (Get-Date).Date  # local 00:00 today
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Friday,Saturday,Sunday,Monday `
    -At $startLocal
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $startLocal `
    -RepetitionInterval (New-TimeSpan -Hours 2) `
    -RepetitionDuration (New-TimeSpan -Hours 23 -Minutes 59)).Repetition

# ExecutionTimeLimit MUST clear the inner Invoke-Claude TimeoutSec (600s=10min) with real
# headroom, or Task Scheduler hard-kills the whole process tree (wscript root + all
# descendants) BEFORE the inner script's own timeout/cleanup/logging can run -- a totally
# silent death (no log line at ANY layer). Found + fixed live during the 2026-07-18
# verification fire: this installer originally set 12 min (only 2 min of margin over the
# 10-min inner budget + ~1 min of L181/gauntlet-hook preamble); the fire silently died with
# zero log output at the exact time window consistent with a 12-min hard kill. The PROVEN
# live Gamma_Conductor task (84 successful fires) actually runs at 15 min (PT15M) -- its
# install script's stale "12" comment had drifted from a live Set-ScheduledTask correction
# that was never backported to source. 16 min here matches that proven margin with one
# extra minute for the weekend wrapper's slightly heavier preamble.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 16)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("Gamma Conductor WEEKEND -- full 'Gamma drives' loop, weekend daytime cadence (J directive 2026-07-18: 'crypto weekends'). Every 2h, Saturday+Sunday all day (triggers on a Fri/Sat/Sun/Mon local margin; the wrapper's own ET weekday gate is the real authority, non-weekend fires SKIP for `$0). Same STAGE 0->5 loop as Gamma_Conductor, WEEKEND nudge checks crypto-twin health + Kitchen first. Sonnet, high effort, `$10 cap. Prompt: automation/prompts/conductor.md (MODE=WEEKEND via Task:conductor-weekend). Kill-switch: Disable-ScheduledTask Gamma_ConductorWeekend.") | Out-Null

Write-Output ("OK: Registered $TaskName")
Write-Output ("    Cadence: every 2h, Sat+Sun all day (local trigger days Fri/Sat/Sun/Mon margin; wrapper gate is authoritative)")
Write-Output ("    Gate:    ET weekend ONLY -- wrapper (run-conductor-weekend.ps1) Test-WeekDay + RTH re-check")
Write-Output ("    Chain:   wscript -> run_exe_hidden.vbs -> sys-pythonw -> run_ps1_hidden.py -> run-conductor-weekend.ps1 -> claude --print (sonnet, high effort)")
Write-Output ("    Cost:    ~`$10/fire cap (full loop, bounded; realistically `$1-3 typical per conductor-outcomes.jsonl history)")
Write-Output ("    Verify:  Get-ScheduledTask -TaskName Gamma_ConductorWeekend | Get-ScheduledTaskInfo")
