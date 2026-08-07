#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_FuturesMirror -- the MES forward shadow-mirror of the live 0DTE SPY fleet
  signals (JOB 1, 2026-07-09). The historical Phase-1 swing batteries killed the seed pile
  twice (backtest/futures/analysis/PHASE1-swing-battery/RESULTS.md: DOES_NOT_TRANSFER); the
  arm's one remaining path is FORWARD evidence -- mirror the CURRENT live 0DTE signals
  expressed on the linear MES instrument and let evidence accumulate going forward.

  PURPOSE: every 5 minutes during the trading window, futures_mirror_shadow.py tails the 4
  fleet arms' decisions.jsonl for new ENTER_BULL/ENTER_BEAR rows, dedupes cross-arm (the same
  strategy fires on multiple arms), opens a synthetic MES shadow trade priced off a live
  ES=F quote (ATR14-based stop, TP1 at 1R, runner trails 1R off its high-water-mark, flat by
  15:55 ET the next trading day), and appends every lifecycle event to
  automation/state/futures/mirror-would-be.jsonl. It places NO real order, touches NO broker
  credentials, and never edits the SPY/0DTE engine or its state -- read-only against the
  fleet decisions.jsonl, otherwise entirely self-contained under automation/state/futures/
  mirror-*.

  WIRING PATTERN (flash-free, matches install-swing-tasks.ps1 / install-preopen-readiness.ps1):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> futures_mirror_shadow.py --once
  Runs on the BACKTEST venv (not system Python) because the script imports pandas +
  yfinance + futures.swing_sim / futures.fill_sim_broker / futures.instruments, none of
  which are installed under system Python (same interpreter choice as Gamma_SwingCore /
  Gamma_SwingMonitor / Gamma_LevelMemory / Gamma_Trendlines -- see SCHEDULED-TASKS.md).

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 09:30 ET -> 07:30 MT,
  16:05 ET -> 14:05 MT. NEVER pass an ET literal to -At. A REPEATING trigger (Once + 5-min
  RepetitionInterval + RepetitionDuration spanning the window), never a one-shot TimeTrigger
  (which would go dark the next day -- project_scheduled_task_onetime_trigger_dark).

  To verify after running: Get-ScheduledTask -TaskName Gamma_FuturesMirror | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_FuturesMirror" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root        = "C:\Users\jackw\Desktop\42"
$vbs         = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script      = Join-Path $root "setup\scripts\futures_mirror_shadow.py"
$etz         = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName    = "Gamma_FuturesMirror"
# 2026-08-07: relay through run_cmd_hidden.py for real exit-code visibility -- see
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT / Gamma_CryptoTwin drift finding, queue.md.
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"

foreach ($p in @($vbs, $pythonwVenv, $script, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

function Show-NextET {
    param([string]$Name)
    $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction SilentlyContinue
    if ($info -and $info.NextRunTime) {
        $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
        Write-Host ("  NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
    } else {
        Write-Host "  NextRun ET: (none / on-demand)"
    }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- backtest venv pythonw -> futures_mirror_shadow.py --once
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonwVenv`" `"$script`" --once"

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 07:30 MT = 09:30 ET start; repeat every 5 min for 6h35m -> covers 09:30-16:05 ET.
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "07:30"
$rep = (New-ScheduledTaskTrigger -Once -At "07:30" `
        -RepetitionInterval (New-TimeSpan -Minutes 5) `
        -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 35)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("MES forward shadow-mirror of the live 0DTE SPY fleet signals (JOB 1, " + `
    "2026-07-09). Every 5 min, 09:30-16:05 ET weekdays. futures_mirror_shadow.py --once: " + `
    "tails the 4 fleet arms' decisions.jsonl for new ENTER_BULL/ENTER_BEAR rows, dedupes " + `
    "cross-arm (same signal fires on multiple arms -> ONE mirror trade), opens a synthetic " + `
    "MES position priced off a live ES=F quote (stop = 1.5xATR14, TP1 = 1R half-off, runner " + `
    "trails 1R off HWM, flat by 15:55 ET next trading day), logs every lifecycle event to " + `
    "automation/state/futures/mirror-would-be.jsonl. Places NOTHING real, no broker, no " + `
    "creds. Fail-open (exits 0 always, logs to automation/state/logs/futures-mirror-*.log). " + `
    "Arming bar (evaluated later, not by this task): >=20 closed round-trips, positive " + `
    "expectancy, beats an ES=F buy-and-hold null.") `
    -Force | Out-Null

Write-Host "Registered $taskName (07:30 MT = 09:30 ET start, every 5 min for 6h35m, Mon-Fri)"
Show-NextET $taskName
Write-Host ""
Write-Host "Futures mirror-shadow wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_FuturesMirror | Get-ScheduledTaskInfo"
