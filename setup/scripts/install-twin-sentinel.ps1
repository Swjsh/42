#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_TwinSentinel -- the deterministic RED/YELLOW/GREEN judge for the
  CRYPTO TWIN (markdown/planning/TWIN-PROGRAM.md). Fires every 15 min, 24/7 -- same
  no-day/time-restriction shape as Gamma_CryptoTwin, since crypto never closes.

  Each fire runs setup/scripts/twin_sentinel.py, which:
    1. Reads decisions.jsonl + twin-health.json + path-coverage.json + incidents.jsonl
       (all READ-ONLY -- this task never writes anything B1/B2 own) and computes a
       deterministic verdict: tick freshness, UTC-day uptime, incident count (dual
       source: incidents.jsonl scan + path-coverage.json's own per-branch
       status=="INCIDENT" count), path-coverage lag (after 18:00 UTC), breaker state,
       account_status regression.
    2. Writes automation/state/twin-sentinel.json every fire.
    3. On a NEW transition into RED: appends one row to automation/overnight/queue.md
       under "## Twin escalations" + sends one Discord ping -- de-duped per episode.
    4. Once per UTC day, after 23:30 UTC: triggers setup/scripts/twin_review.py (the
       nightly FREE-LLM review) as a subroutine of THIS SAME fire -- no second task.

  COST: $0 baseline. Sentinel itself is pure Python (no LLM). The nightly review
  calls ONE free-tier model via swarm_client's roster (OpenRouter free-tier ->
  Cerebras free dev tier -> local Ollama floor) -- never a paid model, never
  scheduled Sonnet/Claude. See twin_review.py's own module docstring for the
  verified (not assumed) cost analysis.

  REAPER EXEMPTION -- same verified pattern as Gamma_CryptoTwin (guard:
  backtest/tests/test_crypto_twin_reaper_exemption.py's static parse of
  _shared.ps1 applies to any pythonw.exe launch regardless of which script; this
  installer reuses the identical launch shape). Stop-StaleClaudeProcesses's
  Win32_Process -Filter Name clause does not include 'pythonw.exe' at all, so this
  task's process is never even fetched by the reaper's query. Defense in depth:
  launched via backtest\.venv\Scripts\pythonw.exe, whose CommandLine also contains
  the literal substring 'backtest\.venv' (an existing $EXEMPT_DAEMONS entry).

  WIRING PATTERN (flash-free, matches install-crypto-twin.ps1 / install-ccr-keepalive.ps1):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> twin_sentinel.py
  Single-hop chain (twin_sentinel.py is a native Python script, no --live flag needed --
  it never places orders, never touches B1/B2's files).

  CADENCE: `-Once` base trigger + `-RepetitionInterval 15min` + a ~10-year
  `-RepetitionDuration` -- the verified-live pattern (matches Gamma_CryptoTwin's real
  NextRunTime behavior: recalculates every fire, never goes dark).

  ExecutionTimeLimit is 8 min (generous vs Gamma_CryptoTwin's 3 min): 95/96 fires per
  day are pure-Python and complete in well under a second, but the ONE fire per day
  that crosses 23:30 UTC also runs the nightly review, which may try up to 2 remote
  free lanes (each capped ~45s) plus a local-ollama attempt (up to 90s) plus ONE
  schema repair-retry -- comfortably inside 8 min even in the worst case, so Task
  Scheduler never kills a legitimately-still-working nightly review.

  To verify after running: Get-ScheduledTask -TaskName Gamma_TwinSentinel
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$taskName  = "Gamma_TwinSentinel"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$script       = Join-Path $root "setup\scripts\twin_sentinel.py"
# 2026-08-07: relay through run_cmd_hidden.py for real exit-code visibility -- see
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT / Gamma_CryptoTwin drift finding, queue.md.
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"

if (-not (Test-Path $script))      { throw "twin_sentinel.py not found at $script" }
if (-not (Test-Path $sysPythonw))  { throw "system pythonw.exe not found at $sysPythonw" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- backtest-venv pythonw -> twin_sentinel.py
# (flash-free chain; backtest-venv pythonw is BOTH the reaper-exempt-by-path launcher
# AND the interpreter that already has et_clock/swarm_client importable cleanly).
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Every 15 min, 24/7 -- no day/time restriction (crypto never closes; matches
# Gamma_CryptoTwin's own no-RTH-gate shape).
$startBoundary = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 8) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "TWIN SENTINEL -- deterministic RED/YELLOW/GREEN judge for the CRYPTO TWIN (markdown/planning/TWIN-PROGRAM.md), built to fill the 'nobody is watching the watcher' gap while B1/B2 build the twin's own core loop. Every 15 min, 24/7: reads decisions.jsonl + twin-health.json + path-coverage.json + incidents.jsonl (READ-ONLY) and evaluates tick freshness / UTC-day uptime / incident count (dual-source) / path-coverage lag (after 18:00 UTC) / breaker state / account_status regression, writes automation/state/twin-sentinel.json every fire. On a NEW transition into RED: one automation/overnight/queue.md row under '## Twin escalations' + one Discord ping, de-duped per episode. Once per UTC day after 23:30 UTC, triggers the nightly FREE-LLM review (twin_review.py, ONE free-tier model call via swarm_client's roster, writes reviews/YYYY-MM-DD.md + .json sidecar) as a subroutine of this SAME fire. Cost: `$0 baseline (pure Python judge; review = free-tier only, never paid, never scheduled Sonnet/Claude). Reaper-exempt: pythonw.exe is outside Stop-StaleClaudeProcesses's Name filter, plus backtest\.venv path match as defense in depth. Built 2026-07-11." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
