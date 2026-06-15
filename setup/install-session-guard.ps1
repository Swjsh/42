#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_SessionGuard scheduled task -- fires every 5 min during
  09:30-15:55 ET weekdays.

.DESCRIPTION
  Detects long-running interactive Claude Code sessions during market hours
  and logs them to STATUS.md WARN. Default mode = SOFT (log only). To enable
  hard-kill, set $env:GAMMA_SESSION_GUARD_MODE=hard before running this
  installer (the env var is captured by the task action).

  Per CLAUDE.md L54 (shared rate-limit foot-gun) + OP-22 (market-hours
  discipline). Closes the gap where an interactive session burns rate-limit
  quota the heartbeat needs.

  Uses OP-27 L42 canonical zero-leak chain.

  Pure Python. Zero LLM cost.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_SessionGuard"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw -- OP-27 L42 requires GUI-subsystem pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-session-guard.ps1"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# Daily 09:30 ET trigger, then repeat every 5 min for 6h25m (covers 09:30-15:55 ET).
$startToday = (Get-Date).Date.AddHours(9).AddMinutes(30)
$trigger = New-ScheduledTaskTrigger -Daily -At $startToday -DaysInterval 1
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $startToday `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 25)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Detect long-running interactive Claude Code sessions during market hours (09:30-15:55 ET). Default soft mode: appends WARN to STATUS.md per detection. Per CLAUDE.md L54 + OP-22."

Write-Output "OK: Registered $TaskName -- every 5 min, 09:30-15:55 ET weekdays (PS1 internally weekend-guards)"
Write-Output "    Mode: SOFT by default. To enable hard-kill, edit run-session-guard.ps1 or set GAMMA_SESSION_GUARD_MODE=hard system-wide."
Write-Output "    Audit:  python setup\scripts\audit_scheduled_tasks.py"
Write-Output "    Test:   Start-ScheduledTask -TaskName $TaskName"
