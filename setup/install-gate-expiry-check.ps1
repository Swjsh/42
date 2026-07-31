#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_GateExpiryCheck scheduled task -- fires 23:00 local (Mountain) nightly.

.DESCRIPTION
  THE GATE-EXPIRY INSTRUMENT (J directive 2026-07-31: "the same thing that worked on day
  372 ago is not gonna work on day 162 ago" -- every armed veto/gate was validated ONCE and
  then blocks forever with no re-validation clock). Runs
  backtest/autoresearch/gate_expiry_check.py, which:
    1. Reads automation/state/gate-registry.json (one row per armed gate/veto/filter that
       can refuse an entry -- the 15 backtest/lib/engine/gates.py GATE_ORDER gates,
       structure_veto_enabled, the free-model veto, risk_gate's safety-class refusals, and
       the fleet's per-arm gate patches).
    2. For every gate with a real SKIP_* action, mines automation/state/core-decisions.jsonl
       for the recent rolling window (reuses autoresearch/recency_check.py's own
       RECENCY_LOOKBACK_TRADING_DAYS / CONFIRM_N_FLOOR -- does not reinvent the window/floor),
       replays each refused signal forward through the REAL OPRA option cache
       (lib.simulator_real.simulate_trade_real, the same call recency_check.py uses), and
       flags a gate RED when its refused cohort would have EARNED money recently (n >= floor)
       -- i.e. the gate is COSTING money right now, not just "once validated".
    3. Writes automation/state/gate-registry-status.json (full detail, every gate).
    4. On a NEW transition into RED (never on a persisting one), appends ONE loud line to
       automation/overnight/STATUS.md's "## Known broken" section -- byte-for-byte the same
       pattern as setup/guard_runner_slow.py::_flag_status_md.

  NEVER BLOCKS, NEVER KILLS, NEVER AUTO-DISARMS ANYTHING. Pure report; arming/disarming a
  gate stays a human/ratification decision. Fail-open throughout -- one gate's mining
  failure degrades to overall="ERROR" for that gate only, never aborts the run.

  Mechanism: wscript -> run_exe_hidden.vbs -> backtest-venv pythonw -> gate_expiry_check.py
  (the canonical L42/C8 zero-leak hidden-spawn chain -- no console window flash). The
  interpreter MUST be the backtest venv (pandas/numpy required for the real-OPRA replay).

  Output:
    automation/state/gate-registry-status.json -- latest full per-gate verdict (always written)
    automation/overnight/STATUS.md "## Known broken" -- one line per NEWLY-RED gate

  Timing: 23:00 MT (= 01:00 ET). After-hours under both timezones, clear of the 09:30-15:55
  ET heartbeat window (07:30-13:55 MT) -- never starves the Max pool (L54). Runs after
  Gamma_GuardsNightly (22:30 MT) so the slow regression suite gets first crack at the venv;
  this task is pure Python + pandas, no pytest. NOTE: -At is LOCAL time (Task Scheduler
  convention). The rig is Mountain; do NOT relabel this as an ET hour.

  Per CLAUDE.md OP-16 (auto-ratify needs a fresh scorecard) + OP-25 (fail loud, silent
  failure is the only true failure) + OP-3 ($0, pure Python, zero LLM cost).
  To disable: Unregister-ScheduledTask -TaskName Gamma_GateExpiryCheck.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_GateExpiryCheck"

# Must be an interpreter that HAS the backtest deps (pandas/numpy). The dedicated backtest
# venv does; the system Python313 does NOT. pythonw keeps it windowless.
$pythonw = "C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "backtest venv pythonw not found at $pythonw (create: cd backtest; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt)"
    exit 1
}

$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$checker      = Join-Path $WorkDir "backtest\autoresearch\gate_expiry_check.py"
$registry     = Join-Path $WorkDir "automation\state\gate-registry.json"

foreach ($p in @($runExeHidden, $checker, $registry)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <pythonw> <gate_expiry_check.py>  (fully hidden)
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$checker`"" `
    -WorkingDirectory $WorkDir

# 23:00 LOCAL (Mountain) = 01:00 ET. DailyTrigger (not a one-time/interval trigger -- a
# trigger with no recurrence spec goes dark after the install day, the exact foot-gun
# project_scheduled_task_onetime_trigger_dark documents).
$trigger = New-ScheduledTaskTrigger -Daily -At "23:00"

# ExecutionTimeLimit wider than a realistic run (a full 21-gate mine over the real OPRA
# cache completed in low single-digit minutes in this session's live dry run) so a genuine
# hang produces a clean Task-Scheduler-killed signal rather than masking a hung process as
# "still running" forever.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Gate-expiry instrument (J directive 2026-07-31): nightly recency check for every armed entry gate/veto in automation/state/gate-registry.json. Mines core-decisions.jsonl for the recent rolling window (reuses recency_check.py's window/floor), replays refused signals through real OPRA fills, flags a gate RED when it is COSTING money recently. Writes automation/state/gate-registry-status.json; on a NEW RED transition appends one loud line to STATUS.md Known broken (no respam). NEVER blocks/kills/auto-disarms -- report only. 23:00 MT / 01:00 ET daily. Pure Python, `$0. Guard: backtest/tests/test_gate_expiry_check.py." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $TaskName for 23:00 MT (01:00 ET) daily"
Write-Output "    Registry: automation\state\gate-registry.json"
Write-Output "    Verdict:  automation\state\gate-registry-status.json"
Write-Output "    Test now: Start-ScheduledTask -TaskName $TaskName"
Write-Output "    Next run: $($info.NextRunTime)"
