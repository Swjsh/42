# Register Gamma_EodDeepDive scheduled task at 16:05 ET daily (post-EodSummary).
# Idempotent: -Force overwrites existing registration.

$ErrorActionPreference = "Stop"

$taskName = "Gamma_EodDeepDive"
$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-eod-deep-dive.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Error "Runner script not found: $scriptPath"
    exit 1
}

# Trigger: daily at 16:05 ET (5 min after EodSummary at 16:00)
$trigger = New-ScheduledTaskTrigger -Daily -At "16:05"

# Action: run the runner PS1
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

# Settings: hardened per harden-tasks pattern
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -WakeToRun `
    -MultipleInstances IgnoreNew

# Try non-elevated first (current user, Interactive logon). Most reliable
# pattern for personal-machine scheduled tasks without admin.
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Trigger $trigger `
        -Action $action `
        -Settings $settings `
        -Description "EOD Deep-Dive: canonical end-of-day analysis. Phase 2.4 ships 12-dimension scoring + winner forensics. Fires 16:05 ET daily." `
        -Force `
        -ErrorAction Stop | Out-Null
    Write-Output "Registered $taskName (no-principal form)"
} catch {
    Write-Output ("Direct register failed: " + $_.Exception.Message)
    Write-Output ""
    Write-Output "MANUAL REGISTRATION INSTRUCTIONS:"
    Write-Output "If automated registration fails (admin required), run from elevated PowerShell:"
    Write-Output "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Write-Output ""
    Write-Output "Or use Task Scheduler GUI to create a task:"
    Write-Output "  Name: $taskName"
    Write-Output "  Trigger: Daily at 16:05"
    Write-Output "  Action: powershell.exe"
    Write-Output ("    Args: -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"" + $scriptPath + "`"")
    exit 1
}

# Verify
$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Output ("  NextRun: " + $info.NextRunTime)
Write-Output ("  State: " + (Get-ScheduledTask -TaskName $taskName).State)
