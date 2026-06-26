#requires -Version 5.1
<#
.SYNOPSIS
  Install/register the Gamma_Grind_Vwap scheduled task (on-demand).

.DESCRIPTION
  ON-DEMAND task that runs the full vwap_continuation strategy-family pipeline in ONE shot:
    grind (mass_grind_vwap, 8 workers, single process)
      -> funnel (mass_grind_vwap_funnel, P2->P3->P4)
      -> consolidation (consolidate_elites_vwap)
  This adds the SECOND family to the strategy table (the first grind, Gamma_Grind_all,
  covered only the ribbon rejection/reclaim entry). Pure Python, $0, propose-only.

  ON-DEMAND (no recurring trigger): it is a one-shot research pipeline, not a standing
  market task. Start it with:  Start-ScheduledTask -TaskName Gamma_Grind_Vwap
  The grind RESUMES from mass-grind-vwap-progress*.jsonl, so a re-run is cheap (delete
  those files first for a clean re-grind).

  Uses the OP-27 L42 canonical zero-leak chain (no console flash):
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw.exe
                   -> run_ps1_hidden.py -> run-grind-vwap.ps1 -> the 3 python stages.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_Grind_Vwap"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw -- OP-27 L42 requires GUI-subsystem pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-grind-vwap.ps1"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

# Remove existing (idempotent)
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> run-grind-vwap.ps1
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# ON-DEMAND: no recurring trigger (one-shot research pipeline). Generous time limit so the
# grind + funnel + consolidation chain (~2 + ~40 + ~1 min) never trips ExecutionTimeLimit.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Settings $settings `
    -Description ("ON-DEMAND vwap_continuation strategy-family pipeline (grind 8-worker -> funnel " +
                  "P2/P3/P4 -> consolidation). SECOND family for the strategy table. Pure Python, " +
                  "zero LLM cost. Real OPRA fills (C1). Start: Start-ScheduledTask Gamma_Grind_Vwap. " +
                  "OP-27 L42 hidden-spawn chain.")

Write-Output ("OK: Registered $TaskName (on-demand)")
Write-Output ("    Run with: Start-ScheduledTask -TaskName $TaskName")
Write-Output ("    Action: wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> run-grind-vwap.ps1")
Write-Output ("    Audit:  python setup\scripts\audit_scheduled_tasks.py")
