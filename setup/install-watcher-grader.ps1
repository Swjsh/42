#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_WatcherGrader scheduled task -- fires 17:10 ET Mon-Fri.

.DESCRIPTION
  Grades ungraded watcher observations post-market. Fires AFTER Gamma_EodSummary
  (16:00) so append_today.py has created the daily-appended spy_5m CSV.

  Uses OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe (GUI subsystem)
                   -> run_exe_hidden.vbs (Shell.Run windowStyle=0)
                   -> sys-pythonw.exe (GUI subsystem)
                   -> run_ps1_hidden.py (Python launcher)
                   -> subprocess.Popen(powershell.exe, CREATE_NO_WINDOW)
                   -> run-watcher-grader.ps1
                   -> watcher_grader.py

  Pure Python. Zero LLM cost.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_WatcherGrader"

# Canonical hidden-spawn chain (OP-27 L42)
$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw -- OP-27 L42 requires GUI-subsystem pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-watcher-grader.ps1"

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

# 17:10 ET weekdays -- after Gamma_EodSummary (16:00, creates daily CSV) + Gamma_AnalystEodReview (16:45)
# and before Gamma_ManagerDailyVerify (17:30) so Manager can mention grading status in daily brief.
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "17:10"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Grade ungraded watcher observations post-EOD. Reads watcher-observations.jsonl, fetches future bars from daily-appended CSV, writes would_be_outcome. Pure Python, zero LLM cost. OP-21 watch-first promotion requires graded observations."

Write-Output "OK: Registered $TaskName for 17:10 ET weekdays"
Write-Output "    Action: wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> run-watcher-grader.ps1"
Write-Output "    Audit:  python setup\scripts\audit_scheduled_tasks.py"
Write-Output "    Test:   Start-ScheduledTask -TaskName $TaskName"
