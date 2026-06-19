#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_HealthBeacon scheduled task -- every 1 min, 24/7.

.DESCRIPTION
  Runs engine_health.py every 1 minute. Phase 0a of the professional
  restructuring: fuse every liveness signal (both heartbeats, watcher feed,
  TV watchdog, kill-switches, positions) into ONE GREEN/YELLOW/RED verdict
  written to automation/state/engine-health.json, and ping Discord ONLY on a
  transition into RED. Turns fail-green into fail-loud mid-day.

  Runs 24/7 (NOT RTH-gated): the beacon is market-hours AWARE in Python (a
  quiet engine reads GREEN overnight), but it must still fire off-hours so a
  dead daemon or tripped breaker surfaces at any time. Pure Python = $0/day.

  Wired via OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-engine-health.ps1 -> engine_health.py

  TZ note (project memory: scheduled_task_tz -- rig is Mountain time): this task
  is all-day with a 1-min repetition, so the start MINUTE is irrelevant -- we
  anchor to LOCAL midnight ((Get-Date).Date) and repeat for 24h. There is no
  ET-to-local conversion needed precisely because the cadence is continuous.

  NOTE: this script registers the task; J / the installer runs it. It does not
  invoke schtasks itself beyond Register-ScheduledTask.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_HealthBeacon"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-engine-health.ps1"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# All-day: fire at local midnight, repeat every 1 min for 24h.
$start = (Get-Date).Date
$trigger = New-ScheduledTaskTrigger -Daily -At $start -DaysInterval 1
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $start `
    -RepetitionInterval (New-TimeSpan -Minutes 1) `
    -RepetitionDuration (New-TimeSpan -Days 1)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Engine Health Beacon. Every 1 min, 24/7. Fuses heartbeats + watcher feed + TV watchdog + kill-switches + positions into ONE GREEN/YELLOW/RED verdict (automation/state/engine-health.json). Discord pings on RED transition only. Market-hours aware (quiet=GREEN overnight). Pure Python = `$0/day. Phase 0a fail-loud." | Out-Null

Write-Output ("OK: Registered $TaskName")
Write-Output ("    Cadence: every 1 min, 24/7 (market-hours aware in Python)")
Write-Output ("    Chain:   wscript -> run_exe_hidden.vbs -> sys-pythonw -> run_ps1_hidden.py -> run-engine-health.ps1 -> engine_health.py")
Write-Output ("    Output:  automation/state/engine-health.json  (+ Discord outbox on RED transition)")
Write-Output ("    Cost:    `$0/day (pure Python)")
