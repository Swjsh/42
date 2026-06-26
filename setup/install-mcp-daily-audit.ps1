#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_McpDailyAudit scheduled task -- fires every day 18:30 ET.
  Daily round-trip health check of the Alpaca + TradingView MCP bridges.
  Hidden window per OP-27. Replaces Gamma_McpWeeklyAudit (Sunday-only).
  Mirrors install-mcp-weekly-audit.ps1.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$newTask  = "Gamma_McpDailyAudit"
$oldTask  = "Gamma_McpWeeklyAudit"

if ($Uninstall) {
    foreach ($t in @($newTask, $oldTask)) {
        if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $t -Confirm:$false
            Write-Host "Unregistered $t."
        }
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-mcp-daily-audit.ps1"
$vbsWrapper = "C:\Users\jackw\Desktop\42\setup\scripts\run_hidden.vbs"

# Unregister both old and new first (idempotent re-install)
foreach ($t in @($newTask, $oldTask)) {
    if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $t -Confirm:$false
        Write-Host "Unregistered $t."
    }
}

# Daily 18:30 ET. Convert ET -> local (Mountain) so DST is handled correctly.
# This is the correct ET-target pattern (avoids the 2h foot-gun on re-run).
$etZone   = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$etTarget = [System.DateTime]::SpecifyKind([System.DateTime]::Today.AddHours(18).AddMinutes(30), 'Unspecified')
$localAt  = [System.TimeZoneInfo]::ConvertTime($etTarget, $etZone, [System.TimeZoneInfo]::Local).ToString('HH:mm')
$trigger  = New-ScheduledTaskTrigger -Daily -At $localAt

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$vbsWrapper`" `"$scriptPath`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 6)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $newTask -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Daily MCP connection audit -- round-trips Alpaca (Safe+Bold) + TradingView MCP tools to catch a hung-but-alive bridge the CDP port check misses. 18:30 ET daily. ~`$0.10/fire. Hidden window per OP-27. Replaces Gamma_McpWeeklyAudit." | Out-Null

$info = Get-ScheduledTask -TaskName $newTask | Get-ScheduledTaskInfo
Write-Host "Registered $newTask (daily 18:30 ET). Next run: $($info.NextRunTime)"
Write-Host "Gamma_McpWeeklyAudit has been unregistered."
