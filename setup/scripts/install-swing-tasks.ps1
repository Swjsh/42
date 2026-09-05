#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_SwingCore + Gamma_SwingMonitor -- the futures multiday-swing PAPER
  fill-sim lane (FUTURES-REVIVAL-PLAN-2026-07-02.md sec 2a/2d, Phase 3 plumbing).

  *** STAGED ONLY AS OF THIS BUILD (2026-07-09) -- DO NOT RUN THIS SCRIPT YET. ***
  This installer was authored per the build task's explicit instruction to write-but-not-
  execute. Running it registers BOTH tasks live. Before running it:
    1. automation/state/futures/armed-setups.json must exist and list >=1 setup.
    2. That setup's analysis/recommendations/futures-swing-{seed}.json scorecard must read
       verdict=="PASS" (Phase-1 battery -- owned by a separate build, not this one).
    3. J's go-ahead per the standing paper-autonomy grant (OP-0) -- reversible/paper-only work
       ships without asking, but "staged, not registered" was this task's explicit boundary.
  Until armed-setups.json exists, swing_core_runner.py refuses every entry
  (SKIP_NO_VALIDATED_SETUP, logged) even after these tasks ARE registered -- registering them
  early is safe (no trade can fire) but the task said not to, so this stays unexecuted.

  PURPOSE: two cadences per FUTURES-REVIVAL-PLAN sec 2a --
    Gamma_SwingCore    -- ONE decision fire/day (15:35 ET, before the 16:00 CT settle):
                          exit/pending-fill management, THEN (gate permitting) SEE+DECIDE+ACT
                          for a new entry via swing_core_runner.py (no --monitor flag).
    Gamma_SwingMonitor -- every 15 min during the RTH-adjacent window (09:00-16:05 ET):
                          exit/pending-fill management ONLY (--monitor) -- this fill-sim's
                          own "exchange", since there is no real broker resting GTC orders
                          server-side to just verify (see swing_core_runner.py's docstring
                          point #3 on why this monitor genuinely IS the fill mechanism, not
                          mere verification like the plan's real-broker monitor sketch).
  Both tasks tick BOTH MNQ and MES (--mes flag) per the plan's stated priority (MES primary,
  direct SPY x10 mapping; MNQ second).

  WIRING PATTERN (2026-09-05 SILENT-RIG R6a fix -- was a direct wscript -> vbs -> backtest-
  venv-pythonw chain: backtest\.venv\Scripts\pythonw.exe is a launcher STUB whose base
  executable is the CONSOLE python.exe, and opens a terminal window per fire from this
  windowless parent. Now matches install-futures-eod.ps1 / install-level-memory.ps1's
  proven relay):
    wscript -> run_exe_hidden.vbs -> SYSTEM pythonw -> run_cmd_hidden.py --cwd <repo>
      -- SYSTEM pythonw -> swing_core_runner.py
  swing_core_runner.py imports futures_heartbeat_core, which transitively imports pandas +
  the full watcher fleet + the fillsim broker's yfinance quote fetch -- none of which are
  installed under system Python 3.13 by default, so PYTHONPATH is injected via run_cmd_
  hidden.py's --env flag to point at backtest\.venv\Lib\site-packages instead of running the
  venv's own (broken) pythonw.exe stub.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 15:35 ET -> 13:35 MT.
  NEVER pass an ET literal to -At. Weekly Mon-Fri triggers only (NOT a one-shot TimeTrigger,
  which would go dark after the first day -- project_scheduled_task_onetime_trigger_dark).

  To verify after running: Get-ScheduledTask -TaskName Gamma_SwingCore,Gamma_SwingMonitor |
                            Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_SwingCore" -Confirm:$false
          Unregister-ScheduledTask -TaskName "Gamma_SwingMonitor" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"
$script       = Join-Path $root "setup\scripts\swing_core_runner.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
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

# ---- Gamma_SwingCore: ONE daily decision fire, 13:35 MT = 15:35 ET, weekdays -------------
$taskCore = "Gamma_SwingCore"
if (Get-ScheduledTask -TaskName $taskCore -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskCore -Confirm:$false
}

$coreArgs   = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`" --mes"
$coreAction = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $coreArgs `
    -WorkingDirectory $root

# 13:35 MT = 15:35 ET, weekdays (before the 16:00 CT futures settle; matches plan sec 2a)
$coreTrigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At ([DateTime]"13:35")

$coreSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskCore -Action $coreAction -Trigger $coreTrigger `
    -Settings $coreSettings -Description ("Futures swing fill-sim PAPER lane -- ONE daily " + `
    "decision fire (FUTURES-REVIVAL-PLAN sec 2a Phase 3). 13:35 MT = 15:35 ET weekdays. " + `
    "swing_core_runner.py --mes: manages any open/pending MNQ+MES fill-sim position, then " + `
    "(gate permitting -- armed-setups.json + a PASS futures-swing-{seed}.json scorecard) " + `
    "runs SEE+DECIDE+ACT for a new entry. Fail-open (exits 0 always, logs to " + `
    "automation/state/logs/swing-core-*.log). Places NOTHING real -- own fill-sim broker " + `
    "only, no tastytrade SDK, no broker credentials touched.") `
    -Force | Out-Null

Write-Host "Registered $taskCore (13:35 MT = 15:35 ET, Mon-Fri)"
Show-NextET $taskCore

# ---- Gamma_SwingMonitor: every 15 min, 07:00-14:05 MT = 09:00-16:05 ET, weekdays ----------
$taskMonitor = "Gamma_SwingMonitor"
if (Get-ScheduledTask -TaskName $taskMonitor -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskMonitor -Confirm:$false
}

$monitorArgs   = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`" --monitor --mes"
$monitorAction = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $monitorArgs `
    -WorkingDirectory $root

# 07:00 MT = 09:00 ET; repeat every 15 min for 7h5m -> covers 09:00-16:05 ET (mirrors the
# repetition-trigger pattern in install-level-memory.ps1).
$monitorTrigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:00"
$rep = (New-ScheduledTaskTrigger -Once -At "07:00" `
        -RepetitionInterval (New-TimeSpan -Minutes 15) `
        -RepetitionDuration (New-TimeSpan -Hours 7 -Minutes 5)).Repetition
$monitorTrigger.Repetition = $rep

$monitorSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskMonitor -Action $monitorAction -Trigger $monitorTrigger `
    -Settings $monitorSettings -Description ("Futures swing fill-sim PAPER lane -- lightweight " + `
    "exit/pending-fill monitor (FUTURES-REVIVAL-PLAN sec 2a Phase 3). Every 15 min, " + `
    "09:00-16:05 ET weekdays. swing_core_runner.py --monitor --mes: checks live MNQ+MES " + `
    "quotes (yfinance) against any pending-entry limit or open position's stop/tp1/runner " + `
    "and realizes a simulated fill on a touch (gap-aware stops -- fills WORSE than the stop " + `
    "on a gap, never at it). Never attempts a NEW entry (that is Gamma_SwingCore's job, " + `
    "once/day). Fail-open, places NOTHING real.") `
    -Force | Out-Null

Write-Host "Registered $taskMonitor (every 15 min, 09:00-16:05 ET, Mon-Fri)"
Show-NextET $taskMonitor

Write-Host ""
Write-Host "Swing fill-sim lane wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_SwingCore,Gamma_SwingMonitor | Get-ScheduledTaskInfo"
Write-Host ""
Write-Host "REMINDER: entries stay gated SKIP_NO_VALIDATED_SETUP until automation/state/futures/armed-setups.json exists AND its scorecard(s) read verdict=PASS."
