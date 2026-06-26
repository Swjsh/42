#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_AutoApply -- the Actuator that closes the approval->apply->commit loop
  (Phase 1 of the autonomy plan).

.DESCRIPTION
  Each fire runs autonomy_actuator.py once: read conductor-proposals.jsonl for rows J
  has approved (via Discord ship), apply each one's structured `apply_ops` (exact
  find/replace), snapshot first, run the fast safety gate, and on green git-commit it;
  on red restore the snapshot and flag. Pure Python ($0 -- no Claude/Max pool), so it
  can run frequently. Every 30 min in the after-hours window 16:00-09:30 ET.

  SAFETY:
    * Only acts on J-APPROVED proposals (per-proposal consent already given on Discord).
    * Requires STRUCTURED apply_ops -- never interprets prose, never runs a model.
    * SAFETY GATE before every commit; RED gate => snapshot restore, nothing commits.
    * Rule 9: the actuator self-refuses during RTH; the task window is after-hours too.
    * Reversible: every apply snapshots first; `autonomy_actuator.py revert <id>` (and the
      Discord "revert <id>" command) restores + commits the revert -- J's one-tap off-switch.
    * FAIL-OPEN: never kills/blocks J's session.

  TZ NOTE (project memory scheduled_task_tz -- rig is Mountain): computes the live
  ET->local offset at install time. Re-run after a DST shift to re-anchor.

  Wired via the OP-27 L42 zero-leak chain:
    Task Scheduler -> wscript -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-autoapply.ps1 -> autonomy_actuator.py
#>
$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_AutoApply"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) { Write-Error "System pythonw not found at $pythonw"; exit 1 }

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-autoapply.ps1"
foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

# --- ET -> local offset (rig is Mountain; honor DST) --------------------------
$etZone = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
$nowUtc = [DateTime]::UtcNow
$etNow = [TimeZoneInfo]::ConvertTimeFromUtc($nowUtc, $etZone)
$localNow = [DateTime]::Now
$etMinusLocalHours = [math]::Round(($etNow - $localNow).TotalHours)

# After-hours window: 16:00 ET -> 09:30 ET next morning = 17.5h, every 30 min.
$startHourEt = 16
$startHourLocal = (($startHourEt - $etMinusLocalHours) % 24 + 24) % 24
$windowHours = 17.5
$startLocal = (Get-Date).Date.AddHours($startHourLocal)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

$trigger = New-ScheduledTaskTrigger -Daily -At $startLocal -DaysInterval 1
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $startLocal `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Hours $windowHours)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("Gamma AutoApply -- the Actuator. Every 30 min 16:00-09:30 ET (after-hours). Applies J-approved conductor proposals (structured apply_ops only), gated by the fast safety suite, snapshot-backed, auto-committed. Pure Python (`$0, no Max pool). Rule-9 self-gates RTH. Reversible via 'autonomy_actuator.py revert <id>' / Discord 'revert <id>'. Fail-open.") | Out-Null

Write-Output ("OK: Registered $TaskName")
Write-Output ("    Cadence: every 30 min 16:00-09:30 ET (local start " + $startLocal.ToString("HH:mm") + ", ET-local delta " + $etMinusLocalHours + "h)")
Write-Output ("    Acts on: J-approved rows in conductor-proposals.jsonl -> apply (gated) -> commit; else restore+flag")
Write-Output ("    Cost:    `$0 (pure Python -- never spawns a model)")
Write-Output ("    Revert:  autonomy_actuator.py revert <id>  (or Discord 'revert <id>')")
Write-Output ("    Verify:  python setup\scripts\audit_scheduled_tasks.py")
