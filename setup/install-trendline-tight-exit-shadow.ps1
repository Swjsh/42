#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_TrendlineTightExitShadow -- the $0 forward shadow that accrues evidence
  on kitchen cell A6's tightened TRENDLINE exit (queue.md TRENDLINE-TIGHT-EXIT-ACCRETE,
  MED), per the PRE-REGISTERED bar + decision rule in
  analysis/recommendations/prereg-trendline-tight-exit-shadow-2026-09-03.md.

.DESCRIPTION
  Cell A6_T-TIGHT_TR-TIGHT (premium_stop_pct -20% -> -12%, trail_pct 15% -> 10%, TRENDLINE-
  tier only) was the overnight kitchen's ONLY 4/4-gate cell and the best day-WR of any
  candidate (67.4%, n=95) -- but q=0.31 after the 83-cell portfolio BH correction. NOT a
  ship. The queue item's accrual path is a live shadow clock that scores the tightened exit
  against every real trendline-class fill going forward until the pre-registered bar clears.

  setup/scripts/trendline_tight_exit_shadow.py: nightly, for every CLOSED engine fill whose
  canonicalized setup (backtest/lib/setup_taxonomy.py) is a ribbon_ride entry AND whose
  trigger_level is None (the verified causal-at-entry proxy for the backtest's TRENDLINE
  tier), replays ONLY the exit under the tightened shape
  (backtest/lib/exit_manager_walk.walk_exit_manager, cached OPRA bars, walker defaults
  untouched) and compares it against that trade's REAL recorded broker P&L. Appends
  {date, arm, symbol, recorded_exit, shadow_exit, delta_pnl, sign_agree, bars_source} to
  analysis/recommendations/trendline-tight-exit-shadow-ledger.jsonl and rewrites
  -summary.json (n, n_skipped, sum/mean delta, a day-clustered bootstrap CI, top-3 share,
  sign_agreement, days_accrued). SHADOW ONLY -- never flips premium_stop_pct/trail_pct,
  never places an order, never touches strategies.py/params.json.

  ⛔ SIGN-ONLY CAVEAT ON DOLLARS: recorded_exit is REAL broker-truth; shadow_exit is a
  RE-SIMULATION over cached bars -- the pair is not apples-to-apples the way two paired
  simulated walks would be. delta_pnl's SIGN is the trustworthy read; its DOLLAR MAGNITUDE
  is not sizing-grade. Every summary this instrument writes carries a `dollar_caveat` field
  restating this, and the decision rule leans on `sign_agreement >= 0.85` as an independent,
  sign-safe gate alongside the (still-reported, still-caveated) dollar CI gate.

  Forward bar (frozen, cannot be softened after data arrives): days_accrued>=20 AND
  n_scored>=25. Below the bar the summary's status is ACCRUING and carries no ship/kill
  signal -- see the prereg file for the full decision rule (day-clustered CI lower bound > 0
  AND top-3 concentration < 50% AND sign_agreement >= 85%).

  ACCRUAL_START_DATE is pinned to this build's own date (2026-09-03) inside the script --
  NO BACKFILL, forward-only by construction (queue item: "going forward").

  16:45 ET weekdays = 14:45 MT (this box runs Mountain time; ET = local+2) -- 5 minutes
  after the sibling Gamma_Tp1R50ForwardShadow slot (16:40 ET) so the two nightly shadow
  clocks don't collide. PT15M/PT30M self-heal repetition covers a missed single-daily-
  trigger fire (same remedy already shipped for the evening-window task family,
  EVENING-TASK-MISSED-RUN-SWEEP / SINGLE-FIRE-TRIGGER-BLANKET-AUDIT).

  WIRING -- the worker script imports pandas (for the ribbon-warmup SPY frame, mirroring
  stop_mode_shadow_ledger.py), which the SYSTEM pythonw lacks (confirmed this build: `import
  pandas` -> ModuleNotFoundError under the system interpreter). Clones
  install-broker-fills.ps1's split-interpreter recipe instead of the plain
  install-tp1-r50-forward-shadow.ps1 base recipe (that sibling's worker is stdlib-only, this
  one is not):
    wscript -> run_exe_hidden.vbs -> SYSTEM pythonw -> run_cmd_hidden.py --cwd <repo>
      -- BACKTEST VENV pythonw (has pandas) -> trendline_tight_exit_shadow.py

  Output:
    analysis/recommendations/trendline-tight-exit-shadow-ledger.jsonl   append-only, dedup
                                                                         on activity_id
    analysis/recommendations/trendline-tight-exit-shadow-summary.json  this clock's own
                                                                        health + running
                                                                        totals

  Per CLAUDE.md OP-3 ($0, pure local computation over already-cached SIP + OPRA bars), OP-25
  (fail loud, never silent -- skipped fills are recorded with a reason, never dropped),
  OP-33 (visibility is the product). Guard:
  backtest/tests/test_trendline_tight_exit_shadow_2026_09_03.py.
  REVOKE (whole instrument, one shot): Unregister-ScheduledTask
  -TaskName Gamma_TrendlineTightExitShadow -Confirm:$false -- nothing on the trading path
  depends on this task (analysis-only leaf, same class as Gamma_Tp1R50ForwardShadow).
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$venvDir      = Join-Path $root "backtest\.venv"
$venvSitePkgs = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\trendline_tight_exit_shadow.py"
$taskName     = "Gamma_TrendlineTightExitShadow"

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

# 14:45 MT (16:45 ET) weekdays -- -Weekly triggers come back with a null .Repetition CIM
# instance; steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround, same technique install-fee-recalibrate.ps1 /
# install-tp1-r50-forward-shadow.ps1 use). PT15M/PT30M self-heal window on a missed fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:45"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "14:45" `
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
    -Description ("Weekdays 14:45 MT (16:45 ET), self-heals every 15 min for 30 min on a " + `
    "missed fire: the FORWARD shadow that accrues evidence on kitchen cell A6's tightened " + `
    "TRENDLINE exit (queue.md TRENDLINE-TIGHT-EXIT-ACCRETE) per the frozen prereg " + `
    "analysis/recommendations/prereg-trendline-tight-exit-shadow-2026-09-03.md. Per-trade " + `
    "delta of the tightened -12%/10% exit vs the REAL recorded broker P&L (SIGN-ONLY on " + `
    "dollars -- see prereg). NO BACKFILL -- accrual starts 2026-09-03. SHADOW ONLY -- " + `
    "flips nothing, places no order. `$0. Guard: " + `
    "backtest/tests/test_trendline_tight_exit_shadow_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_TrendlineTightExitShadow -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- weekdays 14:45 MT (16:45 ET), self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
