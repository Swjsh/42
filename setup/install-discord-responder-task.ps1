#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_DiscordResponder scheduled task -- the async approve/revoke bus.
  Every 15 min during the after-hours window 16:00-09:30 ET.

.DESCRIPTION
  Registers Gamma_DiscordResponder: each fire runs discord-responder.py once,
  which (1) consumes J's "ship <id>" / "shelve <id>" replies from the Discord
  inbox and resolves Conductor proposals in conductor-proposals.jsonl (pure
  Python, $0), and (2) answers free-form J questions via claude --print on HAIKU
  (cheap) -- but only after-hours.

  SAFETY:
    * AFTER-HOURS WINDOW. Triggers are 16:00..09:30 ET (after the close, into the
      pre-open). The script ALSO self-gates: it refuses to spawn ANY Claude model
      during RTH (weekday 09:30-15:55 ET) so it never competes with Gamma_Heartbeat
      on the shared Max rate-limit pool (L54). Approve/revoke parsing is pure
      Python and runs anytime; only the LLM Q&A is after-hours-only.
    * CHEAP. Haiku, --max-budget-usd 0.15, --effort low. Bus parsing is free.
    * FAIL-OPEN. Never kills/blocks J's session; reads inbox, writes outbox, exits.

  TZ NOTE (project memory: scheduled_task_tz -- rig is Mountain). Computes the
  live ET->local offset at install time and anchors triggers to local clock.
  Re-run after a DST shift to re-anchor.

  Wired via OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-discord-responder.ps1 -> discord-responder.py

  NOTE: this script REGISTERS the task; J / the installer runs it deliberately.
  Wire-don't-auto-enable. The inbound half (discord-bridge.py poll_inbox, kept
  alive by Gamma_DiscordBridge) must be running for J's replies to land in the inbox.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_DiscordResponder"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-discord-responder.ps1"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

# --- ET -> local offset (rig is Mountain; honor DST) --------------------------
$etZone = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
$nowUtc = [DateTime]::UtcNow
$etNow = [TimeZoneInfo]::ConvertTimeFromUtc($nowUtc, $etZone)
$localNow = [DateTime]::Now
$etMinusLocalHours = [math]::Round(($etNow - $localNow).TotalHours)

# After-hours window: 16:00 ET start -> 09:30 ET next morning = 17.5h of 15-min fires.
$startHourEt = 16
$startHourLocal = (($startHourEt - $etMinusLocalHours) % 24 + 24) % 24
$windowHours = 17.5

$startLocal = (Get-Date).Date.AddHours($startHourLocal)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

$trigger = New-ScheduledTaskTrigger -Daily -At $startLocal -DaysInterval 1
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $startLocal `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Hours $windowHours)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("Gamma Discord Responder -- async approve/revoke bus. Every 15 min 16:00-09:30 ET (after-hours). Consumes J's ship/shelve replies -> resolves conductor-proposals.jsonl (pure Python, `$0). Free-form Q&A via claude --print HAIKU, after-hours only (self-gates RTH per L54 -- never starves Gamma_Heartbeat). Fail-open. Needs Gamma_DiscordBridge running for inbound. Wire-don't-auto-enable.") | Out-Null

Write-Output ("OK: Registered $TaskName")
Write-Output ("    Cadence: every 15 min 16:00-09:30 ET  (local start " + $startLocal.ToString("HH:mm") + ", ET-local delta " + $etMinusLocalHours + "h)")
Write-Output ("    Bus:     consumes 'ship <id>'/'shelve <id>' -> conductor-proposals.jsonl + conductor-approvals.jsonl (pure Python, anytime)")
Write-Output ("    Q&A:     claude --print HAIKU, after-hours only (self-gates RTH per L54)")
Write-Output ("    Chain:   wscript -> run_exe_hidden.vbs -> sys-pythonw -> run_ps1_hidden.py -> run-discord-responder.ps1 -> discord-responder.py")
Write-Output ("    Dep:     Gamma_DiscordBridge (inbound poll_inbox) must be alive")
Write-Output ("    Verify:  python setup\scripts\audit_scheduled_tasks.py")
