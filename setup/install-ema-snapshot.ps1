#requires -Version 5.1
<#
.SYNOPSIS
  (Re)install Gamma_EmaSnapshot on the canonical hidden-spawn chain -- fires 06:20 local
  (Mountain) = 08:20 ET daily, 10 min before Gamma_Premarket.

.DESCRIPTION
  Computes Saty Pivot Ribbon EMAs (13/20/48) + SMA 50 from the latest SPY 5m CSV and
  patches automation/state/ema-snapshot.json + today-bias.json. Pure Python, $0.

  WHY THIS SCRIPT EXISTS (window-leak fix, 2026-06-20):
  The task was originally registered with a BARE console `python.exe` action:
      Execute = backtest\.venv\Scripts\python.exe   Argument = ...compute_ema_snapshot.py
  python.exe is console-subsystem, so Task Scheduler flashed a visible console window
  every morning at 06:20 (audit_scheduled_tasks.py flagged it VISIBLE_WINDOW +
  PYTHON_NOT_PYTHONW). This re-registers it on the L42/C8 zero-leak chain:
      wscript //nologo run_exe_hidden.vbs <backtest-venv pythonw> compute_ema_snapshot.py
  - wscript.exe is GUI-subsystem  -> no console for itself
  - run_exe_hidden.vbs Shell.Run windowStyle=0 -> bypasses the WT default-terminal handler
  - backtest-venv pythonw.exe is GUI-subsystem -> never allocates a console
  The interpreter MUST be the backtest venv (it has pandas; system Python313 does not).

  NOTE: -At is LOCAL time (Task Scheduler convention). The rig is Mountain; 06:20 MT =
  08:20 ET. Do NOT relabel this as an ET hour (the project_scheduled_task_tz foot-gun).

  Per CLAUDE.md OP-25 (fail loud) + OP-3 ($0). To disable:
  Unregister-ScheduledTask -TaskName Gamma_EmaSnapshot.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_EmaSnapshot"

# Backtest venv pythonw -- has pandas (system Python313 does not). GUI-subsystem = windowless.
$pythonw = Join-Path $WorkDir "backtest\.venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "backtest venv pythonw not found at $pythonw (create: cd backtest; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt)"
    exit 1
}

$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker       = Join-Path $WorkDir "automation\scripts\compute_ema_snapshot.py"

foreach ($p in @($runExeHidden, $worker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <pythonw> <compute_ema_snapshot.py>  (fully hidden)
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$worker`""

# 06:20 LOCAL (Mountain) = 08:20 ET, 10 min before Gamma_Premarket.
$trigger = New-ScheduledTaskTrigger -Daily -At "06:20"

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
    -Description "Pre-premarket EMA/SMA snapshot from SPY 5m CSV -> ema-snapshot.json + today-bias.json. 06:20 MT (08:20 ET) daily. Hidden wscript->venv-pythonw chain (no console flash). Pure Python, zero LLM cost."

Write-Output "OK: Re-registered $TaskName for 06:20 MT (08:20 ET) daily on the hidden chain"
Write-Output "    Worker:  $worker"
Write-Output "    Audit:   python setup\scripts\audit_scheduled_tasks.py   (expect no VISIBLE_WINDOW)"
Write-Output "    Test:    Start-ScheduledTask -TaskName $TaskName"
