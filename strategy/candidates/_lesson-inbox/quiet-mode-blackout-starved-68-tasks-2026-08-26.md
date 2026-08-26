---
kind: lesson
date: 2026-08-26
severity: high
theme: C7 (silent success is failure) + C15 (gates interact multiplicatively)
---

# A blackout window plus a task that only fires inside it equals a dead task

## Symptom
On 2026-08-26 00:34 ET, `unattended_health.py` reported **RED: 18 RED / 43 YELLOW,
only 5 GREEN** across 67 units. 131 of 146 `Gamma_*` scheduled tasks were Disabled.
The EOD pipeline had produced no deep-dive since 2026-08-21; the nightly guard suite
had not run since 08-23; `winner-signature.json` and `day-throttle-shadow-summary.json`
were both stamped 08-24 and had stopped advancing.

## Root cause
Quiet Mode (`setup/scripts/quiet_mode.py`, shipped 2026-08-24 on J's "everything needs
to be turned off after market hours") blacked out **16:00 -> 08:00 ET plus all weekend**.
Its own logic was correct and provably reversible: it recorded every task's prior state,
disabled the non-essential set, and restored 111/111 each morning (verified in
`quiet-mode.log` at 2026-08-25T08:02).

The defect was the WINDOW, not the mechanism. **68 tasks have their only trigger inside
that window.** Each was disabled before its trigger time and re-enabled after it — every
night, cleanly, forever. They never fired again. The blackout and the trigger schedule
were each individually correct; their INTERSECTION was the outage.

Worse, the failure was structurally invisible: the watcher that would have caught it
(`Gamma_UnattendedHealth`, 02:02 ET) was itself in the starved set, so it froze on its
last pre-quiet-mode snapshot and kept serving a stale GREEN-ish board.

## Why nothing caught it
1. No guard compared trigger times against the blackout window — a new interaction with
   no test, shipped the same day.
2. The `guards-nightly` health unit watched `automation/state/guard-watch.json`, which is
   written by the per-EDIT PostToolUse hook, NOT by `Gamma_GuardsNightly` (which writes
   `guard-watch-slow.json`). The unit was reporting whether someone had recently edited a
   file — motion, not function (C7). It would have gone GREEN on any file edit while the
   nightly suite stayed dead.

## Fix (2026-08-26)
* `quiet_mode.py`: post-close grace to **18:00** (the 16:00–17:45 EOD chain completes) and
  a **LOUD maintenance band 23:00–08:00** every day including weekends (J is asleep; a
  popup costs nothing, a dead guard costs everything). Quiet is now weekday 18:00–23:00
  plus weekend 08:00–23:00 — it still covers J's evening, which was the actual directive.
* Re-timed the 10 remaining evening-only tasks into the 23:0x ET band, keeping the same
  calendar day so no date-rollover bug is introduced.
* `backtest/tests/test_quiet_mode_starvation.py`: asks the LIVE Task Scheduler for every
  enabled task's trigger hours and FAILS if any task's reachable fire hours are a subset
  of the blackout hours. RED-proofed against the real 10 before the re-time, GREEN after.
* Repointed the `guards-nightly` health unit at `guard-watch-slow.json`.

## The generalizable rule
**Any mechanism that disables things on a schedule must be tested against the schedules of
the things it disables.** A blackout is not a property of the blackout alone — it is a join
against every trigger in the system. Ship the join as a test, or the intersection will be
discovered by a two-day outage nobody saw.
