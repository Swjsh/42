#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_SwarmPremarket scheduled task -- fires at 06:00 ET weekdays.

.DESCRIPTION
  Registers the swarm pre-market hypothesis engine. Runs automation/swarm/runner.py
  which produces swarm_output.json consumed by premarket.md Step 1c at 08:30 ET.

  Idempotent -- re-registers cleanly if already present.

.EXAMPLE
  .\setup\install-swarm-task.ps1
  .\setup\install-swarm-task.ps1 -Uninstall
#>

[CmdletBinding()]
param(
    [Parameter()][switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$taskName = "Gamma_SwarmPremarket"
$projectRoot = "C:\Users\jackw\Desktop\42"
$scriptPath = Join-Path $projectRoot "setup\scripts\run-swarm-premarket.ps1"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    } else {
        Write-Host "$taskName not registered. Nothing to do."
    }
    return
}

if (-not (Test-Path $scriptPath)) {
    throw "Wrapper script not found: $scriptPath"
}

# Remove existing version
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed existing $taskName"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

# Fires at 06:00 ET (system time, assuming machine is in ET zone)
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At ([DateTime]"06:00")

# 15-min execution limit (generous — all 6 agents run within ~10 min typically)
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Gamma: Swarm pre-market hypothesis engine (6 AI agents, produces swarm_output.json by 06:10 ET for premarket.md Step 1c)" `
    -Force | Out-Null

Write-Host "Registered: $taskName @ weekdays 06:00"
Write-Host "Verify: Get-ScheduledTask -TaskName '$taskName' | Get-ScheduledTaskInfo"
Write-Host "Manual run: Start-ScheduledTask -TaskName '$taskName'"
Write-Host ""
Write-Host "Output written to: $projectRoot\automation\swarm\state\swarm_output.json"
Write-Host "Consumed by: premarket.md Step 1c (08:30 ET)"
