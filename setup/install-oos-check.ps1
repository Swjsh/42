#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_OosCheck scheduled task -- fires 21:40 MT (= 23:40 ET) DAILY.

  DRIFT FIX (2026-09-03, quiet-mode starvation regression, commit dceb125e):
  the LIVE task was re-timed 2026-08-26 to 23:40 ET (into quiet_mode.py's
  23:00-08:00 ET LOUD maintenance band -- the old 20:30 ET slot sits inside
  the 16:00-08:00 blackout and starves silently, per
  tests/test_quiet_mode_starvation.py). This installer's own hardcoded "18:30"
  was never updated to match, so re-running it (as the 2026-09-03 evening
  self-heal sweep did, to add the PT15M/PT30M repetition) silently dragged the
  live trigger back to the starved 20:30 ET time. Fixed here so the installer
  is once again the source of truth SCHEDULED-TASKS.md's row claims it is.

.DESCRIPTION
  Nightly OOS-validation runner for the promote_keeper pipeline (PIPELINE-AUDIT-
  2026-07-01 break #4: proposals stranded forever because contender_oos_check.py
  had no scheduled runner). Worker: setup/scripts/oos_check_runner.py. Each fire:
    1. Runs promote_keeper (refresh proposal from newest contender-rank; idempotent).
    2. Runs contender_oos_check.py per still-current pending proposal (backtest
       venv subprocess, CREATE_NO_WINDOW) -> writes {pid}-scorecard.json.
    3. Flips eval_bar_cleared=true on the proposal row in conductor-proposals.jsonl
       ONLY when all 5 OP-11 gates (incl. CONFIRM-BEFORE-CAPITAL recency) pass.
    4. Exits 0 ALWAYS (fail-open); logs to automation/state/logs/oos-check-{date}.log.

  NEVER edits params.json, never arms, never trades -- validation + eval-bar flip only.

  WHY 21:40 MT (= 23:40 ET): re-timed live 2026-08-26 into the quiet-mode LOUD
  maintenance band, after EOD pipeline + contender ranking. -At is LOCAL time
  (Task Scheduler convention); the rig is Mountain, so 21:40 MT = 23:40 ET. Do
  NOT relabel the -At value as an ET hour (the project_scheduled_task_tz foot-gun).

  TRIGGER NOTE: DailyTrigger (repeating) -- a one-time TimeTrigger goes dark after
  install day (project_scheduled_task_onetime_trigger_dark). Daily incl. weekends:
  weekend fires are cheap no-ops (idempotent promote_keeper + no new rankings).

  pythonw + the wscript -> run_exe_hidden.vbs chain is the canonical L41/L42/C8
  zero-leak hidden spawn (a bare powershell.exe -WindowStyle Hidden action flashes
  OpenConsole on Win11 -- dont-disturb-user mandate).

  To enable:  .\setup\install-oos-check.ps1
  To verify:  Get-ScheduledTaskInfo -TaskName Gamma_OosCheck | Select NextRunTime
  To test:    Start-ScheduledTask -TaskName Gamma_OosCheck
  To disable: Unregister-ScheduledTask -TaskName Gamma_OosCheck
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_OosCheck"

# Backtest venv pythonw (reaper-exempt interpreter home; the runner itself is
# stdlib-only but spawns the venv python.exe for the heavy OOS backtest).
$pythonw = "C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "backtest venv pythonw not found at $pythonw"
    exit 1
}

$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker       = Join-Path $ScriptsDir "oos_check_runner.py"

foreach ($p in @($runExeHidden, $worker)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <venv-pythonw> <oos_check_runner.py>  (fully hidden)
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$worker`""

# 21:40 LOCAL (Mountain) = 23:40 ET -- nightly, inside the quiet-mode LOUD band.
# DailyTrigger (never a one-time TimeTrigger -- those go dark after install day).
$trigger = New-ScheduledTaskTrigger -Daily -At "21:40"
# 2026-09-03 EVENING-TASK-MISSED-RUN-SWEEP (queue.md): same self-heal fix already shipped on
# Gamma_MacroCalendar/Gamma_EarningsCalendar/Gamma_PremarketReadiness (ac47dd10) -- a
# correctly-registered -Daily trigger can still silently skip one evening. oos_check_runner.py
# is idempotent (select_pending() skips already-graded proposal_ids, apply_cleared_scorecard()
# is an atomic per-row rewrite keyed on eval_bar_cleared), so an extra fire on a normal day is
# a safe no-op. Self-heal window: every 15 min for 30 min after the primary fire.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "21:40" `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Nightly OOS validation for promote_keeper proposals (23:40 ET / 21:40 MT daily): refreshes the proposal from the newest contender-rank, runs contender_oos_check (real OPRA fills, 5 OP-11 gates incl. CONFIRM-BEFORE-CAPITAL recency) in the backtest venv, and flips eval_bar_cleared=true on the conductor-proposals.jsonl row ONLY when all gates pass. Un-strands the research->engine bridge (PIPELINE-AUDIT-2026-07-01 break #4). Fail-open exit 0; logs to automation/state/logs/oos-check-{date}.log. NEVER edits params, never arms, never trades."

Write-Output "OK: Registered $TaskName for 23:40 ET daily (21:40 MT)"
Write-Output "    Interpreter: $pythonw"
Write-Output "    Worker:      setup\scripts\oos_check_runner.py"
Write-Output "    Log:         automation\state\logs\oos-check-{date}.log"
Write-Output "    Verify:      Get-ScheduledTaskInfo -TaskName $TaskName | Select NextRunTime"
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Output ("    NextRunTime: " + $info.NextRunTime)
