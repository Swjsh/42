## Lesson candidate: a single-fire daily `-Weekly ... -At` scheduled trigger can silently skip a day even with `StartWhenAvailable=True` and the box continuously awake — needs a bounded repetition window, not just staleness detection

**Symptom (2026-08-25 conductor fire, AFTERHOURS mode):** `self_check.py` flagged
`MACRO-CALENDAR STALE (RED)` — `automation/state/macro-calendar.json`'s freshness stamp
was ~24.5h old, one full day behind. `Get-ScheduledTaskInfo -TaskName Gamma_MacroCalendar`
showed `LastRunTime` stuck on the PRIOR weekday, `NumberOfMissedRuns=1`, and `NextRunTime`
already advanced PAST today to the day after — i.e. Windows Task Scheduler itself recorded
the miss and moved on without ever catching up, despite `StartWhenAvailable=True` being set.

**Ruled out, with evidence:**
- Not asleep: `automation/state/logs/run-cmd-hidden-2026-08-25.log` shows other same-cadence
  tasks (`window_leak_detector_keepalive`, every ~2-5 min) firing continuously straight
  through the 05:45 MT trigger window with zero gap — the box was awake the whole time.
- Not on battery: `Get-CimInstance Win32_Battery` returns nothing — this is a desktop, always
  on AC, so `DisallowStartIfOnBatteries` cannot be the cause.
- Not the L229 wscript-fire-and-forget-masks-a-real-exit-code class: `NumberOfMissedRuns=1`
  means Windows itself correctly identified the miss — this is a genuinely different failure
  mode (Task Scheduler dropped the occurrence, not "ran but the wrapper hid the failure").
- No forensic trail available: `Microsoft-Windows-TaskScheduler/Operational` is DISABLED on
  this box (`wevtutil gl` → `enabled: false`), and enabling it from a non-elevated shell fails
  (`Access is denied`) — so the root Windows-internal cause of the drop is undiagnosable from
  here. Left for J (one-time elevated `wevtutil sl Microsoft-Windows-TaskScheduler/Operational
  /e:true`) if a future incident needs deeper forensics.

**Root cause (mechanism-level, what we CAN say):** a `-Weekly ... -At "HH:MM"` trigger fires
exactly once per matching day. If Task Scheduler drops that one occurrence for any reason
(scheduler service hiccup, a coinciding trigger storm, timing jitter around the exact second),
there is no second chance until the next day — `StartWhenAvailable` only catches up misses
caused by the machine being unavailable (asleep/off/on battery when disallowed), not a dropped
occurrence on an available machine. **This is a re-violation of the same producer's own
2026-07-15 miss** (`test_self_check_macro_calendar_freshness.py`'s docstring: an overnight
Windows-Update reboot chain cut the interactive logon session through the same 05:45-06:00 MT
window) — two independent root causes (reboot-caused vs. undiagnosed scheduler drop), same
single-fire vulnerability, same downstream deadline (`Gamma_Premarket` 08:30 ET needs a fresh
macro/earnings feed for CPI/FOMC/NFP/earnings no-trade-window coverage). Detection
(`self_check.py`) already existed both times and worked correctly both times — what was
missing both times is SELF-HEALING; a twice-hit class with only a detector and no repair is
exactly the re-violated-lesson-must-become-a-guard case (OP-25).

**Fix shipped this fire:** `install-macro-calendar.ps1` and `install-earnings-calendar.ps1`
(the sibling producer, same single-fire shape, same consumer deadline, fixed pre-emptively
rather than waiting for its own live miss) now attach a bounded repetition window to the
primary `-Weekly` trigger — 15-min interval, 30-min duration, mirroring `Gamma_TvWatchdog`'s
re-check cadence. Both producers are cheap (~1-2s) and idempotent (a fresh re-run when
already-fresh just no-ops), so the extra fires change nothing on a normal day; a single
dropped occurrence now gets up to 2 more chances within 30 min, well inside the ~40-45 min
gap to Premarket's 08:30 ET read.

**Generalizable check for a future fire:** grep every `install-*.ps1` whose task feeds a
single-fire `-Weekly ... -At` trigger into a hard downstream deadline (anything
`self_check.py` treats as fail-closed/RED-on-stale) for a MISSING `.Repetition` assignment —
this is the exact same pattern class as the earnings-calendar interpreter-wiring bug
(install script copies a sibling's shape but the shape itself was already incomplete).

**Live actions taken, verified:**
- Manually re-ran `macro_calendar.py` — `self_check.py` verdict `MACRO-CALENDAR STALE`
  cleared, `unattended_health.py` transitions log confirmed `Macro calendar / scout:
  YELLOW -> GREEN (recovered)`.
- Both install scripts re-registered live: `(Get-ScheduledTask -TaskName
  Gamma_MacroCalendar).Triggers[0].Repetition` / same for `Gamma_EarningsCalendar` both
  confirm `Interval=PT15M / Duration=PT30M` on the real, currently-registered task
  definitions (not just in source).
- New guard `backtest/tests/test_daily_feed_trigger_selfheal_2026_08_25.py` (static
  source-parse, no live TS query) pins the repetition assignment on both install scripts +
  bounds the duration against the Premarket deadline + a vacuity check against the
  known-broken (no-repetition) shape. 6/6 pass alongside all pre-existing sibling install-
  script/self-check guards (70/71, 1 pre-existing skip, unrelated).

**Suggested L## anchor category:** C7 (silent success is failure — audit outputs, not exit
codes) and/or a new sub-theme under C14 (dead/translated-but-unapplied knobs) is close but not
quite right — this is closer to "detection without repair is half a fix." Lesson-author:
please pick the best-fit existing theme or flag if this warrants a new one; the closest sibling
is L229 but the mechanism is materially different (Windows-recorded miss vs. masked exit code)
so a cross-reference rather than a merge seems right.
