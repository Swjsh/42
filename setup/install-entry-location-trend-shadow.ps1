#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_EntryLocationTrendShadow -- the $0 F2 ENTRY-LOCATION x TREND-QUALITY shadow
  ledger (slug F2-entry-location-trend), per the frozen prereg
  analysis/recommendations/prereg-entry-location-trend-2026-09-03.md.

.DESCRIPTION
  setup/scripts/entry_location_trend_shadow.py: nightly, for every engine fill in
  analysis/pain-ledger/mae-mfe.json (all 6 SPY-option arms, full backfilled history, no date
  cutoff), appends one row to
  analysis/recommendations/entry-location-trend-ledger.jsonl carrying range_position (H1's
  own formula, reused via import from backtest/tools/money_entry_location.py) plus four
  entry-time trend-quality co-signals computed from the SAME no-lookahead
  core-decisions.jsonl prefix: minutes since the ribbon stack last flipped to the trade
  direction, minutes since htf_15m last matched the trade direction, opening-range extension
  ($ and multiples of the 09:30-09:45 range), and vix/vix_dir at entry. Rewrites
  analysis/recommendations/entry-location-trend-summary.json (n per setup, chase-vs-rest with
  bootstrap CI, the same split stratified by each co-signal tercile, plus a diagnostic preview
  of the frozen prereg cut). SHADOW ONLY -- never flips a knob, never places an order, never
  touches accounts.json/strategies.py/any trading-path file (read-only imports of
  money_entry_location.py / money_entry_location_stats.py only).

  Descriptive, status ARMED. The ONE pre-registered test (BULLISH_RECLAIM_RIDE_THE_RIBBON
  chase-vs-rest conditioned on minutes_since_ribbon_flip, evaluated once n_chase>=150 for that
  setup) is expansion-class -- no proposal, no gate, nothing live before 2026-10-30 regardless
  of what the nightly summary shows. See the prereg file's section 6 for full disclosure.

  17:00 ET weekdays = 15:00 MT (this box runs Mountain time; ET = local+2) -- PT15M/PT30M
  self-heal repetition covers a missed single-daily-trigger fire (same remedy already shipped
  for the evening-window task family, EVENING-TASK-MISSED-RUN-SWEEP, and reused verbatim by
  the sibling Gamma_Tp1R50ForwardShadow installer this file is modeled on).

  WIRING (venv-pythonw recipe -- this worker imports money_entry_location_stats.py, which
  imports numpy; system Python313 has no numpy, backtest\.venv does -- same reasoning as
  install-ema-snapshot.ps1's own venv-pythonw chain, NOT the tp1_r50 sibling's stdlib-only
  system-pythonw chain):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- backtest-venv pythonw -> entry_location_trend_shadow.py

  Output:
    analysis/recommendations/entry-location-trend-ledger.jsonl    append-only, dedup on
                                                                    row_id (arm::symbol::
                                                                    entry_ts_utc)
    analysis/recommendations/entry-location-trend-summary.json    n per setup, chase-vs-rest
                                                                    CI, co-signal tercile
                                                                    splits, prereg diagnostic

  Per CLAUDE.md OP-3 ($0, pure Python over two already-written artifacts), OP-25 (fail loud --
  skipped rows are recorded with a reason, never dropped silently), OP-33 (visibility is the
  product). Guard: backtest/tests/test_entry_location_trend_shadow_2026_09_03.py.
  REVOKE (whole instrument, one shot): Unregister-ScheduledTask
  -TaskName Gamma_EntryLocationTrendShadow -Confirm:$false -- nothing on the trading path
  depends on this task (analysis-only leaf, same class as Gamma_LadderRungShadow /
  Gamma_Tp1R50ForwardShadow).
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$venvDir      = Join-Path $root "backtest\.venv"
$venvSitePkgs = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\entry_location_trend_shadow.py"
$taskName     = "Gamma_EntryLocationTrendShadow"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

foreach ($p in @($vbs, $sysPythonw, $venvSitePkgs, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# 2026-09-03 VENV-PYTHONW-REDIRECTS-TO-CONSOLE-PYTHON recipe (a): inner target changed
# from $venvPythonw to $sysPythonw (base install pythonw), venv activated via --env
# instead -- see install-fee-recalibrate.ps1's WIRING comment for the full root cause.
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" " + `
    "--env VIRTUAL_ENV=`"$venvDir`" --env PYTHONPATH=`"$venvSitePkgs`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 15:00 MT (17:00 ET) weekdays -- -Weekly triggers come back with a null .Repetition CIM
# instance; steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround, same technique install-tp1-r50-forward-shadow.ps1 uses).
# PT15M/PT30M self-heal window on a missed single-daily fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "15:00"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "15:00" `
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
    -Description ("Weekdays 15:00 MT (17:00 ET), self-heals every 15 min for 30 min on a " + `
    "missed fire: F2 ENTRY-LOCATION x TREND-QUALITY shadow ledger per the frozen prereg " + `
    "analysis/recommendations/prereg-entry-location-trend-2026-09-03.md. Appends one row " + `
    "per engine fill (all arms, full backfilled history) with range_position + 4 " + `
    "no-lookahead trend-quality co-signals (ribbon-flip minutes, htf_15m-match minutes, " + `
    "opening-range extension, vix/vix_dir). SHADOW ONLY -- flips nothing, places no order, " + `
    "expansion-class (no live action before 2026-10-30). `$0. Guard: " + `
    "backtest/tests/test_entry_location_trend_shadow_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_EntryLocationTrendShadow -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- weekdays 15:00 MT (17:00 ET), self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
