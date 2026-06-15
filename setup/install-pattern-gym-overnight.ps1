#requires -Version 5.1
<#
.SYNOPSIS
  Install/register the Gamma_PatternGymOvernight scheduled task.

.DESCRIPTION
  Fires nightly at 03:30 ET. Pure-Python pattern-detector regression that
  replays the last 5 trading days, drift-detects rolling-7-day WR vs 16-mo
  baseline, surfaces alerts to automation/overnight/STATUS.md.

  Uses OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe (GUI subsystem)
                   -> run_exe_hidden.vbs (Shell.Run windowStyle=0)
                   -> sys-pythonw.exe (GUI subsystem)
                   -> run_ps1_hidden.py (Python launcher)
                   -> subprocess.Popen(powershell.exe, CREATE_NO_WINDOW)
                   -> run-pattern-gym-overnight.ps1
                   -> pattern_gym_overnight.py
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_PatternGymOvernight"

# Canonical hidden-spawn chain
$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw -- OP-27 L42 requires GUI-subsystem pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1 = Join-Path $ScriptsDir "run-pattern-gym-overnight.ps1"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

# Remove existing (idempotent)
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Build the action: wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> target.ps1
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# 03:30 ET daily -- well after EOD pipeline (16:00-17:00 ET) but before premarket (05:30 ET).
# Skips weekends via wrapper-side weekday check (PowerShell side); cron itself fires daily.
$trigger = New-ScheduledTaskTrigger -Daily -At ([DateTime]"03:30")

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Nightly pattern-detector regression (16-mo baseline drift check). Pure Python, zero LLM cost. Per OP-26 gym + OP-27 L42 hidden-spawn chain."

Write-Output ("OK: Registered $TaskName for 03:30 ET daily")
Write-Output ("    Action: wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> run-pattern-gym-overnight.ps1")
Write-Output ("    Audit:  python setup\scripts\audit_scheduled_tasks.py")
