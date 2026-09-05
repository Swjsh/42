#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_JIntentExecutor -- the standing deterministic executor for
  J-CALLED conditional trades (automation/overnight/queue.md
  ## J-INTENT-EXECUTOR, J-called 2026-07-15 13:30 ET).

  PURPOSE: J: "you are too slow to decide then implement and making LLM calls
  for logic." Today's J-called 752P took ~16 min to arm through a
  hand-written one-off watcher (with a stale-bar bug), ~2 min trigger->fill,
  ~1 min stop->flat -- every hop had an LLM wake inside it. From now on,
  Claude's ONLY role at trade time is to write one intent JSON into
  automation/state/j-intents.json (<60s, one turn, zero ongoing LLM calls --
  see setup/scripts/j_intent_executor.py::arm_intent_example). This task
  keeps a resident daemon alive during RTH so an armed intent is picked up
  and acted on within 15s, with ZERO LLM calls on the hot path.

  ACCEPTANCE GATE (already run + green before this script exists, per the
  build's own doctrine -- never arm live before this passes):
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_j_intent_executor_replay.py -v
  23/23 passed 2026-07-15, replaying J's REAL 752P trade from REAL Alpaca IEX
  5m bars: triggers on the 13:15-close bar, no earlier false trigger,
  chart-stop exit-signal on the 13:20-close bar -- plus stale-bar immunity,
  invalidation, expiry, kill-switch refusal, double-entry refusal, and
  concurrent-instance-lock guards.

  DEFAULT STATE = NO-OP: automation/state/j-intents.json ships with an EMPTY
  intents list. The daemon polling an empty store places NOTHING (guard:
  test_default_empty_intents_is_pure_noop) -- registering this task does NOT
  arm any trade; arming is a SEPARATE, explicit step (Claude appending one
  intent dict, per J's live instruction, any time after this task exists).

  RESIDENT-DAEMON DESIGN (deliberately NOT a 5s/15s-repeating --once launcher
  like context_bundle_producer's pattern): j_intent_executor.py --daemon
  stays resident and ticks every 15s INTERNALLY (time.sleep), self-exiting at
  16:00 ET or after 30 minutes with an empty/all-terminal intents list. This
  task's OWN repetition interval is 30 minutes -- just often enough to
  relaunch the daemon if a prior instance already idled out, so a
  newly-armed intent is always picked up within a 30-min worst case without
  the process sitting resident all day when there is nothing to watch.
  MultipleInstances=IgnoreNew is the scheduler-level guard against two
  overlapping fires; j_intent_executor.py additionally self-guards with an
  in-process lock file (acquire_daemon_lock) so two resident instances can
  never race on the same j-intents.json (double-order risk, C11/Rule-4).

  WIRING PATTERN (flash-free, matches install-futures-mirror.ps1 /
  install-crypto-twin.ps1 / install-context-bundle.ps1):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> j_intent_executor.py --daemon
  Runs on the BACKTEST venv (not system Python) -- the script imports
  fleet_broker/exit_manager/risk_gate/strike_selection, matching every other
  order-adjacent daemon's interpreter choice. This ALSO makes it reaper-
  exempt for free: setup/scripts/_shared.ps1's Stop-StaleClaudeProcesses
  matches on the literal substring 'backtest\.venv' in $EXEMPT_DAEMONS, and
  its process-name Filter clause does not even query pythonw.exe in the
  first place (belt-and-suspenders, same as every other 2026-07-14/15
  pythonw-hidden daemon in this repo).

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 09:25 ET -> 07:25 MT.
  NEVER pass an ET literal to -At. A REPEATING trigger (Once + 30min
  RepetitionInterval + RepetitionDuration spanning RTH), never a one-shot
  TimeTrigger (which would go dark the next day --
  project_scheduled_task_onetime_trigger_dark).

  To verify after running: Get-ScheduledTask -TaskName Gamma_JIntentExecutor | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_JIntentExecutor" -Confirm:$false
          (the daemon self-exits at 16:00 ET / 30min-idle regardless; this
          only stops FUTURE scheduled (re)launches. To also stop the current
          run immediately: taskkill against the pythonw.exe PID recorded in
          automation/state/j-intent-executor.lock.)
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root        = "C:\Users\jackw\Desktop\42"
$vbs         = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw  = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$pythonPath  = Join-Path $root "backtest\.venv\Lib\site-packages"
$script      = Join-Path $root "setup\scripts\j_intent_executor.py"
$etz         = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName    = "Gamma_JIntentExecutor"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

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

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# 2026-09-05 SILENT-RIG fix: was a single-hop wscript -> vbs -> venv-pythonw chain (the
# console-subsystem stub, root cause of the 730-window flash). Now two-hop like every other
# task in this registry: wscript -> vbs -> SYSTEM pythonw -> run_cmd_hidden.py -- SYSTEM
# pythonw j_intent_executor.py --daemon, with --env PYTHONPATH so venv deps still resolve.
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`" --daemon"

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 07:25 MT = 09:25 ET start; re-check/relaunch every 30 min for 6h35m -> covers
# 09:25-16:00 ET. The daemon itself provides the real 15s cadence internally;
# this repetition is only "is a resident instance still alive -- if not, relaunch".
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "07:25"
$rep = (New-ScheduledTaskTrigger -Once -At "07:25" `
        -RepetitionInterval (New-TimeSpan -Minutes 30) `
        -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 35)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 7) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("Standing deterministic executor for J-CALLED conditional trades " + `
    "(J-called 2026-07-15 13:30 ET, queue ## J-INTENT-EXECUTOR). Every 30 min, " + `
    "09:25-16:00 ET weekdays, ensures a resident j_intent_executor.py --daemon is " + `
    "alive (relaunches only if the prior instance already self-exited on 16:00/idle). " + `
    "The daemon polls automation/state/j-intents.json every 15s: on an ARMED intent, " + `
    "evaluates the SAME trigger/invalidation/chart-stop logic the acceptance-gate " + `
    "replay test proved against J's real 2026-07-15 752P trade (test_j_intent_executor_" + `
    "replay.py, 23/23 green) -- broker-flat check (C11) + risk_gate.check_order sizing " + `
    "+ settlement ledger + a simple marketable-limit entry, then hands the fill to " + `
    "exit_actuator/exit_manager (TP1 + catastrophe + chandelier trail + chart-stop + " + `
    "time-stop, arm_id j_intent_{account} -- isolated from core/fleet state), and " + `
    "journals every transition (Rule 8). Zero LLM calls after arming. DEFAULT STATE " + `
    "(empty j-intents.json) is a PURE NO-OP -- registering this task arms NOTHING by " + `
    "itself. MultipleInstances=IgnoreNew + an in-process lock file " + `
    "(automation/state/j-intent-executor.lock) both guard against two daemon " + `
    "instances racing on the same intents store.") `
    -Force | Out-Null

Write-Host "Registered $taskName (07:25 MT = 09:25 ET start, relaunch-check every 30 min for 6h35m, Mon-Fri)"
Show-NextET $taskName
Write-Host ""
Write-Host "j_intent_executor wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_JIntentExecutor | Get-ScheduledTaskInfo"
Write-Host ""
Write-Host "j-intents.json ships EMPTY -- this registers the daemon, it does NOT arm any trade."
Write-Host "To arm: append one intent (template: j_intent_executor.py::arm_intent_example) to"
Write-Host "  automation/state/j-intents.json's 'intents' list with status='armed'."
