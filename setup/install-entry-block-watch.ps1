#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_EntryBlockWatch -- the ESCALATION CORD (WS4, 2026-07-27 night build).
  Every 2 min, 09:30-16:00 ET, weekdays.

.DESCRIPTION
  THE INCIDENT: 2026-07-27 09:46-09:50 ET the engine scored J's setup 9/10 with real
  detections (level_rejection + confluence @744.9) and was blocked by ONE filter (5,
  ribbon). J found out hours later, after an $8 move. This task tails
  automation/state/core-decisions.jsonl (via entry_block_watch.py) and tells J the
  MOMENT a high-quality, level-tied setup shows up blocked -- not hours later.

  Pure Python stdlib, $0/tick, no LLM anywhere in the detection path, <2s steady-state
  (byte-offset tail, not a full re-read of the 20+MB ledger). Fail-open: any error
  degrades to a printed message and exit 0, never blocks/locks J out.

  WIRING PATTERN (flash-free, matches Gamma_WatcherLive / OP-27 L42):
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> pythonw.exe
                   -> run_ps1_hidden.py -> run-entry-block-watch.ps1
                   -> Invoke-PythonHidden -> entry_block_watch.py

  TZ RULE: this rig runs Mountain Time; ET = local + 2h. 09:30-16:00 ET = 07:30-14:00
  MT. NEVER pass an ET literal to -At. Weekly Mon-Fri trigger (not one-time, which
  would go dark the next day -- project_scheduled_task_onetime_trigger_dark).

  Verify: Get-ScheduledTask -TaskName Gamma_EntryBlockWatch
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_EntryBlockWatch"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw -- OP-27 L42 requires GUI-subsystem pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-entry-block-watch.ps1"
$watchScript  = Join-Path $ScriptsDir "entry_block_watch.py"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1, $watchScript)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

# Remove existing (idempotent)
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Action: wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> run-entry-block-watch.ps1
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`"" `
    -WorkingDirectory $WorkDir

# 07:30 MT = 09:30 ET, weekdays. Repeat every 2 min for 6h30m (-> 14:00 MT = 16:00 ET).
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At ([DateTime]"07:30")

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "ESCALATION CORD (WS4, 2026-07-27). Every 2 min, 07:30-14:00 MT (09:30-16:00 ET), Mon-Fri. Tails core-decisions.jsonl for a high-quality level-tied setup (bear_score>=8 or bull_score>=9 + a level-tied raw trigger) the engine did NOT enter; after 2 consecutive qualifying ticks, speaks ONE alert via the existing Kokoro/Discord voice pipeline (max 3/day). Pure Python, `$0/tick, fail-open, never trade-halts." `
    -Force | Out-Null

# Set 2-min repetition for 6h30m (07:30 -> 14:00 MT). Cannot be set on trigger before registration.
$task = Get-ScheduledTask -TaskName $TaskName
$task.Triggers[0].Repetition.Interval = "PT2M"
$task.Triggers[0].Repetition.Duration = "PT6H30M"
$task | Set-ScheduledTask | Out-Null

Write-Output "OK: Registered $TaskName -- every 2 min from 07:30 MT (09:30 ET), 6h30m (-> 16:00 ET), Mon-Fri"
Write-Output "    Action: wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> run-entry-block-watch.ps1 -> entry_block_watch.py"
Write-Output "    entry_block_watch.py self-gates on market hours + is a byte-offset-tail no-op when nothing new landed"
Write-Output ""
Write-Output "    Verify:   Get-ScheduledTask -TaskName '$TaskName' | Format-List"
Write-Output "    Test run: Start-ScheduledTask -TaskName '$TaskName'"
