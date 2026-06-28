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

# TZ-SYSTEMIC fix (2026-06-26): machine is Mountain time (ET = local + 2h).
# Intended fire time: 16:10 ET = 14:10 MT.  Use MT local time for -At.
# If the machine moves back to ET, change 14:10 -> 16:10 and update this comment.
$trigger = New-ScheduledTaskTrigger -Daily -At "14:10"

# Windowless launch chain (project_mcp_window_leak_fix / audit BARE_CMD_POWERSHELL):
# a direct powershell.exe action flashes OpenConsole on Win11 -- route via wscript->pythonw.
$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPs1  = "C:\Users\jackw\Desktop\42\setup\scripts\run_ps1_hidden.py"
$runExe  = "C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden.vbs"
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument ("//nologo `"" + $runExe + "`" `"" + $pythonw + "`" `"" + $runPs1 + "`" `"" + $scriptPath + "`" -AutoFix")

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
    Write-Output "  Name: $taskName   Trigger: Daily 14:10 (MT = 16:10 ET)   Action: wscript.exe"
    Write-Output ("    Args: //nologo `"" + $runExe + "`" `"" + $pythonw + "`" `"" + $runPs1 + "`" `"" + $scriptPath + "`" -AutoFix")
    exit 1
}

$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Output ("  NextRun: " + $info.NextRunTime)
Write-Output ("  State: " + (Get-ScheduledTask -TaskName $taskName).State)
