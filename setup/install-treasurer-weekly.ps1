#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_TreasurerWeekly scheduled task -- fires Sunday 16:00 ET.
  Risk + money management audit for both accounts. Hidden window per OP-27.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$taskName = "Gamma_TreasurerWeekly"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-treasurer-weekly.ps1"
$vbsWrapper = "C:\Users\jackw\Desktop\42\setup\scripts\run_hidden.vbs"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Sunday 16:00 ET only (weekly cadence)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "16:00"

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$vbsWrapper`" `"$scriptPath`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Treasurer persona weekly audit -- sizing math, kill switches, account-tier transitions for Safe + Bold. Fires Sunday 16:00 ET. Cost ~`$0.20/fire. Hidden window per OP-27." | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
