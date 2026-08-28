#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_RegimeShadow -- nightly ER30 regime shadow counter
  (REGIME-CONDITIONAL-EXIT-2026-08-11 prereg). Read-only, shadow only.

  WHY THIS FILE EXISTS NOW (2026-08-28, VBS-WRAPPER-EXIT-CODE-BLIND-SPOT SEVENTH PASS):
  this task has been live since 2026-08-11, correctly wired onto the run_py_venv_hidden.py
  relay (confirmed live via Get-ScheduledTask -- real exit-code + log visibility already
  works today), but had NO discoverable install-*.ps1 source anywhere in the repo -- it
  was registered by a one-off/ad-hoc command that was never saved. That is the exact
  CryptoTwin-class latent regression risk `test_install_script_relay_wiring_drift.py`
  exists to prevent: with no declarative template, any FUTURE legitimate re-registration
  (a cadence tune, a settings change) would have no source-of-truth to copy from and
  could easily land back on a direct wscript->pythonw->script.py wiring, silently losing
  exit-code visibility with zero symptom -- precisely what happened to Gamma_CryptoTwin
  on 2026-08-01 before its own install script was fixed (2026-08-07).

  This file is a PURE SAFETY NET: it reproduces the CURRENT LIVE registration byte-for-byte
  (same relay, same daily 21:24 local trigger, same 10-minute execution limit, same
  IgnoreNew/StartWhenAvailable settings) -- running it is a no-op against live behavior,
  not a change. Verified via `Get-ScheduledTask -TaskName Gamma_RegimeShadow` +
  `Get-ScheduledTaskInfo` before writing this file.

  WIRING PATTERN (matches Gamma_JIntentExecutor / Gamma_RegimeStamp / Gamma_ChartAutoDraw --
  the run_py_venv_hidden.py relay, built 2026-08-13 as a console-leak fix and found to ALSO
  close the exit-code blind spot for every task on it):
    wscript -> run_exe_hidden.vbs -> system pythonw.exe -> run_py_venv_hidden.py ->
    backtest-venv-equivalent regime_shadow_counter.py (run_py_venv_hidden.py puts the
    backtest venv's site-packages on PYTHONPATH and launches under system pythonw --
    see that script's own docstring for why, L41-pattern).

  TZ RULE: this rig is Mountain Time (ET = local + 2h). Live trigger fires at 21:24 LOCAL
  (confirmed via Get-ScheduledTaskInfo's StartBoundary 2026-08-11T21:24:00, local clock) --
  reproduced here as-is, NOT reinterpreted as an ET literal (this task has no documented
  ET-anchored intent; preserving the live time exactly is the safety-net goal, not
  re-deriving a "correct" ET equivalent).

  To verify after running: Get-ScheduledTask -TaskName Gamma_RegimeShadow | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_RegimeShadow" -Confirm:$false
          then re-create via whatever ad-hoc mechanism originally existed (none known --
          this file is now the sole source of truth going forward).
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root       = "C:\Users\jackw\Desktop\42"
$vbs        = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPyVenv  = Join-Path $root "setup\scripts\run_py_venv_hidden.py"
$script     = Join-Path $root "setup\scripts\regime_shadow_counter.py"
$taskName   = "Gamma_RegimeShadow"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

foreach ($p in @($vbs, $sysPythonw, $runPyVenv, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

function Show-Next {
    param([string]$Name)
    $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction SilentlyContinue
    if ($info -and $info.NextRunTime) {
        Write-Host ("  NextRun (local): {0}" -f $info.NextRunTime.ToString("yyyy-MM-dd HH:mm"))
    } else {
        Write-Host "  NextRun: (none / on-demand)"
    }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_py_venv_hidden.py -> regime_shadow_counter.py
# (matches the LIVE registration confirmed 2026-08-28 -- reproduced verbatim, not changed.)
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runPyVenv`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# Daily, 21:24 local -- matches live StartBoundary (2026-08-11T21:24:00) exactly.
$trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At ([DateTime]"21:24")

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Nightly ER30 regime shadow counter (REGIME-CONDITIONAL-EXIT-2026-08-11 prereg). Read-only, shadow only. Fires 21:24 local daily. Relay: run_py_venv_hidden.py (exit-code + log visibility, VBS-WRAPPER-EXIT-CODE-BLIND-SPOT SEVENTH PASS 2026-08-28 -- this install script did not previously exist; task was already correctly wired live, this closes the template-drift gap). Guard: backtest/tests/test_install_script_relay_wiring_drift.py." `
    -Force | Out-Null

Write-Host "Registered $taskName (21:24 local daily, run_py_venv_hidden.py relay)"
Show-Next $taskName
Write-Host ""
Write-Host "Gamma_RegimeShadow wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_RegimeShadow | Get-ScheduledTaskInfo"
