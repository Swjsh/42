#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_ConductorRTH scheduled task -- the bounded market-hours verify-and-flag tick.

.DESCRIPTION
  Registers Gamma_ConductorRTH: every 30 min, 09:30-15:55 ET, WEEKDAYS ONLY. Each fire runs
  a small, low-effort, ~10-tool-call read-and-flag pass (STAGE 0-RTH in conductor.md) --
  verify engine-health.json + self-check-last.json + the fill funnel, and if clean, log
  quietly; if RED/anomalous, flag to STATUS.md + Discord and queue a fix for the next
  after-hours/weekend fire. It NEVER fans out an agent, NEVER ships a change, NEVER places
  an order. This is the ONE J-authorized exception (2026-07-18) to "the conductor never
  runs during market hours" -- sized specifically so it cannot repeat the L54 heartbeat-
  starving incident (tiny budget cap, low effort, short timeout; see run-conductor-rth.ps1).

  Uses a WEEKLY trigger (Mon-Fri only) with a 30-min intra-day repetition, so it recurs
  correctly every week (unlike a bare -Once trigger, which goes dark after one day --
  project memory: project_scheduled_task_onetime_trigger_dark).

  TZ NOTE: rig runs Mountain time; this script computes the live ET->local offset at
  install time and anchors the trigger to local clock so "09:30 ET" fires at the correct
  Mountain wall-clock. Re-run after a DST shift to re-anchor.

  Wired via OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-conductor-rth.ps1 -> claude --print
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_ConductorRTH"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) { Write-Error "System pythonw not found at $pythonw"; exit 1 }

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-conductor-rth.ps1"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

# --- ET -> local offset (rig is Mountain; honor DST) --------------------------
$etZone = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
$nowUtc = [DateTime]::UtcNow
$etNow = [TimeZoneInfo]::ConvertTimeFromUtc($nowUtc, $etZone)
$localNow = [DateTime]::Now
$etMinusLocalHours = [math]::Round(($etNow - $localNow).TotalHours)

# 09:30 ET start. Local start = 09:30 - (ET-local delta). Comfortably mid-morning
# regardless of a 1-3h offset -- no midnight-boundary weekday ambiguity here (unlike
# the weekend installer, which anchors near local midnight and needs a wider day margin).
$startHourEt = 9
$startMinEt = 30
$startTotalMinLocal = (($startHourEt * 60 + $startMinEt) - ($etMinusLocalHours * 60))
$startTotalMinLocal = (($startTotalMinLocal % 1440) + 1440) % 1440
$startHourLocal = [math]::Floor($startTotalMinLocal / 60)
$startMinLocal = $startTotalMinLocal % 60

$startLocal = (Get-Date).Date.AddHours($startHourLocal).AddMinutes($startMinLocal)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# Weekly (Mon-Fri) anchor + 30-min repetition across the RTH window only. RTH window is
# 09:30-15:55 ET = 6h25m; a fire at +6h00m (15:30 ET) is the last one inside that duration,
# which is correct (a 15:55 fire would be pointless -- right at the market-hours gate edge).
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At $startLocal
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $startLocal `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 25)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("Gamma Conductor RTH_LIGHT -- bounded market-hours verify-and-flag tick (J directive 2026-07-18). Every 30 min, 09:30-15:55 ET weekdays. Reads engine-health.json + self-check-last.json + fill_funnel.py; flags STATUS.md/Discord on anomaly, NEVER fans out an agent, NEVER ships, NEVER places an order. Sonnet, low effort, `$0.50 cap. Prompt: automation/prompts/conductor.md (MODE=RTH_LIGHT via Task:conductor-rth). Kill-switch: Disable-ScheduledTask Gamma_ConductorRTH.") | Out-Null

Write-Output ("OK: Registered $TaskName")
Write-Output ("    Cadence: every 30 min, 09:30-15:55 ET weekdays (local start " + $startLocal.ToString("HH:mm") + ", ET-local delta " + $etMinusLocalHours + "h, 13 fires/day)")
Write-Output ("    Gate:    weekday RTH ONLY -- wrapper re-checks (defense in depth)")
Write-Output ("    Chain:   wscript -> run_exe_hidden.vbs -> sys-pythonw -> run_ps1_hidden.py -> run-conductor-rth.ps1 -> claude --print (sonnet, low effort)")
Write-Output ("    Cost:    ~`$0.50/fire cap (bounded ~10-tool-call pass; realistically far less)")
Write-Output ("    Verify:  Get-ScheduledTask -TaskName Gamma_ConductorRTH | Get-ScheduledTaskInfo")
Write-Output ("    Re-run after a DST shift to re-anchor the local start hour.")
