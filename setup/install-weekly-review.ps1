#requires -Version 5.1
<#
.SYNOPSIS
  Install/re-register Gamma_WeeklyReview scheduled task -- fires Sunday 21:12 LOCAL
  (Mountain) = 23:12 ET (quiet-mode LOUD maintenance band; re-timed 2026-08-26,
  was 18:00 ET, inside the 16:00-08:00 blackout, so it fired never).

.DESCRIPTION
  Deepest weekly analytical task: Invoke-Claude review of the week's trades,
  setups, and recommendations (~$8/run, 12-min cap, high effort). Worker:
  setup/scripts/run-weekly-review.ps1 -> automation/prompts/weekly-review.md.

  2026-09-03 WEEKLY-REVIEW-RETRY-DONE-MARKER (queue.md): this task was the one
  evening producer left WITHOUT a self-heal retry window when the other 7 got
  one (dceb125e) -- an Invoke-Claude LLM call is not naturally idempotent, so a
  blind retry would double-bill ~$8. Fixed by adding a done-marker
  (automation/state/weekly-review-done.json, written ONLY on success by
  setup/scripts/weekly_review_marker.py) that run-weekly-review.ps1 now checks
  BEFORE calling Invoke-Claude -- a same-week retry inside this window is a
  free no-op (SKIP, no LLM call), not a double-bill. Self-heal window: every
  15 min for 30 min after the primary fire (matches the other 7).

  pythonw + the wscript -> run_exe_hidden.vbs -> run_ps1_hidden.py chain is the
  canonical L41/L42/C8 zero-leak hidden spawn (OP-27).

  To enable:  .\setup\install-weekly-review.ps1
  To verify:  Get-ScheduledTaskInfo -TaskName Gamma_WeeklyReview | Select NextRunTime
  To test:    Start-ScheduledTask -TaskName Gamma_WeeklyReview   (WARNING: bills ~$8 unless the current ISO week is already marked done)
  To disable: Unregister-ScheduledTask -TaskName Gamma_WeeklyReview
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_WeeklyReview"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-weekly-review.ps1"
$markerScript = Join-Path $ScriptsDir "weekly_review_marker.py"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1, $markerScript)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# Original registration: 2026-06-01T21:12:00 LOCAL (Mountain), weekly on Sunday
# (2026-08-26 re-time out of the 16:00-08:00 quiet-mode blackout). Preserve the
# exact primary fire time -- only the retry window is new.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "21:12"
# 2026-09-03 WEEKLY-REVIEW-RETRY-DONE-MARKER (queue.md): same self-heal shape as the
# other 7 evening producers (dceb125e), gated safe here by the done-marker in
# run-weekly-review.ps1 -- a retry within this window either SKIPs for free
# (current week already marked done) or re-attempts a run that never completed
# (the only case where re-running is correct). Self-heal window: every 15 min
# for 30 min after the primary fire.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "21:12" `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Weekly deep-analytical review (Sunday 21:12 MT = 23:12 ET): Invoke-Claude review of the week's trades/setups/recommendations (~`$8, 12-min cap, high effort) via automation/prompts/weekly-review.md. Gated by a done-marker (automation/state/weekly-review-done.json, written only on success) so the PT15M/PT30M self-heal retry window never double-bills a same-week re-fire."

Write-Output "OK: Registered $TaskName for Sunday 21:12 MT (23:12 ET), retry window PT15M/PT30M"
Write-Output "    Worker:  setup\scripts\run-weekly-review.ps1"
Write-Output "    Marker:  automation\state\weekly-review-done.json (written on success only)"
Write-Output "    Verify:  Get-ScheduledTaskInfo -TaskName $TaskName | Select NextRunTime"
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Output ("    NextRunTime: " + $info.NextRunTime)
