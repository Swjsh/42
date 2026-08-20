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
  automation/state/futures/mirror-would-be.jsonl. It never edits the SPY/0DTE engine or its
  state -- read-only against the fleet decisions.jsonl, otherwise entirely self-contained
  under automation/state/futures/mirror-*.

  ARMED 2026-08-20 (desk_allocator.py "DECISION ROTTING" -- the arming bar CLEARED
  2026-08-19: 59/20 closed round trips, +$1,268.66, beats an ES=F buy-and-hold null; see
  automation/state/futures/shadow-progress.json). `--armed` sets MIRROR_ARMED=1: for every
  signal this poll ALSO opens as a shadow position (unchanged), it ADDITIONALLY places a REAL
  bracket order on the Tastytrade SANDBOX (paper; TT_SANDBOX=true; never reaches live money --
  OP-0 #1 plus a new venue, double-gated same as Gamma_FuturesBrokerLane). Frozen spec qty
  (2 in / 1 off at TP1), never resized by the risk rails -- a rail failure rejects the trade.
  Journals to automation/state/futures/mirror-broker-orders.jsonl (fills=BROKER), disjoint
  from mirror-would-be.jsonl (fills=SIMULATED) so the arming-bar's own evidence stream is
  never touched by the armed leg. See futures_mirror_shadow.py module docstring "ARMED
  EXECUTION" for the full design, cross-lane-safety disclosure (shares sandbox account
  5WW73759 + "MES" instrument with Gamma_FuturesBrokerLane; broker.is_flat() is account-truth
  so both lanes naturally refuse to stack on each other), and the tests in
  backtest/tests/test_futures_mirror_shadow.py::TestArmedExecution (12 guards).
  REVERT TO SHADOW-ONLY: remove " --armed" from $wscriptArgs below and re-run this installer
  (it always unregisters + cleanly re-registers Gamma_FuturesMirror).

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
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonwVenv`" `"$script`" --once --armed"

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
    -Description ("MES forward mirror of the live 0DTE SPY fleet signals (JOB 1, 2026-07-09; " + `
    "ARMED 2026-08-20). Every 5 min, 09:30-16:05 ET weekdays. futures_mirror_shadow.py " + `
    "--once --armed: tails the 4 fleet arms' decisions.jsonl for new ENTER_BULL/ENTER_BEAR " + `
    "rows, dedupes cross-arm (same signal fires on multiple arms -> ONE mirror trade), " + `
    "opens a synthetic MES shadow position priced off a live ES=F quote (stop = 2xATR14, " + `
    "TP1 = 1R half-off, runner trails 1R off HWM, flat by 15:55 ET next trading day) AND " + `
    "ADDITIONALLY places a REAL bracket order on the Tastytrade SANDBOX (paper only, never " + `
    "live money) at the same levels, frozen qty 2/1, gated by futures_risk_rails + " + `
    "broker.is_flat() cross-lane no-stack safety. Shadow ledger -> mirror-would-be.jsonl " + `
    "(fills=SIMULATED, the arming-bar evidence, untouched by arming). Broker ledger -> " + `
    "mirror-broker-orders.jsonl (fills=BROKER). Fail-open (exits 0 always, logs to " + `
    "automation/state/logs/futures-mirror-*.log). Arming bar CLEARED 2026-08-19: 59/20 " + `
    "closed round-trips, +`$1,268.66, beats an ES=F buy-and-hold null.") `
    -Force | Out-Null

Write-Host "Registered $taskName (07:30 MT = 09:30 ET start, every 5 min for 6h35m, Mon-Fri)"
Show-NextET $taskName
Write-Host ""
Write-Host "Futures mirror-shadow wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_FuturesMirror | Get-ScheduledTaskInfo"
