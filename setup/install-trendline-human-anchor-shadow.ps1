#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_TrendlineHumanAnchorShadow -- the $0 shadow instrument for the FROZEN
  rising-support "human anchor" trendline rule (queue
  TRENDLINE-RISING-SUPPORT-HUMAN-ANCHOR-SHADOW), per the pre-registered anchor rule,
  events, and decision rule in
  analysis/recommendations/prereg-trendline-rising-support-human-anchor-2026-09-03.md.

.DESCRIPTION
  T2 (trendline-today-exhibit.md) showed the repo's pivot-anchored detector could not
  construct J's own 2026-09-03 rising support line at the moment he drew it. T3
  (trendline-historical-study.md) then REFUTED the literal "first two confirmed pivot
  lows of the session" rule over 45 sessions -- but found J is not picking the
  chronologically-first two pivots: he picks "the low that ends the pre-move decline, and
  the first higher low after it," a DIFFERENT, untested hypothesis. This task is that
  hypothesis's frozen instrument.

  setup/scripts/trendline_human_anchor_shadow.py: nightly, backfills ONCE over every
  cached session (backtest/data/spy_sip_cache) -- A = the running minimum low of the
  session so far, B = the first confirmed swing-low pivot (window k=2) above A, at least
  6 bars after A on 5m / 2 bars on 15m; the line is a candidate the instant B confirms
  (no third touch required); re-anchors on a new lower low OR a break. Computes TOUCH /
  BREAK events with tolerance $0.20 (5m) / $0.30 (15m), outcome moves at 15/30/60-min
  horizons vs a time-of-day baseline, and a session-clustered bootstrap CI. Writes
  analysis/recommendations/trendline-human-anchor-ledger.jsonl (append-only, 3 row kinds,
  deduped per (date_et, bar_set, anchor_mode)) and -summary.json (per-config n_lines/
  n_touches/n_breaks, rates+CI vs baseline, mean moves+CI, top-3 concentration, decision
  block). SHADOW ONLY -- never wired to backtest/lib/filters.py or trendline_detector.py,
  never calls a broker, never places an order. No verdict is read before 2026-10-30 even
  if the forward bar (>=25 forward sessions, >=40 forward events) is met earlier -- see
  the prereg's hard date gate.

  Rows dated <=2026-09-03 are the one-time in-sample backfill (reported honestly, never
  counted toward the forward decision bar); only rows dated after that feed the forward
  gate. This differs from the tp1-r50 sibling clock (which is forward-only, no backfill)
  by explicit prereg design (section 6) -- the backfill here is a disclosed PRIOR, not
  accrual evidence.

  17:35 ET weekdays = 15:35 MT (this box runs Mountain time; ET = local+2). PT15M/PT30M
  self-heal repetition covers a missed single-daily-trigger fire (same remedy already
  shipped for the evening-window task family, EVENING-TASK-MISSED-RUN-SWEEP).

  WIRING (stdlib-only -- no pandas/numpy import anywhere in the worker script beyond the
  read-only crypto/lib/bar.py + crypto/lib/trendlines.py swing-point helpers, both pure
  Python, verified this build): cloned from install-tp1-r50-forward-shadow.ps1's base-
  system-pythonw recipe (NOT the venv-pythonw recipe -- no venv package is needed):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> trendline_human_anchor_shadow.py

  Output:
    analysis/recommendations/trendline-human-anchor-ledger.jsonl    append-only ledger
    analysis/recommendations/trendline-human-anchor-summary.json    per-config aggregates
                                                                     + decision block

  Per CLAUDE.md OP-3 ($0, pure Python stdlib + one read-only crypto/lib import over the
  cached SIP bars), OP-25 (fail loud -- a torn ledger line is skipped, never silently
  dropped without a trace; the input's own health is not separately tracked here since
  this instrument reads immutable historical cache files, not a live-fed ledger), OP-33
  (visibility is the product -- every session/config is a session_marker row, in_sample
  flagged honestly). Guard:
  backtest/tests/test_trendline_human_anchor_shadow_2026_09_03.py.

  REVOKE (whole instrument, one shot): Unregister-ScheduledTask
  -TaskName Gamma_TrendlineHumanAnchorShadow -Confirm:$false -- nothing on the trading
  path depends on this task (analysis-only leaf, same class as Gamma_LadderRungShadow /
  Gamma_Tp1R50ForwardShadow). This instrument is NEVER wired to live or paper trading,
  by prereg section 9 -- REVOKE here only stops the nightly clock, it does not "arm"
  anything by existing.

.NOTES
  NOT RUN THIS SESSION per the task's hard constraint (installers are written, never
  executed, during this kind of session). Verify manually with:
    Get-ScheduledTask -TaskName Gamma_TrendlineHumanAnchorShadow
  after a future session registers it.
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\trendline_human_anchor_shadow.py"
$taskName     = "Gamma_TrendlineHumanAnchorShadow"

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

# 15:35 MT (17:35 ET) weekdays -- -Weekly triggers come back with a null .Repetition CIM
# instance; steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround, same technique install-fee-recalibrate.ps1 /
# install-tp1-r50-forward-shadow.ps1 use). PT15M/PT30M self-heal window on a missed
# single-daily fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "15:35"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "15:35" `
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
    -Description ("Weekdays 15:35 MT (17:35 ET), self-heals every 15 min for 30 min on a " + `
    "missed fire: the shadow instrument for the FROZEN rising-support human-anchor rule " + `
    "per analysis/recommendations/prereg-trendline-rising-support-human-anchor-2026-09-03.md. " + `
    "A=running session-min low, B=first confirmed higher swing low (window k=2), line " + `
    "live the instant B confirms (no 3rd-touch gate). Backfills once over every cached " + `
    "session (in_sample flagged, never counted toward the forward bar); forward rows only " + `
    "feed the decision rule, and no verdict is read before 2026-10-30. SHADOW ONLY -- " + `
    "flips nothing, places no order, never wired to any live/paper trigger, ever. `$0. " + `
    "Guard: backtest/tests/test_trendline_human_anchor_shadow_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_TrendlineHumanAnchorShadow -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- weekdays 15:35 MT (17:35 ET), self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
