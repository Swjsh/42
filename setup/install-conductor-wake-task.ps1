#requires -Version 5.1
# Install Gamma_ConductorWake -- every 5 min, 24/7, $0 pure-Python wake-on-event watcher.
# Scans discord-outbox.jsonl + STATUS.md "## Known broken" for a NEW RED-grade alert since
# the last watermark; if found (debounced 30 min), Start-ScheduledTask's the right conductor
# mode for the current ET time-of-day (Gamma_ConductorRTH during weekday RTH, else
# Gamma_Conductor). J directive 2026-07-18: a RED alert shouldn't have to wait for the next
# scheduled cadence (up to 1h after-hours / 2h weekend / 30min RTH) to get a response.
#
# Uses the proven -Once + long RepetitionDuration pattern (Gamma_SelfCheck, live since
# 2026-06-29) -- unlike a same-day-duration -Once trigger (which goes dark after one day,
# project memory: project_scheduled_task_onetime_trigger_dark), a 10-year duration keeps
# recurring indefinitely without needing daily/weekly re-anchoring.
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$taskName = "Gamma_ConductorWake"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false; Write-Host "Unregistered $taskName."
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-conductor-wake.ps1"
if (-not (Test-Path $scriptPath)) { Write-Error "Required file missing: $scriptPath"; exit 1 }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$startBoundary = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPs1  = "C:\Users\jackw\Desktop\42\setup\scripts\run_ps1_hidden.py"
$runExe  = "C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden.vbs"
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument ("//nologo `"" + $runExe + "`" `"" + $pythonw + "`" `"" + $runPs1 + "`" `"" + $scriptPath + "`"")

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "WAKE-ON-EVENT for the Gamma_Conductor family (J directive 2026-07-18). Every 5 min, 24/7: scans discord-outbox.jsonl + STATUS.md Known-broken for a NEW RED-grade alert since the last watermark; if found (debounced 30 min), Start-ScheduledTask's Gamma_ConductorRTH (weekday RTH) or Gamma_Conductor (else). Pure Python, `$0, fail-open. Kill-switch: Disable-ScheduledTask Gamma_ConductorWake." | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
