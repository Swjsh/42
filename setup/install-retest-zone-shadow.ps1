#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_RetestZoneShadow -- the $0 F3 RETEST ZONE-WIDTH GRID + ZONE-WIDTH
  PERSISTENCE shadow that adjudicates the retest-entry variant (H10,
  analysis/deep-research/2026-09-03-money/retest-entry-variant.md), per the PRE-REGISTERED
  bar + decision rule in
  analysis/recommendations/prereg-retest-zone-grid-2026-09-03.md.

.DESCRIPTION
  H10 found the aggregate sign of a retest-entry variant of ribbon_ride flips depending on
  the retest zone's width -- a parameter the project could not previously pin down from
  history (no archived key-levels.json snapshot in the study window carries a zone_width
  field). The prereg's two deliverables: (1) a per-trade zone-width RESOLVER that persists
  which width was actually in force (from the dated archive when available, else the $0.30
  default, flagged), and (2) the frozen GRID {0.20, 0.30, 0.40, 0.50, 0.75} scored alongside
  it, disclosure-only, never pickable after reading results.

  setup/scripts/retest_zone_shadow.py: nightly, for every CLOSED RIDE_THE_RIBBON entry (all
  arms), resolves the zone width in force for its trigger level from the archived
  journal/key-levels-archive/key-levels-<date>.json snapshot (default $0.30, flagged
  zone_source='default', when no snapshot/level/zone_width exists -- true for 100% of the
  current archive, see the prereg's Step 1 finding), walks BOTH the actual breakout entry and
  the retest variant (at every grid width AND the in-force width) through the REAL production
  exit code (backtest.lib.exit_manager_walk.walk_exit_manager, via
  backtest/tools/money_retest_entry_variant.py -- reused by import, never modified). Appends
  to analysis/recommendations/retest-zone-shadow-ledger.jsonl and rewrites -summary.json
  (per-width n_confirmed, actual vs retest totals, safe-2-trusted delta with a day-clustered
  bootstrap CI, sign-only for every other arm, per-VIX-band split, the four named big days).
  SHADOW ONLY -- flips no knob, proposes no default, places no order, never touches any
  trading-path file (config freeze through 2026-10-30, per CLAUDE.md).

  Backfill: run ONCE at build time against the full existing history (200 entries,
  2026-07-13..2026-09-02, all tagged in_sample:true). Every trade dated on/after this build's
  own FREEZE_DATE (2026-09-03) processed by a LATER run is tagged in_sample:false (forward,
  judged data) -- deterministic on the trade's own date, not on run timing.

  Forward bar (frozen, cannot be softened after data arrives): >=20 forward trading sessions
  AND >=40 forward signals. Below the bar the summary's status is ACCRUING and carries no
  ship/kill signal -- see the prereg file for the full decision rule (safe-2-trusted
  day-clustered CI lower bound > 0 at the in-force width, AND no named big-winner day flips
  sign at the in-force width; the grid columns are disclosure only).

  17:05 ET weekdays = 15:05 MT (this box runs Mountain time; ET = local+2) -- after the
  15:55 ET EOD flatten and the entry-quality-ledger's own nightly refresh, so this shadow
  always reads a same-day-complete population. PT15M/PT30M self-heal repetition covers a
  missed single-daily-trigger fire (same remedy already shipped for the evening-window task
  family, EVENING-TASK-MISSED-RUN-SWEEP, and reused verbatim by
  Gamma_Tp1R50ForwardShadow / Gamma_LadderRungShadow).

  WIRING (stdlib + pandas -- pandas IS needed here, unlike tp1_r50_forward_shadow.py, because
  this script imports backtest/tools/money_retest_entry_variant.py for the walker/retest
  logic; cloned from a venv-pythonw recipe, not the stdlib-only base-pythonw recipe):
    wscript -> run_exe_hidden.vbs -> backtest venv pythonw -> run_cmd_hidden.py --cwd <repo>
      -- backtest venv pythonw -> retest_zone_shadow.py

  Output:
    analysis/recommendations/retest-zone-shadow-ledger.jsonl   append-only, dedup on
                                                                 activity_id
    analysis/recommendations/retest-zone-shadow-summary.json   this clock's own health +
                                                                 running totals per width

  Per CLAUDE.md OP-3 ($0, pure local computation over cached bars + already-written
  artifacts), OP-25 (fail loud, never silent -- skipped trades are recorded with a reason,
  never dropped silently), OP-33 (visibility is the product). Guard:
  backtest/tests/test_retest_zone_shadow_2026_09_03.py.
  REVOKE (whole instrument, one shot): Unregister-ScheduledTask
  -TaskName Gamma_RetestZoneShadow -Confirm:$false -- nothing on the trading path depends on
  this task (analysis-only leaf, same class as Gamma_LadderRungShadow /
  Gamma_Tp1R50ForwardShadow).

  ⛔ NOT RUN BY THE AUTHORING SESSION. Per this build's hard constraints, this installer is
  written and left for a session with Register-ScheduledTask authority to execute.
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$venvPythonw  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\retest_zone_shadow.py"
$taskName     = "Gamma_RetestZoneShadow"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

foreach ($p in @($vbs, $venvPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$venvPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$venvPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 15:05 MT (17:05 ET) weekdays -- -Weekly triggers come back with a null .Repetition CIM
# instance; steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround, same technique install-fee-recalibrate.ps1 /
# install-tp1-r50-forward-shadow.ps1 both use). PT15M/PT30M self-heal window on a missed
# single-daily fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "15:05"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "15:05" `
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
    -Description ("Weekdays 15:05 MT (17:05 ET), self-heals every 15 min for 30 min on a " + `
    "missed fire: F3 RETEST ZONE-WIDTH GRID + ZONE-WIDTH PERSISTENCE shadow (descends from " + `
    "H10 retest-entry-variant.md) per the frozen prereg " + `
    "analysis/recommendations/prereg-retest-zone-grid-2026-09-03.md. Resolves the zone width " + `
    "in force per trade from the archived key-levels snapshot (default `$0.30 when absent -- " + `
    "true for the entire archive today), scores the retest variant at the frozen grid AND " + `
    "the in-force width through the REAL production exit code. Backfilled once " + `
    "(in_sample:true); forward rows (in_sample:false) accrue from FREEZE_DATE 2026-09-03 " + `
    "onward. SHADOW ONLY -- flips nothing, places no order, touches no trading-path file " + `
    "(config freeze through 2026-10-30). `$0. Guard: " + `
    "backtest/tests/test_retest_zone_shadow_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_RetestZoneShadow -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- weekdays 15:05 MT (17:05 ET), self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
