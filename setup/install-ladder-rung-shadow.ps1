#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_LadderRungShadow -- the $0 nightly forward clock for the HELD
  SCORE-LADDER-RUNG patch (LANE 1, single-demerit, bull-only, rungs risky-3=7/risky-1=8;
  prereg a780122e, runner 3b3072a9).

.DESCRIPTION
  2026-08-07 evening HOLD decision (analysis/deep-research/CLOSE-EXECUTION-2026-08-07.md):
  the frozen ship gate's week-added stayed positive (+$1,866 = Mon-Thu's real +$2,811 plus
  Friday's real -$945) but Friday was materially WORSE under the ladder than without it
  (binary_day_pnl +$80 vs ladder_day_pnl -$865 for the SAME arms/day -- a $945 same-day
  swing on the week's highest rescue-admission count, 57) -- so the patch is HELD, not
  applied. accounts.json carries no score_ladder_rung key; production stays byte-identical
  binary tonight.

  This task changes NOTHING on the live trading path. It fires once daily after close,
  replays LANE 1's exact frozen admission rule against that day's REAL core-decisions
  ledger + REAL OPRA bars (never EST), and appends one row per LANE-1 arm to
  analysis/arm-ladder/ladder-rung-shadow-ledger.jsonl. Forward re-decision bar (>=10
  sessions, extras net>0, no session worse than -$500, negative-session avg no worse than
  -$300) is recorded in the worker script's own docstring/FORWARD_BAR dict.

  16:40 ET weekdays = 14:40 MT (this box is Mountain; ET = local+2) -- 5 minutes after the
  spy_5m cache typically lands (~16:16 ET) and comfortably after same-day OPRA unlocks
  (~16:21 ET), mirroring LANE 2's own analogous (still-unregistered) shadow instrument's
  cadence -- named separately here on purpose so this file registers exactly one task name.

  Zero-leak chain per L42/C8 (mirrors install-regime-stamp.ps1):
      wscript //nologo run_exe_hidden.vbs <backtest-venv pythonw> score_ladder_rung_shadow_nightly.py
  Analysis-only: writes ONLY under analysis/arm-ladder/. No accounts.json read/write, no
  order placement, no config mutation -- guarded by
  backtest/tests/test_score_ladder_rung_shadow_nightly.py
  (test_module_source_never_touches_a_live_order_or_config_surface).

  Per CLAUDE.md OP-25 (fail loud) + OP-3 ($0). To disable:
  Unregister-ScheduledTask -TaskName Gamma_LadderRungShadow -Confirm:$false
  REVERT (of this whole instrument, one shot): delete this task registration + delete
  backtest/tools/score_ladder_rung_shadow_nightly.py + its guard test + this installer --
  nothing else in the repo depends on it (analysis-only leaf).
#>

# 2026-08-18: routed via run_py_venv_hidden.py (2026-08-13 console-leak fix). Also closes
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT via self_check.check_run_py_venv_hidden_masked_exit()
# (evidence live 2026-08-17: score_ladder_rung_shadow_nightly.py exit=0 in
# run-py-venv-hidden-2026-08-17.log). Live state was already on this wiring (2026-08-13
# imperative patch); this template was drifted (CryptoTwin-class regression) until now.
$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_LadderRungShadow"

# System pythonw (GUI-subsystem, windowless) + run_py_venv_hidden.py puts the backtest
# venv's site-packages on PYTHONPATH so pandas/numpy still resolve.
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $sysPythonw)) {
    Write-Error "system pythonw not found at $sysPythonw"
    exit 1
}

$runExeHidden    = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$runPyVenvHidden = Join-Path $ScriptsDir "run_py_venv_hidden.py"
$worker          = Join-Path $WorkDir "backtest\tools\score_ladder_rung_shadow_nightly.py"

foreach ($p in @($runExeHidden, $runPyVenvHidden, $worker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <sys-pythonw> run_py_venv_hidden.py <...nightly.py>
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runPyVenvHidden`" `"$worker`""

# 14:40 LOCAL (Mountain) = 16:40 ET weekdays -- after spy_5m cache lands (~16:16 ET) and
# same-day OPRA unlocks (~16:21 ET). Weekdays only (0DTE has nothing to tally on weekends).
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:40"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "SCORE-LADDER-RUNG (LANE 1, prereg a780122e) $0 forward shadow clock after the 2026-08-07 HOLD decision -- CLOSE-EXECUTION-2026-08-07.md. Replays the frozen bull-only rung-7/8 admission rule against real core-decisions + real OPRA nightly, appends to analysis/arm-ladder/ladder-rung-shadow-ledger.jsonl. Zero trading-path effect -- analysis-only, no accounts.json touch, no order placement. Hidden wscript->venv-pythonw chain."

Write-Output "OK: Registered $TaskName for 14:40 MT (16:40 ET) weekdays on the hidden chain"
Write-Output "    Worker:  $worker"
Write-Output "    Ledger:  analysis\arm-ladder\ladder-rung-shadow-ledger.jsonl"
Write-Output "    Test:    Start-ScheduledTask -TaskName $TaskName"
