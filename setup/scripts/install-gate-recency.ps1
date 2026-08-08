#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_GateRecency -- the WEEKLY gate-recency instrument (J directive 2026-08-08:
  the gate-recency audit that found money-blocking stale gates must become PERMANENT DOCTRINE
  + a STANDING INSTRUMENT, not a one-off). Fires Sundays 18:00 local.

.DESCRIPTION
  THE GAP THIS CLOSES: analysis/recommendations/gate-recency-audit-2026-08-08.{md,json} was a
  manual, one-shot audit that found real money-blocking staleness the existing nightly checker
  (Gamma_GateExpiryCheck / backtest/autoresearch/gate_expiry_check.py) cannot see on its own --
  that checker only mines GATE_ORDER + two named vetoes + fleet config, not the scoring-filter
  layer, the extra-setup lane, or risk_gate config modes (pdt_gate_mode). Without a standing
  re-run, the audit's findings would rot exactly like block_elite_bull's 2026-07-10 verdict
  rotted for 21 days before the 2026-07-31 scar (111 refusals on a maxed 11/11 setup, on stale
  evidence, same session). This task is the fix.

  Runs setup/scripts/gate_recency_report.py, which:
    1. Reads automation/state/gate-registry-status.json (the nightly checker's own RED/YELLOW/
       GREEN/STALE_UNVERIFIED P&L verdicts -- read only, never recomputed here).
    2. Mines automation/state/core-decisions.jsonl for a FRESH block-count pass (raw tick
       counts, no $ simulation) over the trailing 15 distinct armed=true trading days, using
       the exact per-gate attribution rules gate-recency-audit-2026-08-08.json documented
       (sole-blocker attribution for the scoring-filter layer, detector-fired for the
       extra-setup lane, verdict/action equality for GATE_ORDER gates + vetoes + risk_gate
       config modes).
    3. Reads automation/state/gate-registry.json for provenance dates where a gate has a
       registry row; falls back to a hardcoded date ported from the 2026-08-08 audit for the
       gates the registry doesn't cover (the scoring filters, the extra-setup lane,
       pdt_gate_mode, the two confirmed-dead params bundles).
    4. Writes automation/state/gate-recency-latest.json -- schema-stable, consumable by a
       future standup/wants-surface without special-casing.

  NEVER BLOCKS, NEVER KILLS, NEVER AUTO-DISARMS, NEVER WRITES params.json. Pure report, exactly
  like Gamma_GateExpiryCheck's own "arming/disarming stays a human decision" rule (OP-16).
  Fail-open per source throughout -- a missing/malformed input degrades that ONE source, never
  aborts the run. See markdown/doctrine/GATE-RECENCY-DOCTRINE.md for the full doctrine + the
  7-day RED-without-a-pre-reg rule this instrument exists to make checkable.

  DEPENDENCY-LIGHT BY DESIGN: gate_recency_report.py is pure stdlib (json/pathlib/datetime/
  argparse) -- no pandas, no OPRA cache. Unlike Gamma_GateExpiryCheck (which NEEDS the
  backtest venv for its real-OPRA-fills replay), this task runs entirely on SYSTEM pythonw --
  one fewer moving part for a "keeps running forever" weekly instrument.

  WIRING PATTERN (flash-free, cloned from install-futures-mirror.ps1's exit-code-visible
  chain -- 2026-08-07 VBS-wrapper-exit-code-blind-spot lesson: wscript's own `shell.Run cmd,
  0, False` never waits, so Task Scheduler's LastTaskResult reflects wscript's instant exit,
  not the real script's; run_cmd_hidden.py's own dated log is the ONLY place the true exit
  code is visible):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> gate_recency_report.py
  Both hops use SYSTEM pythonw (not the backtest venv) -- this script has no third-party deps.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). -At is LOCAL time (Task Scheduler
  convention) -- 18:00 MT = 20:00 ET, well clear of the 09:30-15:55 ET heartbeat window and
  clear of Sunday being a non-trading day anyway. A WEEKLY trigger (DaysOfWeek Sunday), never
  a one-time/interval trigger (goes dark after the install day --
  project_scheduled_task_onetime_trigger_dark).

  Output:
    automation/state/gate-recency-latest.json -- latest weekly report (always written on a
      successful non-dry-run)
    automation/state/logs/gate-recency-report.std{out,err}.log -- headless stdio redirect
    automation/state/logs/run-cmd-hidden-<date>.log -- the real exit code, dated

  To verify after running: Get-ScheduledTask -TaskName Gamma_GateRecency | Get-ScheduledTaskInfo
  To test now (does NOT wait for Sunday):     Start-ScheduledTask -TaskName Gamma_GateRecency
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_GateRecency" -Confirm:$false

  Per CLAUDE.md OP-3 ($0, pure Python) + OP-25 (fail loud on genuine failure, never silent) +
  OP-16 J's 2026-07-31 recency directive. Guard: backtest/tests/test_gate_recency_report.py.
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\gate_recency_report.py"
$taskName     = "Gamma_GateRecency"

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- system pythonw -> gate_recency_report.py   (no --dry-run: this IS the writer)
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# Sundays 18:00 LOCAL (Mountain) = 20:00 ET. Weekly, not one-time (a one-time TimeTrigger
# goes dark after the install day per project_scheduled_task_onetime_trigger_dark).
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "18:00"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Weekly gate-recency instrument (J directive 2026-08-08): merges " + `
    "gate-registry-status.json's nightly RED/YELLOW/GREEN P&L verdicts with a fresh 15-" + `
    "trading-day block-count pass (ported from gate-recency-audit-2026-08-08.json's per-gate " + `
    "attribution rules) covering the scoring-filter layer, extra-setup lane, and risk_gate " + `
    "config modes that Gamma_GateExpiryCheck's own scope does not reach. Writes " + `
    "automation/state/gate-recency-latest.json. NEVER blocks/kills/auto-disarms/writes " + `
    "params -- report only. Sundays 18:00 MT (20:00 ET). Pure stdlib Python, `$0, no venv " + `
    "needed. Guard: backtest/tests/test_gate_recency_report.py. Doctrine: " + `
    "markdown/doctrine/GATE-RECENCY-DOCTRINE.md.") `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $taskName for Sundays 18:00 MT (20:00 ET)"
Write-Output "    Report:   automation\state\gate-recency-latest.json"
Write-Output "    Test now: Start-ScheduledTask -TaskName $taskName"
Write-Output "    Next run: $($info.NextRunTime)"
