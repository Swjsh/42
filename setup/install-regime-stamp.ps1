#requires -Version 5.1
<#
.SYNOPSIS
  (Re)install Gamma_RegimeStamp on the canonical hidden-spawn chain -- fires TWICE daily:
  06:22 local (Mountain) = 08:22 ET, between Gamma_EmaSnapshot (08:20) and Gamma_Premarket
  (08:30) -- the original rebuild+stamp+patch; and 06:40 local = 08:40 ET, a REPATCH-ONLY
  safety net ~10min after Premarket (08:30 ET) normally finishes.

.DESCRIPTION
  WS6 regime library morning stamp (2026-08-01). Rebuilds
  analysis/regime-library/day-archetypes.json from the pinned SPY/VIX CSV lineage
  (pure Python, deterministic, $0), writes automation/state/regime-stamp.json
  ("yesterday was X, the recent mix is Y") and patches today-bias.json#regime_context.
  Premarket lifts the stamp into the fresh today-bias.json it writes at 08:30.

  REGIME-STAMP DRIFT fix (2026-08-05): Premarket is an LLM-prompt-driven session that
  rewrites today-bias.json wholesale at 08:30 and is INSTRUCTED to carry all 4
  regime_context fields (one_liner, yesterday_archetype, stamp_date, source) forward --
  but transcription fidelity is not guaranteed (observed live 2026-08-05: one_liner made
  it through, the other 3 fields silently landed null, flagged RED by both
  monday_verify's WS6 check and self_check's REGIME-STAMP DRIFT problem the same day).
  main() is idempotent and cheap ($0, pure Python) -- re-running it at 08:40 ET re-reads
  whatever today-bias.json Premarket just wrote and unconditionally overwrites
  regime_context with the correct 4-field dict, so the deterministic patch is always the
  LAST writer regardless of how faithfully the LLM prompt transcribed it. This removes the
  dependency on prose-instruction fidelity for a producer/consumer contract (CLAUDE.md
  C14 class). Guard: backtest/tests/test_regime_stamp_repatch.py.

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

# 2026-08-18: routed via run_py_venv_hidden.py (2026-08-13 console-leak fix -- system
# pythonw + PYTHONPATH onto the backtest venv's site-packages, never the venv's own pythonw,
# which allocates a WindowsTerminal -Embedding host on `import pandas`). Also closes
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT via self_check.check_run_py_venv_hidden_masked_exit().
# Live state was already on this wiring (2026-08-13 imperative patch, convert_tasks_off_
# venv_python.py); this template was drifted (CryptoTwin-class regression,
# test_install_script_relay_wiring_drift.py) until this fix.
$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_RegimeStamp"

# System pythonw (GUI-subsystem, windowless) + run_py_venv_hidden.py puts the backtest
# venv's site-packages on PYTHONPATH so pandas/numpy still resolve.
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $sysPythonw)) {
    Write-Error "system pythonw not found at $sysPythonw"
    exit 1
}

$runExeHidden    = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$runPyVenvHidden = Join-Path $ScriptsDir "run_py_venv_hidden.py"
$worker          = Join-Path $WorkDir "automation\scripts\regime_stamp.py"

foreach ($p in @($runExeHidden, $runPyVenvHidden, $worker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <sys-pythonw> run_py_venv_hidden.py <regime_stamp.py>
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runPyVenvHidden`" `"$worker`""

# 06:22 LOCAL (Mountain) = 08:22 ET, between EmaSnapshot (06:20) and Premarket (06:30):
# rebuild + stamp + patch. 06:40 LOCAL = 08:40 ET, ~10min after Premarket (06:30 MT)
# normally finishes: repatch-only safety net (main() is idempotent -- see .DESCRIPTION
# REGIME-STAMP DRIFT fix, 2026-08-05).
$trigger = @(
    (New-ScheduledTaskTrigger -Daily -At "06:22"),
    (New-ScheduledTaskTrigger -Daily -At "06:40")
)

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
    -Description "WS6 regime library stamp: rebuild day-archetypes.json + write regime-stamp.json (yesterday's archetype + last-25 mix) + patch today-bias.json#regime_context. Fires TWICE daily: 06:22 MT (08:22 ET, rebuild+stamp+patch) and 06:40 MT (08:40 ET, idempotent repatch-only safety net vs Premarket transcription drift -- 2026-08-05 fix). Hidden wscript->venv-pythonw chain. Pure Python, zero LLM cost, descriptive only."

Write-Output "OK: Registered $TaskName for 06:22 MT (08:22 ET) + 06:40 MT (08:40 ET) daily on the hidden chain"
Write-Output "    Worker:  $worker"
Write-Output "    Audit:   python setup\scripts\audit_scheduled_tasks.py   (expect no VISIBLE_WINDOW)"
Write-Output "    Test:    Start-ScheduledTask -TaskName $TaskName"
