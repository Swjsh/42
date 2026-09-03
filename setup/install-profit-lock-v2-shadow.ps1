#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_ProfitLockV2Shadow -- the $0 forward counterfactual shadow that adjudicates
  the PROFIT-LOCK V2 candidate (F1 profit-lock-v2-shadow, filed 2026-09-03), per the
  PRE-REGISTERED bar + decision rule in
  analysis/recommendations/prereg-profit-lock-v2-forward-shadow-2026-09-03.md.

.DESCRIPTION
  Descends from analysis/deep-research/2026-09-03-money/profit-lock-scope.md's H4 finding:
  arming the pre-TP1 chandelier profit-lock on ANY +5% favorable tick (profit_lock_
  arm_scope='full') is a MIXED result -- real but thin on the one arm this codebase trusts
  (safe-2), NOT recency-stable, and truncates 3 of 4 named big winning days to a combined
  -$880.90 (two trades cut to exactly $0). H4's own conclusion named a narrower candidate as
  the next step and required it be pre-registered against genuinely forward, not-yet-seen
  data -- this task and its prereg are that follow-up.

  setup/scripts/profit_lock_v2_shadow.py: nightly, for every CLOSED engine-attributed option
  fill (analysis/entry-quality/entry-quality-ledger.json, all 6 arms) on/after
  FORWARD_START_DATE=2026-09-03, replays CONTROL (canonical_shape(date), today's live
  'post_tp1' behaviour, unmodified production exit_manager.plan_exit_actions) against
  TREATMENT (profit_lock_arm_scope='full', profit_lock_arm_pct=0.20 instead of the live
  0.05, PLUS an additional 10-minute minimum-time-in-trade gate implemented ONLY in this
  script's own walker wrapper -- exit_manager.py itself has no such knob; see the script's
  and prereg's docstrings). ALSO backfills the 2026-06-26..2026-09-02 history ONCE on first
  run as a disclosed in_sample=true prior (never counted toward the forward bar or decision).
  Appends analysis/recommendations/profit-lock-v2-shadow-ledger.jsonl (dedup on activity_id)
  and rewrites -summary.json (per-arm sums, safe-2 trusted bootstrap CI on FORWARD rows only,
  the chronological recent-quarter delta, the four named big-day deltas, the 2026-08-04
  SPY260804C00769000 runner delta, bar/status). SHADOW ONLY -- never flips a live knob, never
  places an order, never touches strategies.py/accounts.json/params.json (read-only imports).

  Forward bar (frozen, cannot be softened after data arrives): >=20 forward trading sessions
  (any arm) AND >=25 forward safe-2 scored fills. Below the bar the summary's status is
  ARMED_AWAITING_FILLS or ACCRUING and carries no ship/kill signal -- see the prereg for the
  full 4-condition decision rule. NOTHING SHIPS BEFORE 2026-10-30 (config freeze) regardless
  of what this ledger ever reads, and even past that date the live min-time-in-trade knob
  this candidate needs does not exist yet and is a separate build item.

  16:55 ET weekdays = 14:55 MT (this box runs Mountain time; ET = local+2) -- after the
  16:40 ET Gamma_Tp1R50ForwardShadow / Gamma_LadderRungShadow / Gamma_LossArmedBudgetShadow
  slot, so entry-quality-ledger.json's own nightly refresh (which those sibling clocks also
  depend on) has had a few extra minutes to land before this one reads it. PT15M/PT30M
  self-heal repetition covers a missed single-daily-trigger fire (same remedy already shipped
  for the evening-window task family, EVENING-TASK-MISSED-RUN-SWEEP).

  WIRING (stdlib + pandas -- this script imports pandas transitively via
  pdt_blocked_counterfactual.py / exit_manager_walk.py, so it runs under the BACKTEST VENV
  pythonw both as the outer wscript target AND the inner call -- same recipe as the sibling
  F3 retest-zone-shadow task filed the same night (install-retest-zone-shadow.ps1), not the
  sysPythonw-outer/venvPythonw-inner recipe older stdlib+pandas tasks used):
    wscript -> run_exe_hidden.vbs -> backtest venv pythonw -> run_cmd_hidden.py --cwd <repo>
      -- backtest venv pythonw -> profit_lock_v2_shadow.py

  No --env override needed: the script resolves its own absolute sys.path entries at import
  time (REPO = Path(__file__).resolve().parents[2], mirroring pdt_blocked_counterfactual.py
  / money_profit_lock_scope.py) rather than depending on a PYTHONPATH/cwd convention.

  Measured wall time this build, full 438-trade backfill: 39.02s (well under the 4-minute
  budget; a forward-only nightly increment is a handful of new trades and takes seconds --
  idempotent re-run against an already-scored population measured at 3.35s).

  Output:
    analysis/recommendations/profit-lock-v2-shadow-ledger.jsonl   append-only, dedup on
                                                                    activity_id
    analysis/recommendations/profit-lock-v2-shadow-summary.json   this clock's own health +
                                                                    running totals + decision
                                                                    condition readout

  Per CLAUDE.md OP-3 ($0, local replay over already-written cached bars + JSON artifacts),
  OP-25 (fail loud -- skipped trades are recorded with a reason, never dropped silently),
  OP-33 (visibility is the product). Guard:
  backtest/tests/test_profit_lock_v2_shadow_2026_09_03.py.
  REVOKE (whole instrument, one shot): Unregister-ScheduledTask
  -TaskName Gamma_ProfitLockV2Shadow -Confirm:$false -- nothing on the trading path depends
  on this task (analysis-only leaf, same class as Gamma_Tp1R50ForwardShadow).

  ⛔ NOT RUN BY THE AUTHORING SESSION. Per this build's hard constraints, this installer is
  written and left for a session with Register-ScheduledTask authority to execute.
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$venvPythonw  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$venvDir      = Join-Path $root "backtest\.venv"
$venvSitePkgs = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\profit_lock_v2_shadow.py"
$taskName     = "Gamma_ProfitLockV2Shadow"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

foreach ($p in @($vbs, $sysPythonw, $venvPythonw, $venvSitePkgs, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# 2026-09-03 VENV-PYTHONW-REDIRECTS-TO-CONSOLE-PYTHON recipe (a): BOTH outer and inner
# target changed from $venvPythonw to $sysPythonw (base install pythonw), venv activated
# via --env instead -- see install-fee-recalibrate.ps1's WIRING comment for the full root
# cause. This installer previously used venv pythonw on BOTH hops (the doubly-leaking
# shape), so both are converted here.
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" " + `
    "--env VIRTUAL_ENV=`"$venvDir`" --env PYTHONPATH=`"$venvSitePkgs`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 14:55 MT (16:55 ET) weekdays -- -Weekly triggers come back with a null .Repetition CIM
# instance; steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround, same technique install-tp1-r50-forward-shadow.ps1 uses).
# PT15M/PT30M self-heal window on a missed single-daily fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:55"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "14:55" `
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
    -Description ("Weekdays 14:55 MT (16:55 ET), self-heals every 15 min for 30 min on a " + `
    "missed fire: the FORWARD counterfactual shadow that adjudicates the profit-lock V2 " + `
    "candidate (arm_scope=full, arm_pct=0.20, wrapper-only 10-min mask) per the frozen " + `
    "prereg analysis/recommendations/prereg-profit-lock-v2-forward-shadow-2026-09-03.md. " + `
    "Also backfills 2026-06-26..2026-09-02 ONCE as a disclosed in_sample=true prior on " + `
    "first run. SHADOW ONLY -- flips no live knob, places no order. `$0. Guard: " + `
    "backtest/tests/test_profit_lock_v2_shadow_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_ProfitLockV2Shadow -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- weekdays 14:55 MT (16:55 ET), self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
