#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_GymSession scheduled task -- fires daily at 17:00 ET (Mon-Fri).
  Fires BETWEEN Analyst (16:45) and Manager (17:30) so Manager can read the gym
  scorecard for the daily brief.
  Hidden window per OP-27 L42 canonical pattern.

.DESCRIPTION
  Unified chart-reading audit "physical exam":
    crypto-gym (42 validators) + chart-data-verify + heartbeat-tick-audit
    + pin-chain-verify + heartbeat-mcp-self-test + heartbeat-pulse-check
    + watcher-state-inspector
  -> ONE GREEN/YELLOW/RED scorecard at automation/state/gym-scorecard-{date}.json
  -> Narrative at analysis/gym/{date}.md
  Pure Python -- $0 cost.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$taskName = "Gamma_GymSession"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-gym-session.ps1"
$vbsWrapper = "C:\Users\jackw\Desktop\42\setup\scripts\run_hidden.vbs"

if (-not (Test-Path $scriptPath)) { throw "missing $scriptPath" }
if (-not (Test-Path $vbsWrapper)) { throw "missing $vbsWrapper" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# 17:00 ET weekdays -- after Analyst 16:45 + EOD pipeline, before Manager 17:30
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "17:00"

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$vbsWrapper`" `"$scriptPath`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Daily gym session -- single GREEN/YELLOW/RED for chart-reading engine, consumed by Manager for daily brief. Aggregates 7 audits (crypto-gym + chart-data-verify + tick-audit + pin-chain + mcp-self-test + pulse-check + watcher-state). Pure Python, `$0 cost. Hidden window per OP-27 L42." | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
