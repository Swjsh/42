#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_DiscordBridge -- every-5-min keepalive for the Discord bridge +
  trade-watcher daemons (the proactive presence layer). Hidden window per OP-27.
  Runs ensure-discord-bridge-alive.ps1, which is idempotent: starts a dead daemon,
  no-ops if both are alive.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$taskName = "Gamma_DiscordBridge"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\ensure-discord-bridge-alive.ps1"
$vbsWrapper = "C:\Users\jackw\Desktop\42\setup\scripts\run_hidden.vbs"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Every 5 minutes, 24/7 (the bridge + watcher are 24/7 daemons; crypto trades none, but
# proactive comms + two-way listening run continuously).
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$vbsWrapper`" `"$scriptPath`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Keepalive for discord-bridge.py (outbox->Discord, inbox<-Discord) + discord-watcher.py (trade events -> Sharp-voice pings). Every 5 min, 24/7. Idempotent. Hidden window per OP-27." | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
