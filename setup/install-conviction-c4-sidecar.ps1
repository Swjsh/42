#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_ConvictionC4Sidecar -- the $0 shadow instrument for F4 CONVICTION C4
  CONTINUATION-POLARITY SIDECAR + FLEET COVERAGE
  (analysis/deep-research/2026-09-03-money/SYNTHESIS.md #F4, descended from H2
  range-extreme-dead.md), per the PRE-REGISTERED bar + decision rule in
  analysis/recommendations/prereg-conviction-c4-continuation-polarity-2026-09-03.md.

.DESCRIPTION
  conviction.py's C4 `range_extreme` component is a proven DEAD KNOB (H2: 0/482+ post-fix
  hit rate) -- not a coding bug but a POLARITY mismatch: C4 was calibrated on a
  mean-reversion exhibit while the live trigger family (RIDE_THE_RIBBON, 100% of scored
  rows) is continuation-shaped. conviction.py is FROZEN through 2026-10-30 and stays
  untouched -- this task builds the sidecar that re-scores the SAME rows off to the side
  with C4's polarity flipped, plus closes H2's OTHER finding (zero conviction coverage on
  the four fleet arms) by recomputing range_position from the cached SPY tape for fleet
  PLACED rows.

  setup/scripts/conviction_c4_sidecar.py: nightly, re-scores every post-fix core-decisions
  conviction row (re-deriving `total` from STORED components, never re-invoking
  score_conviction()) AND every placed fleet-ledger row (recomputing range_position from
  backtest/data/spy_sip_cache/spy_1m_<date>.json, no look-ahead) under both C4 polarities.
  Appends to analysis/recommendations/conviction-c4-sidecar-ledger.jsonl (idempotent, dedup
  on arm+account+ts_et) and rewrites -summary.json (per-arm + book-wide would_block rates,
  flips, outcome join to real fills with a day-clustered bootstrap CI, top-3 concentration,
  the four-big-days check). SHADOW ONLY -- conviction.py is never imported for write, never
  monkeypatched; there is no SKIP_LOW_CONVICTION branch in the engine and this task does not
  add one.

  Forward bar (frozen): >=20 sessions AND >=60 scored core rows AND >=60 scored fleet rows.
  Below the bar the summary's status is ACCRUING and decision_rule values are visible but
  carry no verdict -- see the prereg file for the full frozen decision rule (book-wide
  would_block cohort CI-upper < 0 under continuation polarity AND all four named big winning
  days' entries stay would_allow).

  17:10 ET weekdays = 15:10 MT (this box runs Mountain time; ET = local+2) -- clear of the
  15:55 ET EOD-flatten fire and the 16:40 ET tp1-r50/ladder-rung shadow slot, matching the
  sibling shadow clocks' after-close cadence. PT15M/PT30M self-heal repetition covers a
  missed single-daily-trigger fire (same remedy the evening-window task family already
  ships, EVENING-TASK-MISSED-RUN-SWEEP).

  WIRING (stdlib-only -- no pandas/numpy import anywhere in the worker script, verified this
  build; cloned from install-tp1-r50-forward-shadow.ps1's base-pythonw recipe):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> conviction_c4_sidecar.py

  Output:
    analysis/recommendations/conviction-c4-sidecar-ledger.jsonl    append-only, dedup on
                                                                    arm+account+ts_et
    analysis/recommendations/conviction-c4-sidecar-summary.json    this shadow's own health +
                                                                    running per-arm totals

  Per CLAUDE.md OP-3 ($0, pure Python stdlib over already-written artifacts + one cached
  SPY tape read), OP-25 (fail loud, never silent -- a date with no cached tape is recorded
  with a skip_reason, never dropped silently), OP-33 (visibility is the product). Guard:
  backtest/tests/test_conviction_c4_sidecar_2026_09_03.py.
  REVOKE (whole instrument, one shot): Unregister-ScheduledTask
  -TaskName Gamma_ConvictionC4Sidecar -Confirm:$false -- nothing on the trading path
  depends on this task (analysis-only leaf, same class as Gamma_LadderRungShadow /
  Gamma_Tp1R50ForwardShadow); conviction.py is never touched.
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\conviction_c4_sidecar.py"
$taskName     = "Gamma_ConvictionC4Sidecar"

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

# 15:10 MT (17:10 ET) weekdays -- -Weekly triggers come back with a null .Repetition CIM
# instance; steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround, same technique install-tp1-r50-forward-shadow.ps1 uses).
# PT15M/PT30M self-heal window on a missed single-daily fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "15:10"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "15:10" `
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
    -Description ("Weekdays 15:10 MT (17:10 ET), self-heals every 15 min for 30 min on a " + `
    "missed fire: F4 CONVICTION C4 CONTINUATION-POLARITY SIDECAR + FLEET COVERAGE per the " + `
    "frozen prereg " + `
    "analysis/recommendations/prereg-conviction-c4-continuation-polarity-2026-09-03.md. " + `
    "Re-scores post-fix core-decisions conviction rows (re-derived total, never re-invokes " + `
    "score_conviction()) AND placed fleet-ledger rows (range_position off the cached SPY " + `
    "tape, no look-ahead) under LIVE vs CONTINUATION C4 polarity. conviction.py stays " + `
    "FROZEN and untouched. SHADOW ONLY -- gates nothing, places no order. `$0. Guard: " + `
    "backtest/tests/test_conviction_c4_sidecar_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_ConvictionC4Sidecar -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- weekdays 15:10 MT (17:10 ET), self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
