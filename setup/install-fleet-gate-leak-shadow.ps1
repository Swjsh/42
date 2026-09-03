#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_FleetGateLeakShadow -- the $0 nightly shadow that joins core safe/bold
  verdicts x REAL fleet fills per core_tick_id (queue.md FLEET-GATE-LEAK-SHADOW, MED,
  filed 2026-09-03 14:51 ET), feeding the frozen decision rule in
  analysis/recommendations/prereg-fleet-gate-inheritance-2026-09-03.md.

.DESCRIPTION
  Closes out FLEET-STRATEGIES-BYPASS-SAFE-GATES (status:done, decided 14:51 ET
  2026-09-03): sig["strategies"] (every fleet arm's entry-side signal) defaults to
  SAFE's own block but substitutes BOLD's whenever SAFE is gated and BOLD's own
  perception separately passes -- and the mirror. The 20-agent fleet review found the
  leak PARTIAL not total (5.6-15% of safe-gated ticks on the two mapped GATE_KEYS gates)
  and the bypass cohort's P&L indistinguishable from zero on the in-sample data (every
  CI straddles zero, n=3-8 per gate). This instrument is the standing nightly clock the
  review committed to building: fills-corrected (never a decisions.jsonl action-row
  count -- proven inflated 1.2x-4.7x by re-logged still-open decisions,
  verify-fleet-gates-ledger-binding-check-2.md), per (core_tick_id, arm) real-fill
  outcome + FIFO P&L, backfilled from 2026-08-06 and accruing forward every night.

  setup/scripts/fleet_gate_leak_shadow.py: nightly, joins automation/state/core-
  decisions.jsonl (safe/bold per tick) against REAL closed round trips
  (automation/state/fleet/fills_fifo.mine_real_arm_fills) for safe-3/risky-1/risky-3/
  safe-1, matching within a 300s entry window (stated + justified in the module's own
  docstring). Appends to analysis/recommendations/fleet-gate-leak-ledger.jsonl (dedup on
  core_tick_id+arm+cohort+refused_account) and rewrites -summary.json (gate x arm
  tables, control cohort, VIX bands, the four named winning days + September window
  broken out separately, and the forward-bar tracking block this prereg's decision rule
  reads). SHADOW ONLY -- never calls fleet_executor._perception_for_arm, never edits
  accounts.json/strategies.py/build_shared_signal.py, never places an order.

  Forward bar (frozen, per decision-focus arm safe-3/safe-1 independently):
  n_forward_sessions_elapsed>=20 AND n_forward_real_bypass_entries>=20, counted only
  from 2026-09-04 onward (IN_SAMPLE_CUTOFF=2026-09-03 pinned in the script -- the
  2026-08-06..09-03 backfill is descriptive context, never judged). Below the bar the
  summary's status is ACCRUING and carries no route/no-route signal -- see the prereg
  file for the full frozen decision rule (day-clustered CI upper bound < 0 on the
  bypass cohort AND no named winning day loses > 10% of its own P&L to the bypass
  trades).

  17:20 ET weekdays = 15:20 MT (this box runs Mountain time; ET = local+2) -- 5 min
  behind Gamma_ConvictionC4Sidecar (17:10 ET), the last of this evening's money-leak
  audit fires. PT15M/PT30M self-heal repetition covers a missed single-daily-trigger
  fire (same remedy already shipped for the evening-window task family,
  EVENING-TASK-MISSED-RUN-SWEEP).

  WIRING (stdlib-only -- no pandas/numpy import anywhere in the worker script, verified
  this build; cloned from install-tp1-r50-forward-shadow.ps1's base-pythonw recipe
  rather than the venv-pythonw recipe, since no venv package is needed):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> fleet_gate_leak_shadow.py

  Output:
    analysis/recommendations/fleet-gate-leak-ledger.jsonl    append-only, dedup on
                                                               (core_tick_id, arm,
                                                               cohort, refused_account)
    analysis/recommendations/fleet-gate-leak-summary.json    gate x arm tables + this
                                                               clock's own forward-bar
                                                               health

  Per CLAUDE.md OP-3 ($0, pure Python stdlib over two already-written artifacts), OP-25
  (fail loud, never silent -- an error is returned in the summary dict, never
  swallowed), OP-33 (visibility is the product). Guard:
  backtest/tests/test_fleet_gate_leak_shadow_2026_09_03.py.
  REVOKE (whole instrument, one shot): Unregister-ScheduledTask
  -TaskName Gamma_FleetGateLeakShadow -Confirm:$false -- nothing on the trading path
  depends on this task (analysis-only leaf, same class as Gamma_LadderRungShadow).
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\fleet_gate_leak_shadow.py"
$taskName     = "Gamma_FleetGateLeakShadow"

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

# 15:20 MT (17:20 ET) weekdays -- -Weekly triggers come back with a null .Repetition CIM
# instance; steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround, same technique install-tp1-r50-forward-shadow.ps1 uses).
# PT15M/PT30M self-heal window on a missed single-daily fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "15:20"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "15:20" `
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
    -Description ("Weekdays 15:20 MT (17:20 ET), self-heals every 15 min for 30 min on a " + `
    "missed fire: joins core safe/bold verdicts x REAL fleet fills per core_tick_id " + `
    "(queue.md FLEET-GATE-LEAK-SHADOW) per the frozen prereg " + `
    "analysis/recommendations/prereg-fleet-gate-inheritance-2026-09-03.md. Per (tick, " + `
    "arm) real-fill outcome + FIFO P&L, using ONLY fills_fifo.mine_real_arm_fills (never " + `
    "a decisions.jsonl action-row count). Backfills 2026-08-06..build-date once, then " + `
    "accrues forward. SHADOW ONLY -- calls no trading-path function, places no order. " + `
    "`$0. Guard: backtest/tests/test_fleet_gate_leak_shadow_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_FleetGateLeakShadow -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- weekdays 15:20 MT (17:20 ET), self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
