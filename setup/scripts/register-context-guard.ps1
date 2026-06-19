# Register Gamma_ContextGuard scheduled task at 16:10 ET daily (after EodDeepDive 16:05).
# Runs the context-budget guard with -AutoFix: scores CLAUDE.md, refreshes state, and
# if RED (over 8K tokens) AND after market hours, trips Claude to run the
# context-leanness skill. Idempotent: -Force overwrites.
# PowerShell 5.1 compatible.

$ErrorActionPreference = "Stop"

$taskName = "Gamma_ContextGuard"
$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\check-context-budget.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Error "Guard script not found: $scriptPath"
    exit 1
}

# Trigger: daily at 16:10 ET (after the EOD pipeline; outside market hours so edits are allowed)
$trigger = New-ScheduledTaskTrigger -Daily -At "16:10"

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -AutoFix"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -WakeToRun `
    -MultipleInstances IgnoreNew

try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Trigger $trigger `
        -Action $action `
        -Settings $settings `
        -Description "Context-leanness guard: keep CLAUDE.md under 8K tokens. Scores + alerts daily; auto-trims via the context-leanness skill on RED, after hours only. Fires 16:10 ET." `
        -Force `
        -ErrorAction Stop | Out-Null
    Write-Output "Registered $taskName (no-principal form)"
} catch {
    Write-Output ("Direct register failed: " + $_.Exception.Message)
    Write-Output ""
    Write-Output "MANUAL: run from elevated PowerShell:"
    Write-Output ("  powershell -NoProfile -ExecutionPolicy Bypass -File `"" + $PSCommandPath + "`"")
    Write-Output "Or Task Scheduler GUI:"
    Write-Output "  Name: $taskName   Trigger: Daily 16:10   Action: powershell.exe"
    Write-Output ("    Args: -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"" + $scriptPath + "`" -AutoFix")
    exit 1
}

$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Output ("  NextRun: " + $info.NextRunTime)
Write-Output ("  State: " + (Get-ScheduledTask -TaskName $taskName).State)
