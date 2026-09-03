#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_ReleaseBlackoutShadow -- the $0 forward shadow that accrues evidence for
  the SCHEDULED-RELEASE BLACKOUT candidates (R1/R3; R2 is a comparison arm only), per the
  PRE-REGISTERED bar + decision rule in
  analysis/recommendations/prereg-scheduled-release-blackout-2026-09-03.md.

.DESCRIPTION
  `backtest/tools/release_gap_study.py`'s historical read (44 cached trading days
  2026-06-26..2026-09-02 + today's real fills) found NONE of R1/R2/R3 clears "net >= 0 after
  drop-best-day" with real (multi-day) evidence -- R1 and R3 each rest on a single trading
  day's worth of correlated legs, R2 (comparison-only, never ship-eligible) fails outright
  once its one positive day is dropped. The prereg's DO-NOT rules out re-testing that same
  (already-seen) data -- the only clean path is a forward shadow scored on release days
  nobody has seen yet, exactly the two-DO-NOT contract install-tp1-r50-forward-shadow.ps1's
  own sibling instrument states.

  setup/scripts/release_blackout_shadow.py: nightly, for every ISM (tier-1) release day
  on/after ACCRUAL_START_DATE=2026-09-03 whose session is complete, logs (a) the SPY $ /
  option % moves across the 10:00 ET window from whichever cache has the data that night
  (highres 1-min bars once archived, else the quote-tape's own adjacent-poll gap inside a
  [09:55,10:05) window, else honestly "no_data" -- informational only) and (b) what R1
  ([09:45,10:05) entry blackout), R2 ([09:35,10:05), comparison-only) and R3 (R1 + flatten
  any open position at 09:58 ET, kill-type) would have done to that day's REAL fills
  (automation/state/fills-ledger.jsonl). Appends to
  analysis/recommendations/release-blackout-shadow-ledger.jsonl and rewrites -summary.json
  (n_ism_release_days_accrued, n_days_meeting_15pct_adverse_threshold, per-rule totals, a
  day-clustered bootstrap CI, drop-best-day, ship_verdict). SHADOW ONLY -- never blocks a
  live entry, never places an order, never touches automation/state/params.json or any
  frozen trading-path file (read-only imports of macro_calendar.py and
  backtest/tools/release_gap_study.py only).

  ⛔ NO LOOK-AHEAD BY CONSTRUCTION: the function that decides which trades R1/R2/R3 touch
  (`_apply_rules_for_date`) takes no move/gap parameter at all -- it reads only the release
  CALENDAR (known premarket) and each position's own entry timestamp, never the release's
  realized size. Guarded by `test_release_blackout_shadow_2026_09_03.py::
  test_apply_rules_signature_carries_no_move_parameter` +
  `test_apply_rules_result_identical_whether_or_not_moves_were_ever_computed`.

  Forward bar (frozen, cannot be softened after data arrives): >=3 ISM release days accrued
  AND >=2 of those >=3 days show a >=15% adverse 1-minute option move inside the blackout
  window. Below the bar the summary's status is ACCRUING and each rule's ship_verdict is
  BAR_NOT_MET -- see the prereg file for the full decision rule (ex-best-day net >= 0, no
  named big winning day loses >10% of its P&L, R2 is NEVER ship-eligible regardless of its
  numbers). ACCRUAL_START_DATE is pinned to this build's own date (2026-09-03) inside the
  script -- NO BACKFILL; today is itself an ISM day, so the first scheduled run already
  contributes real forward evidence.

  17:15 ET weekdays = 15:15 MT (this box runs Mountain time; ET = local+2) -- after the
  15:55 ET EOD flatten and Gamma_EodFlatten, so every session it processes is fully closed.
  PT15M/PT30M self-heal repetition covers a missed single-daily-trigger fire (same remedy
  Gamma_Tp1R50ForwardShadow / EVENING-TASK-MISSED-RUN-SWEEP already use).

  WIRING (stdlib-only -- no pandas/numpy import anywhere in the worker script, verified this
  build; cloned from install-tp1-r50-forward-shadow.ps1's base-pythonw recipe):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> release_blackout_shadow.py

  Output:
    analysis/recommendations/release-blackout-shadow-ledger.jsonl   append-only, dedup on date_et
    analysis/recommendations/release-blackout-shadow-summary.json   this clock's own health +
                                                                      running totals + ship_verdict

  Per CLAUDE.md OP-3 ($0, pure Python stdlib over already-cached files), OP-25 (fail loud,
  never silent -- excluded positions are recorded with a reason, never dropped silently),
  OP-33 (visibility is the product). Guard:
  backtest/tests/test_release_blackout_shadow_2026_09_03.py (28 tests).
  REVOKE (whole instrument, one shot): Unregister-ScheduledTask
  -TaskName Gamma_ReleaseBlackoutShadow -Confirm:$false -- nothing on the trading path
  depends on this task (analysis-only leaf, same class as Gamma_Tp1R50ForwardShadow).

  ⛔ THIS INSTALLER IS NOT RUN AS PART OF TASK B2 -- the task explicitly says "do NOT run
  it". It is committed so a later session (or J) can register the task deliberately.
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\release_blackout_shadow.py"
$taskName     = "Gamma_ReleaseBlackoutShadow"

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

# 15:15 MT (17:15 ET) weekdays -- -Weekly triggers come back with a null .Repetition CIM
# instance; steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround, same technique install-tp1-r50-forward-shadow.ps1 uses).
# PT15M/PT30M self-heal window on a missed single-daily fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "15:15"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "15:15" `
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
    -Description ("Weekdays 15:15 MT (17:15 ET), self-heals every 15 min for 30 min on a " + `
    "missed fire: the FORWARD shadow that accrues evidence for the scheduled-release " + `
    "blackout candidates (R1/R3; R2 comparison-only) per the frozen prereg " + `
    "analysis/recommendations/prereg-scheduled-release-blackout-2026-09-03.md. Logs the " + `
    "10:00 ET window's SPY/option moves (informational) and what each rule would have done " + `
    "to that ISM day's REAL fills, using ONLY the release calendar + each trade's own entry " + `
    "timestamp to decide rule membership -- never the release's realized size (no look-" + `
    "ahead). NO BACKFILL -- accrual starts 2026-09-03. SHADOW ONLY -- flips nothing, blocks " + `
    "no live entry, places no order. `$0. Guard: " + `
    "backtest/tests/test_release_blackout_shadow_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_ReleaseBlackoutShadow -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- weekdays 15:15 MT (17:15 ET), self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
