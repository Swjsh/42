#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_FreeModelAudit -- daily 23:48 ET (21:48 MT) fire of
  setup/scripts/free_model_audit.py --subject all (J directive 2026-07-11:
  "audit it every other day until we're confident in it... reusable harness framework").

  DRIFT FIX (2026-09-03, quiet-mode starvation regression, commit dceb125e): the LIVE task
  was re-timed 2026-08-26 to 23:48 ET (into quiet_mode.py's 23:00-08:00 ET LOUD maintenance
  band -- the old 21:00 ET slot sits inside the 16:00-08:00 blackout and starves silently,
  per tests/test_quiet_mode_starvation.py). This installer's own hardcoded "19:00" was never
  updated to match, so re-running it (as the 2026-09-03 evening self-heal sweep did, to add
  the PT15M/PT30M repetition) silently dragged the live trigger back to the starved 21:00 ET
  time. Fixed here so the installer is once again the source of truth SCHEDULED-TASKS.md's
  row claims it is.
  "all" grades every registered AUDIT_SUBJECTS entry each fire (heartbeat_veto, twin_review,
  future subjects) -- each self-gates its own cadence independently, so adding a new subject
  never requires re-touching this installer again.

  Grades heartbeat_core.py's `_free_model_eval` 2-lane free-model veto gate against ground
  truth: real fill P&L for GO decisions, counterfactual replay (real OPRA option bars through
  the live exit_manager decision core) for VETOED decisions, falling back to a blind Sonnet
  re-judgment only when replay is genuinely infeasible. Writes
  analysis/free-model-audit/heartbeat-veto/YYYY-MM-DD-scorecard.md +
  automation/state/free-model-audit-history.jsonl +
  automation/state/free-model-audit-state.json. Fires AFTER Gamma_TradeAutopsy (16:15 ET) so
  the day's fills are already in fills-ledger.jsonl for real-fill grading.

  CADENCE -- the SCRIPT self-gates internally to "every other day" (J's literal ask), NOT the
  scheduled task: this task fires DAILY (the proven DailyTrigger pattern -- see this repo's
  own trigger lesson: a bare one-time/interval trigger goes dark after the install day, e.g.
  install-dress-rehearsal.ps1 / install-crypto-twin.ps1's docstrings), and
  free_model_audit.run_subject() reads automation/state/free-model-audit-state.json's
  last_run_date + cadence_days and prints a clearly-logged "SKIPPED (not due...)" line on the
  days it isn't due -- never silent (OP-25/C7). Once a subject crosses the confidence bar
  (>=85% correct-grade rate over >=15 evidence points, sustained 3 consecutive runs -- the
  SAME bar as the existing Nemotron shadow-model promotion standard), the script auto-relaxes
  its OWN required cadence to every 7 days and logs a STATUS.md note -- no re-install needed.

  REAPER EXEMPTION + WIRING PATTERN -- mirrors install-crypto-twin.ps1 exactly:
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> free_model_audit.py
  'pythonw.exe' sits outside Stop-StaleClaudeProcesses's Win32_Process Name filter entirely
  (setup/scripts/_shared.ps1), so this task's process is never even fetched by the reaper's
  query -- independent of any string-match exemption list. backtest-venv pythonw is used
  because free_model_audit.py imports pandas (via crypto/lib/strike_selection dependencies)
  and this repo's fleet/backtest modules, which only resolve cleanly under that interpreter.

  Cost: $0 incremental API spend -- counterfactual replay hits real Alpaca market data (same
  already-paid subscription every other tool in this repo uses) and needs no LLM call at all;
  the Sonnet fallback (measured 0% usage rate across a REAL 106-item full-history dry run,
  2026-07-11) rides the Max subscription pool via `claude --print`, same cost characterization
  as manager_overseer.py / gamma-drive, not metered API spend. See free_model_audit.py's
  module docstring for the measured per-run estimate.

  To verify after running: Get-ScheduledTask -TaskName Gamma_FreeModelAudit
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root     = "C:\Users\jackw\Desktop\42"
$taskName = "Gamma_FreeModelAudit"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$script       = Join-Path $root "setup\scripts\free_model_audit.py"
# 2026-08-07: relay through run_cmd_hidden.py for real exit-code visibility -- see
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT / Gamma_CryptoTwin drift finding, queue.md.
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"

if (-not (Test-Path $script))      { throw "free_model_audit.py not found at $script" }
if (-not (Test-Path $sysPythonw))  { throw "system pythonw.exe not found at $sysPythonw" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> backtest-venv pythonw -> free_model_audit.py --subject all
# (flash-free chain; reaper-exempt by construction -- see docstring above). "all" runs every
# registered AUDIT_SUBJECTS entry (heartbeat_veto, twin_review, ...future subjects) in one
# fire -- each subject self-gates its OWN cadence independently, so this stays safe to call
# daily even as more subjects get wired (fixed 2026-07-11: this task originally hardcoded
# --subject heartbeat_veto, so twin_review's B2 wiring was never actually graded on a
# schedule despite being registered in the harness).
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`" `"--subject`" `"all`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# 23:48 ET weekday-and-weekend daily fire (the SCRIPT decides every-other-day internally --
# see docstring), inside the quiet-mode LOUD maintenance band. MT = ET - 2h during EDT, so
# 23:48 ET = 21:48 MT. Simple -Daily -At form, NOT the one-time-trigger foot-gun (project
# lesson: a trigger with no recurrence spec goes dark after the install day).
$trigger = New-ScheduledTaskTrigger -Daily -At "21:48"
# 2026-09-03 EVENING-TASK-MISSED-RUN-SWEEP (queue.md): a correctly-registered -Daily trigger
# can still silently skip ONE evening's fire (same class as Gamma_MacroCalendar/
# Gamma_EarningsCalendar/Gamma_PremarketReadiness, ac47dd10). free_model_audit.py's
# already_graded_ids() dedupes by item_id before appending history, so an extra fire on a
# normal day is a safe no-op. Self-heal window: every 15 min for 30 min after the primary fire.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "21:48" `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Grades heartbeat_core.py's free-model veto gate against ground truth (real fills + counterfactual OPRA replay, Sonnet-judgment fallback). Fires daily 23:48 ET, self-gates internally to every-other-day (auto-relaxes to weekly once confident: >=85%% correct-grade rate / >=15 evidence pts / 3 consecutive runs). Writes analysis/free-model-audit/heartbeat-veto/*.md. Read-only on all decisions.jsonl. Built 2026-07-11 (AUDIT-HARNESS-B1)." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
