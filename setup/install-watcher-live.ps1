#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_WatcherLive -- every 5 min, 09:30-15:55 ET Mon-Fri.

.DESCRIPTION
  Fires watcher_live.py to accumulate live watcher observations in
  automation/state/watcher-observations.jsonl. Killed in the 2026-05-23
  infrastructure reset (was one of 33 tasks nuked to stop rate-limit pool
  starvation). Re-registered 2026-05-24 after confirming the 13-task count
  is within safe limits.

  Uses OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe (GUI subsystem)
                   -> run_exe_hidden.vbs (Shell.Run windowStyle=0)
                   -> sys-pythonw.exe (GUI subsystem)
                   -> run_ps1_hidden.py (Python launcher)
                   -> subprocess.Popen(powershell.exe, CREATE_NO_WINDOW)
                   -> run-watcher-live.ps1
                   -> Invoke-PythonHidden -> Python313 + PYTHONPATH=venv
                   -> watcher_live.py

  watcher_live.py self-gates on market hours (09:30-15:55 ET + weekday).
  run-watcher-live.ps1 also gates before spawn to avoid unnecessary PS launches
  outside market hours.

  Pure Python. Zero LLM cost. Fires every 5 min from 09:30, duration 6h25m (-> 15:55).

.WHY
  OP-21 watch-first setups (ORB, V14E_BEAR, BULLISH_RECLAIM, H&S, DB, FBW, NLWB,
  RSI_DIV, etc.) need live observations to progress through the promotion gate.
  Without this task, watcher-observations.jsonl only contains backtest replay data
  and no promotion paths can advance. Gap discovered 2026-05-24: last live obs
  was 2026-05-15 (9 days of zero accumulation post-reset).
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_WatcherLive"

# OP-27 L42 canonical chain components
$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw -- OP-27 L42 requires GUI-subsystem pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-watcher-live.ps1"
$watcherLive  = Join-Path $WorkDir "backtest\autoresearch\watcher_live.py"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1, $watcherLive)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

# Remove existing (idempotent)
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Action: wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> run-watcher-live.ps1
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# Trigger: daily at 09:30, repeat every 5 min for 6h25m (-> 15:55 ET)
# Trigger fires Mon-Fri. run-watcher-live.ps1 gates on weekday too (belt + suspenders).
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "09:30"

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
    -Description "Run watcher_live.py once per tick. Accumulates live watcher observations (ORB, V14E_BEAR, H&S, DB, etc.) in watcher-observations.jsonl. Zero LLM cost. OP-21 promotion path requires live observations. Re-registered 2026-05-24 after 2026-05-23 infrastructure reset." `
    -Force | Out-Null

# Set 5-min repetition for 6h25m (09:30 -> 15:55). Cannot be set on trigger before registration.
$task = Get-ScheduledTask -TaskName $TaskName
$task.Triggers[0].Repetition.Interval = "PT5M"
$task.Triggers[0].Repetition.Duration = "PT6H25M"
$task | Set-ScheduledTask | Out-Null

Write-Output "OK: Registered $TaskName -- every 5 min from 09:30, 6h25m (-> 15:55 ET), Mon-Fri"
Write-Output "    Action: wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> run-watcher-live.ps1"
Write-Output "    watcher_live.py self-gates on market hours inside the script"
Write-Output ""
Write-Output "    Verify:   Get-ScheduledTask -TaskName '$TaskName' | Format-List"
Write-Output "    Test run: Start-ScheduledTask -TaskName '$TaskName'"
Write-Output "    Audit:    python setup\scripts\audit_scheduled_tasks.py"
