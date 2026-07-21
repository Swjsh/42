# `run_exe_hidden.vbs`'s `shell.Run cmd, 0, False` makes Task Scheduler's exit code meaningless

**Date:** 2026-07-20 (conductor, AFTERHOURS)
**Class:** new (C7/C8 family — silent success, headless Windows spawn)

## What happened

`self_check.py` flagged `MACRO-CALENDAR STALE (RED)`: `news.json`'s `freshness_stamp` was
`2026-07-15T19:20:11` — ~5 days / ~122h old — even though `Gamma_MacroCalendar` (07:45 ET
daily) showed **`LastTaskResult: 0`, `NumberOfMissedRuns: 0`** in Task Scheduler, including
a "successful" run at 07:45 ET *that very morning*. By every signal Task Scheduler exposes,
the task was healthy. It was not — the underlying Python script had not actually written
fresh state in 5 days, and nothing surfaced that until `self_check.py`'s independent
content-freshness check caught it tonight.

## Root cause

`setup/scripts/run_exe_hidden.vbs` (the standard hidden-daemon launcher used by ~60
scheduled tasks per `SCHEDULED-TASKS.md`, C8's documented pattern) does:

```vbs
shell.Run cmd, 0, False   ' windowStyle=0 (hidden), bWaitOnReturn=False (fire-and-forget)
```

`bWaitOnReturn=False` means `wscript.exe` launches the inner `pythonw.exe <script>.py`
process and **returns immediately without waiting** for it to finish. `wscript.exe`'s own
exit code (which Task Scheduler records as `LastTaskResult`) reflects only "did I
successfully hand off the launch" — **it can never reflect whether the inner Python
process actually ran to completion, crashed, hung, or was later reaped** (the fleet's
3-minute stale-process reaper, `Stop-StaleClaudeProcesses` in `_shared.ps1`, kills
`python.exe` >5 min old unless in `$EXEMPT_DAEMONS` — a plausible silent killer for any
script whose execution + network calls run long some mornings). Task Scheduler shows
`0`/`0 missed runs` for a task whose actual payload script may not have written anything
in days. No log path is wired for this launcher (headless-by-design, per C8), so there was
no artifact anywhere to catch this except `self_check.py`'s own independent read of
`news.json`'s content, which happened to be checking freshness already for an unrelated
reason.

Verified this is the mechanism (not theorized): manually ran
`python setup/scripts/macro_calendar.py` this fire — it succeeded immediately, updated
`freshness_stamp` to the current timestamp, `self_check.py` re-run confirmed the
MACRO-CALENDAR STALE finding cleared. The script itself is fine; only the launcher's exit
code is a lie for diagnosing it.

## Recommended graduation (OP-25)

This is a **generalizable, high-leverage** footgun — the same `run_exe_hidden.vbs` pattern
gates ~60 scheduled tasks, and Task Scheduler's `LastTaskResult`/`NumberOfMissedRuns` is
the FIRST place anyone (including a conductor fire) looks to judge "is this task healthy."
Right now that signal is unconditionally green regardless of the payload's actual outcome.
Two complementary fixes, either is a real fire's worth of work (do not attempt to touch
all ~60 tasks in one bounded fire):

1. **Redirect stdout/stderr per-task.** Extend `run_exe_hidden.vbs` (or a new variant) to
   accept an optional log-path argument and pipe the child's output there (e.g. via
   `cmd /c ... > logfile 2>&1` wrapped inside the hidden shell.Run, or switch to
   `WshShell.Exec` + poll, which exposes `Status`/`ExitCode`/`StdOut` without a visible
   window). This alone would have caught 5 days of silent macro_calendar failures (if it
   was in fact failing — worth confirming with the redirected log once wired, since this
   fire could not determine *why* it went stale, only *that* the launcher's exit code
   can't tell you).
2. **A generic "last successful completion" staleness ratchet**, the same shape already
   proven for `heartbeat_safe`/`heartbeat_bold`/`sight_beacon`/`watcher_feed` in
   `engine-health.json` — extend that checker (or `self_check.py`) to cover EVERY producer
   with a `freshness_stamp`/`updated_at`/`as_of` field and an expected cadence, so a stale
   producer surfaces automatically instead of by accident (tonight's catch was luck: the
   PREMARKET STALE investigation happened to also be checking `self-check-last.json`,
   which happened to already carry a macro-calendar freshness rule someone had built —
   `test_self_check_macro_calendar_freshness.py` exists, meaning THIS ONE producer already
   has a dedicated freshness test; most of the other ~60 tasks do not).

Filed as a `queue.md` MED item (`WSCRIPT-FIRE-AND-FORGET-AUDIT`) rather than fixed this
fire — this is infra-breadth work (audit which of ~60 tasks would benefit, pick a launcher
redesign, add tests) that does not fit in one bounded task alongside tonight's primary
today-bias.json repair.
