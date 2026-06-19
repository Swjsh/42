#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_Conductor scheduled task -- the "Gamma drives" engine.
  Hourly during the after-hours window 18:00-07:00 ET (NEVER during RTH).

.DESCRIPTION
  Registers Gamma_Conductor: each fire runs ONE bounded conductor tick
  (run-conductor.ps1 -> conductor.md prompt, opus). Read engine-health + STATUS
  + the prioritized queue, pick the single highest-value ready item, fan out the
  right specialist persona via the Agent tool, validate (gym/tests), SHIP only if
  it clears the auto-ratify gate ELSE flag J via Discord, update STATUS + queue.

  SAFETY (the whole point -- see conductor.md "SAFETY RAILS"):
    * AFTER-HOURS ONLY. Triggers are 18:00..07:00 ET (no fire 09:30-15:55 ET).
      The wrapper AND the prompt both re-gate on market hours -- defense in depth
      against starving Gamma_Heartbeat on the shared Max rate-limit pool (L54).
    * FAIL-OPEN. The conductor never kills/blocks J's session (the OP-32 scar).
    * ONE BOUNDED TASK PER FIRE. No runaway loop; the next fire continues.
    * PROPOSE-AND-PING-J for any doctrine/params/order change -- never auto-apply.

  TZ NOTE (project memory: scheduled_task_tz -- rig is Mountain time, tasks are
  scheduled at ET-converted-to-LOCAL). This script computes the live ET->local
  offset at install time and anchors the trigger to local clock so 18:00 ET fires
  at the correct Mountain wall-clock. Re-run after a DST shift to re-anchor (same
  as the other ET-windowed installers on this box).

  Wired via OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-conductor.ps1 -> claude --print

  NOTE: this script REGISTERS the task; J / the installer runs it deliberately
  (like the health beacon). It does not start a live fire itself. Wire-don't-auto-enable.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_Conductor"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-conductor.ps1"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

# --- ET -> local offset (rig is Mountain; honor DST) --------------------------
# Compute the current ET-vs-local hour delta so "18:00 ET" maps to the right
# local wall-clock start. Both zones observe US DST so the delta is stable
# (ET is 2h ahead of MT), but we compute it rather than hardcode 2.
$etZone = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
$nowUtc = [DateTime]::UtcNow
$etNow = [TimeZoneInfo]::ConvertTimeFromUtc($nowUtc, $etZone)
$localNow = [DateTime]::Now
# Hours that LOCAL is behind ET (e.g. Mountain = 2). Round to whole hours.
$etMinusLocalHours = [math]::Round(($etNow - $localNow).TotalHours)

# After-hours window: 18:00 ET start. Local start hour = 18 - (ET-local delta).
$startHourEt = 18
$startHourLocal = (($startHourEt - $etMinusLocalHours) % 24 + 24) % 24

# Window length 18:00 ET -> 07:00 ET inclusive = 14 hourly fires (18,19,...,23,0..7).
$windowHours = 14

$startLocal = (Get-Date).Date.AddHours($startHourLocal)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# Daily anchor + hourly repetition across the after-hours window only.
$trigger = New-ScheduledTaskTrigger -Daily -At $startLocal -DaysInterval 1
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $startLocal `
    -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration (New-TimeSpan -Hours ($windowHours - 1))).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 12)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("Gamma Conductor -- the 'Gamma drives' engine. Hourly 18:00-07:00 ET (after-hours ONLY; never RTH per L54). One bounded task per fire: read engine-health + STATUS + queue, pick the highest-value ready item, fan out a specialist persona, validate via gym/tests, SHIP only if it clears the auto-ratify gate ELSE propose-and-ping-J. Fail-open (never blocks J -- OP-32 scar). Doctrine/params/orders are PROPOSE-only. Opus, ~`$1.50/fire. Prompt: automation/prompts/conductor.md.") | Out-Null

Write-Output ("OK: Registered $TaskName")
Write-Output ("    Cadence: hourly 18:00-07:00 ET  (local start " + $startLocal.ToString("HH:mm") + ", ET-local delta " + $etMinusLocalHours + "h, " + $windowHours + " fires/night)")
Write-Output ("    Gate:    after-hours ONLY -- wrapper + prompt both refuse 09:30-15:55 ET (rail 1 / L54)")
Write-Output ("    Chain:   wscript -> run_exe_hidden.vbs -> sys-pythonw -> run_ps1_hidden.py -> run-conductor.ps1 -> claude --print (opus, --agent gamma)")
Write-Output ("    Prompt:  automation\prompts\conductor.md")
Write-Output ("    Cost:    ~`$1.50/fire (opus, bounded; ~`$15-20/mo if it fires nightly)")
Write-Output ("    Verify:  python setup\scripts\audit_scheduled_tasks.py")
Write-Output ("    Re-run after a DST shift to re-anchor the local start hour.")
