#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_McpWeeklyAudit scheduled task -- fires Sunday 18:30 ET.
  Weekly round-trip health check of the Alpaca + TradingView MCP bridges.
  Hidden window per OP-27. Mirrors install-treasurer-weekly.ps1.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$taskName = "Gamma_McpWeeklyAudit"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-mcp-weekly-audit.ps1"
$vbsWrapper = "C:\Users\jackw\Desktop\42\setup\scripts\run_hidden.vbs"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Sunday 18:30 ET (weekly cadence -- after Gamma_WeeklyReview 18:00, before the week).
# This machine is Mountain time and New-ScheduledTaskTrigger -At treats the time as
# LOCAL, so convert 18:30 ET -> local first (else it fires 2h late). TimeZoneInfo
# handles ET<->local DST automatically. This is the correct ET-target pattern; the
# older install-*.ps1 scripts pass the ET number straight to -At (a 2h foot-gun if re-run).
$etZone   = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$etTarget = [System.DateTime]::SpecifyKind([System.DateTime]::Today.AddHours(18).AddMinutes(30), 'Unspecified')
$localAt  = [System.TimeZoneInfo]::ConvertTime($etTarget, $etZone, [System.TimeZoneInfo]::Local).ToString('HH:mm')
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At $localAt

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$vbsWrapper`" `"$scriptPath`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 6)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Weekly MCP connection audit -- round-trips Alpaca (Safe+Bold) + TradingView MCP tools to catch a hung-but-alive bridge the CDP port check misses. Sunday 18:30 ET. ~`$0.10/fire. Hidden window per OP-27." | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
