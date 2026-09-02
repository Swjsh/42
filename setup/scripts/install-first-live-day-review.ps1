#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_FirstLiveDayReview -- daily 16:30 ET post-session review of the
  overnight-safety stack (2026-09-02). Fires 14:30 MT local (this box is Mountain, ET = local + 2h).

.DESCRIPTION
  THE GAP THIS CLOSES: markdown/planning/OPUS-WORK-ORDER-2026-09.md §1 specifies a
  "16:30 ET first-live-day review (Opus, 20 min)" -- a MANUAL read of the dead-man's-switch
  log, engine_health, the EOD flatten chain and the conductor picks. A manual review runs
  only if a human remembers, which is the same failure mode that left Gamma_GuardsFull's
  RED unread for two days (see GUARDS-FULL-NEVER-RUNS-ON-A-GAMING-EVENING) and left the
  window-leak violation in prereg_hygiene.py shipping a nightly console popup unnoticed.
  §5 of that order says recurring work becomes a $0 script. This registers the script so
  the loop between "the instrument exists" and "the instrument actually runs" is closed --
  the built-is-not-running gap (C35 / L221) this repo keeps re-learning.

  Runs setup/scripts/first_live_day_review.py, which is READ-ONLY: it places no order,
  mutates no trading state, and writes only analysis/first-live-day/<date>.{json,md}.

  Checks: DMS cadence (expected fires derived from dead_mans_switch.py's own
  RTH_START/RTH_END, with gaps > 4 min enumerated), DMS verdicts (FLATTENED / ERROR /
  NO_CREDS / READ_FAILED all failures; DMS_DRY flagged as not-armed), engine_health
  escalation_flags + duplicate_ticks, the Gamma_EodFlatten_Aggressive 15:55 broker reach,
  fleet kill-switch proximity (Rule 5 is NOT latched on fleet arms until the
  safety-bundle-2026-09-29 branch merges, so the draw is computed independently rather
  than trusting circuit-breaker.json#tripped), GuardsFull freshness vs its expected 4
  failures, and conductor GATE-BLOCKING picks (ADVISORY -- never gates the verdict).

  A check that COULD NOT RUN is never a pass: a missing DMS log is RED "never fired", not
  GREEN-by-absence. That rule is the guard_runner_full scar and it is tested.

  WIRING PATTERN (flash-free, cloned from install-prereg-hygiene.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> first_live_day_review.py
  System pythonw: the script is pure stdlib + setup/scripts/et_clock (verified -- it runs
  clean on system `python`, no venv, no pandas).

  TZ RULE: rig is Mountain (ET = local + 2h). -At is LOCAL. 14:30 MT = 16:30 ET, after the
  15:55 ET flatten and the 15:52 Core flatten have both written. A DAILY trigger, never a
  one-time TimeTrigger (which goes dark after install day -- project_scheduled_task_onetime
  _trigger_dark). 16:30 ET sits inside quiet_mode's LOUD weekday band (08:00-18:00 ET), so
  it is not held down by the fullscreen presence gate the way the 23:15 ET GuardsFull is.

  Output:
    analysis/first-live-day/<date>.json|.md -- the review
    automation/state/logs/run-cmd-hidden-<date>.log -- the real exit code, dated

  Per CLAUDE.md OP-3 ($0, pure Python), OP-25 (fail loud, never silent), OP-33
  (visibility is the product). Guard: backtest/tests/test_first_live_day_review_2026_09_02.py.
  REVOKE: Unregister-ScheduledTask -TaskName Gamma_FirstLiveDayReview -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\first_live_day_review.py"
$taskName     = "Gamma_FirstLiveDayReview"

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

# Daily 14:30 LOCAL (Mountain) = 16:30 ET.
$trigger = New-ScheduledTaskTrigger -Daily -At "14:30"

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
    -Description ("Daily 16:30 ET post-session review of the overnight-safety stack " + `
    "(2026-09-02, work-order §1/§5). READ-ONLY: places no order, writes only " + `
    "analysis/first-live-day/<date>.{json,md}. Checks DMS cadence + verdicts, " + `
    "engine_health, the 15:55 aggressive flatten, fleet kill-switch proximity (Rule 5 is " + `
    "not latched on fleet arms until safety-bundle-2026-09-29 merges), GuardsFull " + `
    "freshness vs its expected 4 failures, and conductor picks (advisory). A check that " + `
    "could not run is RED, never GREEN-by-absence. Daily 14:30 MT (16:30 ET). Pure stdlib, " + `
    "`$0. Guard: backtest/tests/test_first_live_day_review_2026_09_02.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_FirstLiveDayReview -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- daily 14:30 MT (16:30 ET)."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
