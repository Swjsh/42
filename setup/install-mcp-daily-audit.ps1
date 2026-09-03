#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_McpDailyAudit scheduled task -- fires every day 23:20 ET.
  Daily round-trip health check of the Alpaca + TradingView MCP bridges.
  Hidden window per OP-27. Replaces Gamma_McpWeeklyAudit (Sunday-only).
  Mirrors install-mcp-weekly-audit.ps1.

  DRIFT FIX (2026-09-03): this script's own hardcoded time (18:30 ET) had gone
  stale since the 2026-08-26 quiet-mode starvation fix re-timed the LIVE task to
  23:20 ET (18:30 ET sits inside quiet_mode.py's 18:00-23:00 ET weekday blackout
  -- SCHEDULED-TASKS.md documents "the 16:00-08:00 blackout meant it fired
  never"). That re-time was applied directly to the scheduled task (Set-
  ScheduledTaskTrigger or the Task Scheduler UI) without updating THIS installer,
  so re-running this script for the 2026-09-03 mcp_daily_audit.py repoint
  silently reverted the live trigger back to 18:30 ET -- caught by diffing this
  file's hardcoded time against SCHEDULED-TASKS.md's documented value before
  trusting the reinstall. Fixed here so the installer is once again the source
  of truth this task's own registry row claims it is.
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

# Daily 23:20 ET (inside quiet_mode.py's 23:00-08:00 LOUD maintenance band --
# 2026-08-26 re-time; see DRIFT FIX note above). Convert ET -> local (Mountain)
# so DST is handled correctly -- the correct ET-target pattern.
$etZone   = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$etTarget = [System.DateTime]::SpecifyKind([System.DateTime]::Today.AddHours(23).AddMinutes(20), 'Unspecified')
$localAt  = [System.TimeZoneInfo]::ConvertTime($etTarget, $etZone, [System.TimeZoneInfo]::Local).ToString('HH:mm')
$trigger  = New-ScheduledTaskTrigger -Daily -At $localAt
# 2026-09-03 EVENING-TASK-MISSED-RUN-SWEEP (queue.md): same self-heal fix already shipped on
# Gamma_MacroCalendar/Gamma_EarningsCalendar/Gamma_PremarketReadiness (ac47dd10) -- a
# correctly-registered -Daily trigger can still silently skip one evening. mcp_daily_audit.py
# writes a plain overwrite snapshot (output_path.write_text(...)), so an extra fire on a
# normal day is a safe no-op. Self-heal window: every 15 min for 30 min after the primary fire.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $localAt `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$vbsWrapper`" `"$scriptPath`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 6)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $newTask -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Daily MCP connection audit -- round-trips Alpaca (Safe+Bold) account/clock + TradingView CDP port (deterministic `$0 Python probe, mcp_daily_audit.py, since 2026-09-03 -- was an Invoke-Claude LLM fire). 23:20 ET daily (2026-08-26 quiet-mode re-time, inside the LOUD maintenance band). Hidden window per OP-27. Replaces Gamma_McpWeeklyAudit." | Out-Null

$info = Get-ScheduledTask -TaskName $newTask | Get-ScheduledTaskInfo
Write-Host "Registered $newTask (daily 23:20 ET). Next run: $($info.NextRunTime)"
Write-Host "Gamma_McpWeeklyAudit has been unregistered."
