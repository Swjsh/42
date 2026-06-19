#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_GexCapture scheduled task -- fires 09:15 ET weekdays.

.DESCRIPTION
  Daily dealer-GEX (gamma exposure) capture + regime tag. Worker:
  automation/scripts/gex_capture.py. Each fire:
    1. Pulls the full SPY option-chain snapshot (greeks + open interest) from Alpaca.
    2. Archives the RAW chain to journal/gex-archive/{date}.json -- the BACKTESTABLE
       history that accrues going forward (the key unblock: today we have NO historical
       OI+gamma snapshots, so the one peer-reviewed regime signal in
       backtest/lib/engine/gex_regime.py cannot be backtested; these daily snapshots fix
       that as they accumulate).
    3. Computes the dealer-gamma regime (short_gamma_trend / long_gamma_pin / neutral)
       by REUSING gex_regime.from_alpaca_snapshot + compute_gex_regime, and writes the
       tag to automation/state/gex-regime.json for premarket/heartbeat to read.

  WHY 09:15 ET: ~15 min after the options market opens, the chain is liquid and greeks/OI
  are populated, but it's still in the premarket-prep window (before the 09:30 heartbeat
  starts) so the regime tag is fresh for the day's first ticks. -At is LOCAL time (Task
  Scheduler convention); the rig is Mountain, so this is set as 07:15 MT (= 09:15 ET).
  Do NOT relabel the -At value as an ET hour (the project_scheduled_task_tz foot-gun).

  CRITICAL INTERPRETER NOTE (L20/L42 venv-interpreter lesson): gex_capture.py imports the
  engine package (backtest/lib/engine/gex_regime.py), which pulls in pandas/the lib. The
  system Python313 does NOT have those deps -> "No module named pandas". So this task MUST
  run on the backtest venv interpreter (backtest/.venv/Scripts/pythonw.exe). pythonw keeps
  it windowless; the wscript -> run_exe_hidden.vbs chain is the canonical L41/L42/C8
  zero-leak hidden spawn (no console flash -- the dont-disturb-user mandate).

  WIRE-NOT-AUTO-ENABLE (Rule 9 / OP-22 propose-only): this script is AUTHORED but the
  task is NOT registered live by the build that created it. J runs this installer when
  ready (same pattern as Gamma_ArchiveKeyLevels / the health beacon). Documented in
  automation/state/SCHEDULED-TASKS.md under "Wired -- NOT yet enabled".

  The job is idempotent (SKIP_EXISTS if today's archive is present) and fail-safe (writes
  a status:"not_computed" tag, never crashes, if the chain is unavailable). It reads no
  production state and writes only NEW files. Never places orders; never edits
  params*.json / heartbeat.md / CLAUDE.md. Pure Python + one REST pull. Zero LLM cost.

  To enable:  .\setup\install-gex-capture.ps1
  To verify:  python setup\scripts\audit_scheduled_tasks.py
  To disable: Unregister-ScheduledTask -TaskName Gamma_GexCapture
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_GexCapture"

# Must be the backtest venv interpreter -- it has pandas/the engine deps that the worker
# imports via gex_regime. The system Python313 does NOT (the "No module named pandas"
# foot-gun, L20/L42). pythonw keeps the process windowless.
$pythonw = "C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "backtest venv pythonw not found at $pythonw (create: cd backtest; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt)"
    exit 1
}

$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker       = Join-Path $WorkDir "automation\scripts\gex_capture.py"

foreach ($p in @($runExeHidden, $worker)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <venv-pythonw> <gex_capture.py>  (fully hidden)
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$worker`""

# 07:15 LOCAL (Mountain) = 09:15 ET -- ~15 min after options open, chain liquid, still
# inside premarket prep (before the 09:30 ET heartbeat). LOCAL time per Task Scheduler.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:15"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily SPY dealer-GEX capture: archives the raw option chain (greeks+OI) to journal/gex-archive/{date}.json (backtestable history) and writes the regime tag to automation/state/gex-regime.json (reuses backtest/lib/engine/gex_regime.py). 09:15 ET weekdays (07:15 MT). Idempotent + fail-safe. Pure Python, zero LLM cost. OP-22 propose-only -- does NOT trade or edit doctrine."

Write-Output "OK: Registered $TaskName for 09:15 ET weekdays (07:15 MT)"
Write-Output "    Interpreter: $pythonw  (backtest venv -- has pandas/engine deps)"
Write-Output "    Archive:     journal\gex-archive\{date}.json   (backtestable raw chain)"
Write-Output "    Regime tag:  automation\state\gex-regime.json"
Write-Output "    Audit:       python setup\scripts\audit_scheduled_tasks.py"
Write-Output "    Test now:    Start-ScheduledTask -TaskName $TaskName"
