#requires -Version 5.1
<#
.SYNOPSIS
  (Re)install Gamma_RegimeStamp on the canonical hidden-spawn chain -- fires 06:22 local
  (Mountain) = 08:22 ET daily, between Gamma_EmaSnapshot (08:20) and Gamma_Premarket (08:30).

.DESCRIPTION
  WS6 regime library morning stamp (2026-08-01). Rebuilds
  analysis/regime-library/day-archetypes.json from the pinned SPY/VIX CSV lineage
  (pure Python, deterministic, $0), writes automation/state/regime-stamp.json
  ("yesterday was X, the recent mix is Y") and patches today-bias.json#regime_context.
  Premarket lifts the stamp into the fresh today-bias.json it writes at 08:30.

  Zero-leak chain per L42/C8 (mirrors install-ema-snapshot.ps1):
      wscript //nologo run_exe_hidden.vbs <backtest-venv pythonw> regime_stamp.py
  - wscript.exe is GUI-subsystem -> no console for itself
  - run_exe_hidden.vbs Shell.Run windowStyle=0 -> bypasses the WT default-terminal handler
  - backtest-venv pythonw.exe -> has pandas, never allocates a console
  regime_stamp.py additionally self-redirects stdio to automation/state/logs/ when
  launched under pythonw (OP-27 L41 layer 3).

  NOTE: -At is LOCAL time (Task Scheduler convention). The rig is Mountain; 06:22 MT =
  08:22 ET. Do NOT relabel this as an ET hour (project_scheduled_task_tz foot-gun).

  Per CLAUDE.md OP-25 (fail loud) + OP-3 ($0). To disable:
  Unregister-ScheduledTask -TaskName Gamma_RegimeStamp.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_RegimeStamp"

# Backtest venv pythonw -- has pandas (system Python313 does not). GUI-subsystem = windowless.
$pythonw = Join-Path $WorkDir "backtest\.venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "backtest venv pythonw not found at $pythonw (create: cd backtest; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt)"
    exit 1
}

$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker       = Join-Path $WorkDir "automation\scripts\regime_stamp.py"

foreach ($p in @($runExeHidden, $worker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <pythonw> <regime_stamp.py>  (fully hidden)
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$worker`""

# 06:22 LOCAL (Mountain) = 08:22 ET, between EmaSnapshot (06:20) and Premarket (06:30).
$trigger = New-ScheduledTaskTrigger -Daily -At "06:22"

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
    -Description "WS6 regime library stamp: rebuild day-archetypes.json + write regime-stamp.json (yesterday's archetype + last-25 mix) + patch today-bias.json#regime_context. 06:22 MT (08:22 ET) daily. Hidden wscript->venv-pythonw chain. Pure Python, zero LLM cost, descriptive only."

Write-Output "OK: Registered $TaskName for 06:22 MT (08:22 ET) daily on the hidden chain"
Write-Output "    Worker:  $worker"
Write-Output "    Audit:   python setup\scripts\audit_scheduled_tasks.py   (expect no VISIBLE_WINDOW)"
Write-Output "    Test:    Start-ScheduledTask -TaskName $TaskName"
