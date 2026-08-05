# Lesson candidate: a Task Scheduler task can silently STOP auto-firing for >24h with zero error signal, even though it is Enabled/Ready and its last run succeeded

**Date:** 2026-07-31 (conductor AFTERHOURS fire)
**Class:** C7 (silent success is failure) sibling -- a scheduling-layer analogue of the 2026-07-30 blind-engine incident, one level below the file-freshness symptom it produced.

## What happened

`Gamma_TradeToday`, `Gamma_BrokerFills`, and `Gamma_EmaSnapshot` (and, per a
`Get-ScheduledTask`/`Get-ScheduledTaskInfo` sweep of the whole `Gamma_*` fleet, a
cluster of ~17 more tasks spanning trigger times from 07:46 to 15:30 local) all
last successfully fired on 2026-07-29 and then never fired again through all of
2026-07-30, despite:

- `Settings.Enabled = True`, `State = Ready` (not Disabled -- ruled out the
  2026-07-30 `levels_blind` root cause, task-disabled-in-Scheduler).
- `LastTaskResult = 0` on their last actual run (the script itself did not error).
- No hung/zombie process for any of the three scripts found on the box
  (`Get-CimInstance Win32_Process` sweep, clean).
- No system reboot (`LastBootUpTime` = 2026-07-17, ten days earlier) and the
  `Schedule` service `Status = Running` throughout.
- A manual `Start-ScheduledTask` succeeded immediately and re-ran the script to
  completion (confirmed by the output file's mtime updating).
- `NumberOfMissedRuns` was large and nonzero (195 / 43 / 1) -- Task Scheduler
  itself knew it had missed occurrences, but `StartWhenAvailable=True` did not
  catch it up.
- The `Microsoft-Windows-TaskScheduler/Operational` event log is **disabled** on
  this box (`IsEnabled=False`), so there is no forensic trail for *why* the
  scheduler stopped dispatching triggers for this specific subset of tasks while
  dozens of OTHER `Gamma_*` tasks (including high-frequency ones like
  `Gamma_HeartbeatCore`, `Gamma_ConductorRTH`, `Gamma_TvWatchdog`) kept firing
  normally through the same window.

**Root cause NOT determined.** Every settings field checked (LogonType, Hidden,
Compatibility, MultipleInstances, conditions) was identical between the stalled
tasks and healthy siblings. This is left as a genuinely open Windows Task
Scheduler mystery -- re-enabling the Operational event log
(`wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true`) would give
the next occurrence a forensic trail; that is a good, cheap, non-invasive
follow-up (reads only, no trading-path touch) but was NOT done this fire (scope
discipline -- the remediation shipped was the priority, not the forensics).

## The generalizable lesson

`state_freshness_audit.py` (built 2026-07-30 for the `key-levels.json`
incident) already generalizes the CONSEQUENCE-side detection across every
manifest-listed producer -- and it worked exactly as designed here, catching
all 3 stalls immediately via its `state_freshness` engine-health check. What was
still missing was the CAUSE-side assumption baked into every existing watchdog
(`Invoke-TvLaunchSafe`, `Invoke-LevelRefreshSafe`): **"a scheduled task not
running means it crashed or hung, so kill+relaunch the process."** That
assumption is FALSE here -- there was no process to kill. The actual failure
mode is "Task Scheduler itself silently declined to dispatch the trigger,"
which no existing instrument modeled.

**Generalizable guard, shipped this fire:**
`setup/scripts/state_freshness_selfheal.py` -- for any RED
`state_freshness_audit` entry, resolve the manifest's `task` field to a single
`Gamma_*` scheduled-task name and force `Start-ScheduledTask` on it directly
(no process-kill step needed, since the failure is scheduler-side, not
process-side). Cooldown-guarded, fail-open, wired into the existing 5-min
`Gamma_TvWatchdog` cadence. This is a DIFFERENT remediation shape than the
existing kill-tree+relaunch pattern and is the right one for "the trigger
itself never fired" as opposed to "the process wedged."

## Suggested follow-up (not done this fire -- queued)

1. Re-enable `Microsoft-Windows-TaskScheduler/Operational` so a future
   recurrence has forensic evidence (`wevtutil sl ... /e:true`).
2. If the pattern recurs, correlate the stall's start time against ANY
   concurrent event (git commit, another conductor fire, antivirus scan,
   Windows Update) with second-level precision -- this fire only had
   minute-level LastRunTime granularity to work with.
3. Consider whether the sheer COUNT of registered `Gamma_*` scheduled tasks
   (80+, several with 1-minute repetition intervals) is itself contributing to
   an undocumented Windows Task Scheduler dispatch-queue limit -- worth a
   literature check if this recurs.
