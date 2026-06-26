#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_Drive scheduled task -- the nightly bounded "Gamma drives like J"
  loop. Fires ONCE daily at 20:00 ET (after-hours; NEVER during RTH).

.DESCRIPTION
  Registers Gamma_Drive: one daily fire runs run-gamma-drive.ps1, a BOUNDED loop of
  up to 3 fresh `claude --print` fires, each doing ONE gamma-drive initiative
  (automation/prompts/gamma-drive.md, opus, --agent gamma). The wrapper -- not the
  model -- enforces every hard cap (iteration count, convergence stop, wall-clock
  deadline, stop-flag, single-instance lock, per-fire budget). See the wrapper
  header + .claude/skills/gamma-drive/SKILL.md for the full safety model.

  WHY A SINGLE DAILY FIRE (not /loop): an in-session `/loop /gamma-drive`
  accumulates context across iterations (the 97%-bloat foot-gun). A scheduled
  wrapper that runs a FRESH process per initiative is leak-proof by construction --
  that is the correct shape for continuous unattended running.

  SAFETY (see gamma-drive.md "THE FOUR RAILS"):
    * AFTER-HOURS ONLY. Fires at 20:00 ET; the wrapper re-gates market hours every
      iteration and refuses 09:30-15:55 ET (defense in depth, L54 shared-pool).
    * FAIL-OPEN. Never kills/blocks J's session (the OP-32 scar). Lock released in
      a finally block; stop-flag is a $0 off-switch.
    * BOUNDED. Hard iteration + budget + convergence + deadline caps. Cannot run
      infinitely or eat unbounded tokens.
    * PROPOSE-AND-PING-J for any doctrine/params/order change -- never auto-apply.

  COEXISTENCE: Gamma_Conductor already fires hourly 18:00-07:00 ET (one task/fire).
  Gamma_Drive is the nightly BATCH sibling (a few initiatives in one bounded run).
  They share the queue's status:in_progress / Completed idempotency; the lock only
  guards Gamma_Drive vs itself. If pool usage runs hot, thin the conductor cadence
  (a deliberate, separate call) -- do not silently double-spend.

  TZ NOTE (project memory scheduled_task_tz -- rig is Mountain; tasks scheduled at
  ET-converted-to-LOCAL). Computes the live ET->local offset at install time and
  anchors the trigger to local clock so 20:00 ET fires at the right Mountain
  wall-clock. Re-run after a DST shift to re-anchor.

  Wired via the OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-gamma-drive.ps1 -> claude --print

  NOTE: this script REGISTERS the task; it does not start a live fire itself.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_Drive"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-gamma-drive.ps1"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

# --- ET -> local offset (rig is Mountain; honor DST) --------------------------
# Compute the current ET-vs-local hour delta so "20:00 ET" maps to the right
# local wall-clock start. Both zones observe US DST so the delta is stable
# (ET is 2h ahead of MT), but we compute it rather than hardcode 2.
$etZone = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
$nowUtc = [DateTime]::UtcNow
$etNow = [TimeZoneInfo]::ConvertTimeFromUtc($nowUtc, $etZone)
$localNow = [DateTime]::Now
$etMinusLocalHours = [math]::Round(($etNow - $localNow).TotalHours)

# Single daily fire at 20:00 ET. Local start hour = 20 - (ET-local delta).
$startHourEt = 20
$startHourLocal = (($startHourEt - $etMinusLocalHours) % 24 + 24) % 24
$startLocal = (Get-Date).Date.AddHours($startHourLocal)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# Single daily trigger (NO hourly repetition -- the bounded loop is INSIDE the run).
$trigger = New-ScheduledTaskTrigger -Daily -At $startLocal -DaysInterval 1

# ExecutionTimeLimit covers MAX_INITIATIVES x per-fire timeout + ret/overhead.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 45)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("Gamma Drive -- nightly bounded 'Gamma drives like J' loop. ONE daily fire at 20:00 ET runs up to 3 fresh claude --print fires, each doing ONE gamma-drive initiative (opus, --agent gamma). Wrapper-enforced HARD caps: iteration=3, budget=`$8/fire, convergence=2 no-ops, deadline=08:15 ET, stop-flag + single-instance lock. Fresh context per fire (leak-proof). After-hours ONLY (re-gated every iteration; never RTH per L54). Fail-open (never blocks J -- OP-32 scar). Doctrine/params/orders PROPOSE-only. Off-switch: drop automation/state/gamma-drive-stop.flag. Prompt: automation/prompts/gamma-drive.md; program: .claude/skills/gamma-drive/SKILL.md.") | Out-Null

Write-Output ("OK: Registered $TaskName")
Write-Output ("    Cadence: ONE daily fire 20:00 ET  (local start " + $startLocal.ToString("HH:mm") + ", ET-local delta " + $etMinusLocalHours + "h)")
Write-Output ("    Loop:    bounded INSIDE the run -- max 3 initiatives, `$8/fire, converge=2 no-ops, deadline 08:15 ET")
Write-Output ("    Gate:    after-hours ONLY -- wrapper re-gates every iteration, refuses 09:30-15:55 ET (rail 1 / L54)")
Write-Output ("    Caps:    iteration + budget + convergence + wall-clock + stop-flag + single-instance lock (all wrapper-enforced)")
Write-Output ("    Off:     drop automation\state\gamma-drive-stop.flag to halt the loop")
Write-Output ("    Chain:   wscript -> run_exe_hidden.vbs -> sys-pythonw -> run_ps1_hidden.py -> run-gamma-drive.ps1 -> claude --print (opus, --agent gamma)")
Write-Output ("    Cost:    <=`$24/night ceiling (3 x `$8); realistic ~`$3-6 (convergence + cheap fires); ~`$90-180/mo worst case")
Write-Output ("    Verify:  python setup\scripts\audit_scheduled_tasks.py")
Write-Output ("    Re-run after a DST shift to re-anchor the local start hour.")
