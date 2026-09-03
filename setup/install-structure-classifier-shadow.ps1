#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_StructureClassifierShadow -- the $0 nightly SHADOW that gathers the
  EVIDENCE half of queue item STRUCTURE-VETO-CLASSIFIER-FIX (the classifier swap itself is
  a separate, later, 2026-10-30 decision), per the PRE-REGISTERED bar + decision rule in
  analysis/recommendations/prereg-structure-classifier-swap-2026-09-03.md.

.DESCRIPTION
  `_classify_sameday_5m` (backtest/lib/engine/engine_cli.py:192-224) calls ONLY
  `crypto.lib.market_structure.classify_trend` -- the module's own self-documented
  "tentative" fallback, fed `find_swing_points(window=2)` swings that structurally cannot
  confirm the newest 10 minutes of bars. The SAME module ships `walk_structure`, its own
  self-documented "authoritative" BOS/CHoCH state machine, with ZERO live callers (grep
  confirmed). On 2026-09-03 this produced a SKIP_STRUCTURE_VETO "downtrend" read 11:11-11:35
  ET during a continuous 6-point SPY rally (analysis/deep-research/2026-09-03-money/
  dissect-structure-veto-misclass.md).

  setup/scripts/structure_classifier_shadow.py: nightly, for every core tick (account=safe
  only -- the only account with structure_veto_enabled=true) since the veto's own first live
  fire (found dynamically, not hardcoded), scores both every SKIP_STRUCTURE_VETO row AND
  every ENTER_BULL/ENTER_BEAR row: rebuilds the same-day 5m bars available at that tick (no
  look-ahead, test-proven), labels them with BOTH classifiers -- `label_live` via the REAL
  `_classify_sameday_5m` (imported, never reimplemented) and `label_walk` via
  `walk_structure` on the identical swings -- and records the forward SPY move at +30/+60
  min in the vetoed/entered side's own favorable direction. Real continuous-tick bars come
  from the frozen `backtest/data/spy_5m_2026-05-19_2026-09-02.csv` cache (byte-verified this
  build against a real logged verdict); dates after 2026-09-02 fall back to an APPROXIMATE
  reconstruction from core-decisions.jsonl's own per-minute `spy` tape (disclosed on every
  such ledger row via `bar_source`). Appends to
  analysis/recommendations/structure-classifier-shadow-ledger.jsonl and rewrites
  -summary.json (agreement rate, favorable/veto-correct rates with bootstrap CIs split by
  classifier agreement, today's 11:16/11:21/11:27 ET rows quoted, the four named winning
  days' walk_structure veto check, and the forward (>=2026-09-03) decision clock). SHADOW
  ONLY -- never edits engine_cli.py/params.json/any trading-path file (read-only imports
  only), places no order.

  Forward bar (frozen, cannot be softened after data arrives): forward_sessions_accrued>=20
  AND forward_disagreement_ticks>=30 (ticks dated on/after 2026-09-03 only -- the historical
  backfill from 2026-07-06 is descriptive, not part of the frozen decision rule). Below the
  bar the summary's forward_decision_clock.status is ACCRUING and carries no ship/kill
  signal -- see the prereg file for the full decision rule (walk_structure's veto-correct
  rate CI-lower must exceed the live classifier's own CI-lower, AND zero of the four named
  winning days' entries may be vetoed by walk_structure -- which, per this build's own first
  pass, is ALREADY FALSE: 2026-08-06 and 2026-08-13 each show 5 entries walk_structure would
  have vetoed).

  17:25 ET weekdays = 15:25 MT (this box runs Mountain time; ET = local+2). PT15M/PT30M
  self-heal repetition covers a missed single-daily-trigger fire (same remedy already
  shipped for the evening-window task family, EVENING-TASK-MISSED-RUN-SWEEP).

  WIRING (stdlib-only -- no pandas/numpy import anywhere in the worker script, verified this
  build; cloned from install-tp1-r50-forward-shadow.ps1's base-pythonw recipe, since no venv
  package is needed):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> structure_classifier_shadow.py

  Output:
    analysis/recommendations/structure-classifier-shadow-ledger.jsonl   append-only, dedup
                                                                         on (account, ts_et)
    analysis/recommendations/structure-classifier-shadow-summary.json  this clock's own
                                                                        health + running stats

  Per CLAUDE.md OP-3 ($0, pure Python stdlib over an already-written cache + the existing
  core-decisions.jsonl ledger), OP-25 (fail loud -- a self-check runs every invocation and
  the run reports SELFCHECK_FAILED loudly rather than silently trusting a drifted cache/
  import), OP-33 (visibility is the product). Guard:
  backtest/tests/test_structure_classifier_shadow_2026_09_03.py.
  REVOKE (whole instrument, one shot): Unregister-ScheduledTask
  -TaskName Gamma_StructureClassifierShadow -Confirm:$false -- nothing on the trading path
  depends on this task (analysis-only leaf, same class as Gamma_Tp1R50ForwardShadow).

  NOTE: this installer is WRITTEN but per this task's own constraints has NOT been run --
  the scheduled task does not exist yet. Run it manually (no admin rights required, matches
  every sibling installer in this family) to actually register the task.
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\structure_classifier_shadow.py"
$taskName     = "Gamma_StructureClassifierShadow"

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

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 15:25 MT (17:25 ET) weekdays -- -Weekly triggers come back with a null .Repetition CIM
# instance; steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround, same technique install-tp1-r50-forward-shadow.ps1 uses).
# PT15M/PT30M self-heal window on a missed single-daily fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "15:25"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "15:25" `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Weekdays 15:25 MT (17:25 ET), self-heals every 15 min for 30 min on a " + `
    "missed fire: the EVIDENCE-half shadow for queue.md STRUCTURE-VETO-CLASSIFIER-FIX per " + `
    "the frozen prereg analysis/recommendations/prereg-structure-classifier-swap-2026-09-03.md. " + `
    "Scores every SKIP_STRUCTURE_VETO + ENTER_BULL/ENTER_BEAR tick (account=safe) with BOTH " + `
    "the live classify_trend-based classifier and the unused walk_structure state machine " + `
    "on the identical bars. NO trading-path file edited (read-only imports only). SHADOW " + `
    "ONLY -- flips nothing, places no order. `$0. Guard: " + `
    "backtest/tests/test_structure_classifier_shadow_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_StructureClassifierShadow -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- weekdays 15:25 MT (17:25 ET), self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
