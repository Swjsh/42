#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Register Gamma_LevelAlertDaemon scheduled task (09:25 ET weekday start).

.DESCRIPTION
  Creates a Windows scheduled task that invokes
  `setup/scripts/run-level-alert-daemon.ps1` every weekday at 09:25 America/New_York.
  The launched daemon runs until 16:05 ET writing alerts to
  `automation/state/live-alerts.jsonl`.

  This is a SYSTEM CHANGE — per CLAUDE.md OP 24 the autonomy stack does not
  register scheduled tasks without J authorization. Run this script manually
  when you want the daemon to start picking up Monday's session.

.NOTES
  Mirrors the install pattern of Gamma_WatcherLive / Gamma_Heartbeat in
  setup/install-tasks.ps1 — see those for the canonical version.
#>

$ErrorActionPreference = 'Stop'
$taskName = 'Gamma_LevelAlertDaemon'
$wrapperPath = 'C:\Users\jackw\Desktop\42\setup\scripts\run-level-alert-daemon.ps1'

# Run weekdays at 09:25 ET. Trigger uses local time (set Windows tz to
# America/New_York or accept that DST drift means daylight saving offset).
$action = New-ScheduledTaskAction -Execute 'pwsh.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$wrapperPath`""

$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At '9:25am'

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 7) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 2)

# Register under the current user. If the task exists, replace.
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Write-Output "Task $taskName already exists. Unregistering for clean install..."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Register-ScheduledTask -TaskName $taskName `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description 'Local SPY level-alert daemon — polls yfinance, writes live-alerts.jsonl. No Claude API cost.' `
    -User $env:USERNAME `
    -RunLevel Limited | Out-Null

Write-Output "Installed scheduled task: $taskName"
Write-Output "Will fire weekdays at 09:25 ET; daemon writes to automation/state/live-alerts.jsonl"
Write-Output ""
Write-Output "To verify: Get-ScheduledTask -TaskName $taskName | Format-List"
Write-Output "To test now: Start-ScheduledTask -TaskName $taskName"
Write-Output "To uninstall: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
