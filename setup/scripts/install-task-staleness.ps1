#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_TaskStaleness -- "did each scheduled task ACTUALLY RUN?" reporter
  (2026-09-02). Fires daily 05:45 ET (03:45 MT local -- this box is Mountain, ET=local+2h).

.DESCRIPTION
  THE GAP THIS CLOSES: Gamma_GuardsFull -- the ~11,400-test regression suite, the rig's
  main safety net -- produced no verdict from 2026-08-31 to 2026-09-02, and every existing
  surface reported it healthy the whole time:

      State           : Ready        <- task_state_guard.py checks exactly this
      LastTaskResult  : 0            <- ...and this
      LastRunTime     : 8/31 07:31   <- nothing read this
      NumberOfMissedRuns : 2         <- nothing read this either

  task_state_guard.py verifies a pinned task is ENABLED and its last result was 0. Neither
  field moves when a task simply never starts, so a task can go dark indefinitely while
  every dashboard stays green. Same shape as the two silent futures outages of August.

  THE MECHANISM (proven 2026-09-02 by a 7/7 differential, not assumed): quiet mode disables
  ~120 Gamma tasks for J's evening and HOLDS the blackout past the 23:00 ET clock while a
  fullscreen app is foreground. A trigger inside a hold is skipped -- and because the task
  was Disabled rather than merely unavailable, StartWhenAvailable cannot recover the fire.
  On 2026-09-01 that ate GuardsFull (23:15), FuturesBrokerProbe (23:05) and GuardsNightly
  (00:30) while SpendSummary (23:30), OosCheck (23:40), LicenseMonitor (23:58) and
  GateExpiryCheck (01:00) all ran fine -- seven tasks, seven correct predictions.

  setup/scripts/scheduled_task_staleness.py reads LastRunTime + NumberOfMissedRuns for
  every Gamma_* task, derives a staleness bar from each task's OWN trigger cadence, and
  NAMES the quiet-hold cause when the evidence supports it. Report only: never enables,
  disables, starts or kills anything (pinned by a test).

  TIMING -- 05:45 ET is deliberate. The tasks it monitors fire 23:00-01:00 ET, so it must
  run after them; it must also land before the 08:00 ET premarket chain so a dark nightly
  guard is known before the trading day. 05:45 ET sits inside quiet mode's LOUD maintenance
  band (23:00-08:00 ET) with margin on both sides.

  SELF-SILENCING GUARD: this task is in quiet_mode.py's ESSENTIAL set, so the blackout can
  never disable the one instrument whose job is reporting what the blackout disabled. A
  monitor that its own subject can switch off is not a monitor (cf. the prereg-hygiene
  orphan-proxy self-silencing bug found 2026-09-01).

  WIRING PATTERN (flash-free, cloned from install-prereg-hygiene.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> scheduled_task_staleness.py
  System pythonw (pure stdlib, no third-party deps).

  Output:
    automation/state/scheduled-task-staleness.json -- latest report
    automation/state/logs/run-cmd-hidden-<date>.log -- the real exit code, dated
  Consumed by setup/scripts/self_check.py as a thin passthrough (never recomputed there).

  To verify: Get-ScheduledTask -TaskName Gamma_TaskStaleness | Get-ScheduledTaskInfo
  To test now: Start-ScheduledTask -TaskName Gamma_TaskStaleness
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_TaskStaleness" -Confirm:$false

  Per CLAUDE.md OP-3 ($0, pure Python) + OP-25 (fail loud, never silent) + OP-33
  (visibility is the product). Guard:
  backtest/tests/test_scheduled_task_staleness_2026_09_02.py.
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\scheduled_task_staleness.py"
$taskName     = "Gamma_TaskStaleness"

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# Daily 03:45 LOCAL (Mountain) = 05:45 ET.
$trigger = New-ScheduledTaskTrigger -Daily -At "03:45"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Scheduled-task staleness reporter (2026-09-02): reads LastRunTime + " + `
    "NumberOfMissedRuns for every Gamma_* task -- the two fields nothing in the rig read, " + `
    "which is how Gamma_GuardsFull went dark 08-31..09-02 with State=Ready and " + `
    "LastTaskResult=0. Derives a staleness bar from each task's own trigger cadence and " + `
    "names the quiet-mode-hold cause when the evidence supports it. Writes " + `
    "automation/state/scheduled-task-staleness.json; consumed by self_check.py as a thin " + `
    "passthrough. NEVER enables/disables/starts/kills anything -- report only. Daily " + `
    "03:45 MT (05:45 ET), inside the LOUD maintenance band and before premarket. Pure " + `
    "stdlib Python, `$0. Guard: " + `
    "backtest/tests/test_scheduled_task_staleness_2026_09_02.py.") `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $taskName for daily 03:45 MT (05:45 ET)"
Write-Output "    Report:   automation\state\scheduled-task-staleness.json"
Write-Output "    Test now: Start-ScheduledTask -TaskName $taskName"
Write-Output "    Next run: $($info.NextRunTime)"
