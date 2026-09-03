#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_Tp1R50ForwardShadow -- the $0 forward counterfactual shadow that
  ADJUDICATES R_tp100_f50 (queue.md TP1-R50-FORWARD-SHADOW, HIGH, filed 2026-08-23 Opus
  adjudication), per the PRE-REGISTERED bar + decision rule in
  analysis/recommendations/prereg-tp1-r50-forward-shadow-2026-09-03.md.

.DESCRIPTION
  R_tp100_f50 (TP1 sells 50% instead of ribbon_ride's live 66.7%) still fails gate G4 on
  the extended popA re-adjudication (n=213, commit 97f3c864) -- STRUCTURALLY, not
  statistically: G4's fixed calendar sub-windows are unreachable by construction for this
  cell (see the queue item + the prereg file for the full mechanism). The prereg's two
  DO-NOTs rule out re-specifying G4 and rule out a new backtest prereg on the same
  (already-seen) data. The only clean path is a forward shadow judged on data nobody has
  seen yet -- this task is that clock's heartbeat.

  setup/scripts/tp1_r50_forward_shadow.py: nightly, for every CLOSED ribbon_ride trade on
  an arm whose resolved live tp1_qty_fraction is 0.667, computes the per-trade dollar delta
  of an f=0.5 TP1 sell vs the live f=0.667, using ONLY that trade's own recorded broker legs
  (the TP1 partial-sell fill + the runner exit fill(s) from automation/state/fills-ledger.
  jsonl) -- never a re-simulation. Appends to
  analysis/recommendations/tp1-r50-forward-shadow-ledger.jsonl and rewrites
  -summary.json (n_trades, n_tp1_reached, n_no_op_rounding, sum_delta, mean_delta, a
  day-clustered bootstrap CI, top-3 concentration share, days_accrued). SHADOW ONLY --
  never flips tp1_qty_fraction, never places an order, never touches accounts.json or
  strategies.py (read-only imports).

  Forward bar (frozen, cannot be softened after data arrives): days_accrued>=20 AND
  n_tp1_reached>=25. Below the bar the summary's status is ACCRUING and carries no
  ship/kill signal -- see the prereg file for the full decision rule (day-clustered CI
  lower bound > 0, top-3 concentration < 50%, ex-best-day sum still positive).

  ACCRUAL_START_DATE is pinned to this build's own date (2026-09-03) inside the script --
  NO BACKFILL, forward-only by construction (the queue item's own words: "the clock starts
  at the first scheduled run").

  16:40 ET weekdays = 14:40 MT (this box runs Mountain time; ET = local+2) -- the same slot
  already shared by Gamma_LossArmedBudgetShadow and Gamma_LadderRungShadow (multiple
  sibling shadow clocks fire nominally together; each is fast and idempotent). PT15M/PT30M
  self-heal repetition covers a missed single-daily-trigger fire (same remedy already
  shipped for the evening-window task family, EVENING-TASK-MISSED-RUN-SWEEP).

  WIRING (stdlib-only -- no pandas/numpy import anywhere in the worker script, verified
  this build; cloned from install-xsp-spread-recorder.ps1's base-pythonw recipe rather than
  the venv-pythonw recipe, since no venv package is needed):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> tp1_r50_forward_shadow.py

  Output:
    analysis/recommendations/tp1-r50-forward-shadow-ledger.jsonl   append-only, dedup on
                                                                    activity_id
    analysis/recommendations/tp1-r50-forward-shadow-summary.json   this clock's own health +
                                                                    running totals

  Per CLAUDE.md OP-3 ($0, pure Python stdlib over two already-written artifacts), OP-25
  (fail loud, never silent -- skipped trades are recorded with a reason, never dropped
  silently), OP-33 (visibility is the product). Guard:
  backtest/tests/test_tp1_r50_forward_shadow_2026_09_03.py.
  REVOKE (whole instrument, one shot): Unregister-ScheduledTask
  -TaskName Gamma_Tp1R50ForwardShadow -Confirm:$false -- nothing on the trading path
  depends on this task (analysis-only leaf, same class as Gamma_LadderRungShadow).
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\tp1_r50_forward_shadow.py"
$taskName     = "Gamma_Tp1R50ForwardShadow"

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

# 14:40 MT (16:40 ET) weekdays -- -Weekly triggers come back with a null .Repetition CIM
# instance; steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround, same technique install-fee-recalibrate.ps1 uses). PT15M/PT30M
# self-heal window on a missed single-daily fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:40"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "14:40" `
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
    -Description ("Weekdays 14:40 MT (16:40 ET), self-heals every 15 min for 30 min on a " + `
    "missed fire: the FORWARD counterfactual shadow that adjudicates R_tp100_f50 (queue.md " + `
    "TP1-R50-FORWARD-SHADOW) per the frozen prereg " + `
    "analysis/recommendations/prereg-tp1-r50-forward-shadow-2026-09-03.md. Per-trade delta " + `
    "of an f=0.5 TP1 sell vs the LIVE f=0.667, using ONLY each trade's own recorded broker " + `
    "legs (never a re-simulation). NO BACKFILL -- accrual starts 2026-09-03. SHADOW ONLY -- " + `
    "flips nothing, places no order. `$0. Guard: " + `
    "backtest/tests/test_tp1_r50_forward_shadow_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_Tp1R50ForwardShadow -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- weekdays 14:40 MT (16:40 ET), self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
