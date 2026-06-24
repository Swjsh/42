#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_ShadowEval scheduled task -- fires daily at 16:05 ET (Mon-Fri).
  Runs shadow_model_eval.py for today's date on both accounts using Nemotron free tier.
  No Claude session opened; $0 cost. Writes scorecard to analysis/shadow-model/.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$taskName = "Gamma_ShadowEval"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-shadow-eval.ps1"
$vbsWrapper = "C:\Users\jackw\Desktop\42\setup\scripts\run_hidden.vbs"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# 16:05 ET weekdays -- after market close (16:00), before EOD Analyst (16:45).
# MT (Mountain Time) = ET - 2h during MDT, so 16:05 ET = 14:05 MT.
# Windows Task Scheduler uses LOCAL time, so we enter MT here.
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "14:05"

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$vbsWrapper`" `"$scriptPath`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Nemotron shadow DT-agreement scorer. Free-tier ($0). Scores today's heartbeat decisions vs Nemotron; writes analysis/shadow-model/YYYY-MM-DD-scorecard.md. Fires 16:05 ET weekdays. No Claude session." | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
