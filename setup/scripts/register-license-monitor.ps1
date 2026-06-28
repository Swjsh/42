# Register Gamma_LicenseMonitor: nightly at 22:30 ET (20:30 MT on J's Colorado machine).
# Monitors recency-confirmation.json for RED->YELLOW->CONFIRM transitions and pings J
# via Discord so the first eligible day after a drawdown is never missed.
# Idempotent (-Force overwrites). Pure $0 (backtest venv, cached OPRA only).
# PowerShell 5.1 compatible.

$ErrorActionPreference = "Stop"

$taskName   = "Gamma_LicenseMonitor"
$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-license-monitor.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Error "Wrapper script not found: $scriptPath"
    exit 1
}

# TZ-SYSTEMIC fix (ET = local + 2h on MT machine):
# 22:30 ET = 20:30 MT. Use MT local time for -At.
$trigger = New-ScheduledTaskTrigger -Daily -At "20:30"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPs1  = "C:\Users\jackw\Desktop\42\setup\scripts\run_ps1_hidden.py"
$runExe  = "C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden.vbs"
$action  = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument ("//nologo `"" + $runExe + "`" `"" + $pythonw + "`" `"" + $runPs1 + "`" `"" + $scriptPath + "`"")

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 3) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Trigger $trigger `
        -Action $action `
        -Settings $settings `
        -Force | Out-Null
    Write-Host "Registered: $taskName (daily 22:30 ET = 20:30 MT)" -ForegroundColor Green
} catch {
    Write-Error "Registration failed: $_"
    exit 1
}

$info    = Get-ScheduledTask -TaskName $taskName
$nextRun = (Get-ScheduledTaskInfo -TaskName $taskName).NextRunTime
Write-Host "State:   $($info.State)"
Write-Host "NextRun: $nextRun"
