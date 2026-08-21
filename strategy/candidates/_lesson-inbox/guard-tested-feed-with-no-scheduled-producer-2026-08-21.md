---
filed: 2026-08-21
filed_by: conductor (AFTERHOURS fire, ~00:59-01:20 ET)
kind: lesson
status: pending
---

# `earnings_calendar.py`'s output was fully guard-tested but had NO scheduled task — the feed was guaranteed to go BROKEN on a timer

## Symptom

`self_check.py` verdict was `BROKEN`: `EARNINGS-CALENDAR STALE (RED): earnings-blackout.json
is 49.4h old (fail-closed threshold 48h, params.json#entry.
earnings_feed_stale_hours_fail_closed)`. `automation/state/weekly/earnings-blackout.json`
carried `generated_at_et: 2026-08-18T23:14:30` and had not moved since. No Windows
scheduled task named anything like `*Earnings*` existed on the box (`Get-ScheduledTask`
returned zero rows) — the file had been written exactly once, by hand, on 2026-08-18, and
never again.

## Root cause

The producer (`setup/scripts/earnings_calendar.py`, a two-source yfinance+Nasdaq
earnings-blackout feed for the weekly-1 lane) and its freshness guard
(`self_check.py#check_earnings_calendar_freshness`, `backtest/tests/
test_self_check_earnings_calendar_freshness.py`, 46/46 passing) were BOTH built and fully
tested on 2026-08-18 in the same workstream — but the workstream stopped at "the check
exists and is guard-tested," never reaching "and something actually re-runs the producer
on a cadence." A near-identical sibling producer, `macro_calendar.py`, already had a
working installer (`setup/scripts/install-macro-calendar.ps1`, registered task
`Gamma_MacroCalendar`, verified `LastTaskResult=0`) sitting right next to it in the same
directory the whole time — the pattern to copy was one `ls` away and was never applied.

Because `params.json#entry.earnings_feed_stale_hours_fail_closed` is a fixed 48h window,
a hand-run-once file is not a one-time gap — it is a **guaranteed future RED on a timer**,
identical in shape to L252/the state-freshness-detector lesson ("a detector without an
automatic remediator/producer re-violates on its own schedule"), except one layer
upstream: here the DETECTOR was fine, but the THING BEING DETECTED (the producer) had no
scheduler at all, not even one that silently stopped firing.

## Generalizable rule

**A fail-closed consumer contract is only as good as its producer's cron.** Whenever a
new state file gets a staleness/freshness guard (self_check check, contract, drift
ratchet), the SAME PR/fire must also confirm — by literally running
`Get-ScheduledTask -TaskName '*<Producer>*'` — that something re-writes that file on a
cadence tighter than the guard's own threshold. "I wrote the check" and "I wired the
producer" are two different verbs and both are required; shipping only the first
guarantees the second becomes a future RED, discovered by whichever fire happens to run
`self_check.py` after the clock runs out.

## Fix applied this fire

Copied `install-macro-calendar.ps1`'s exact wiring (`wscript -> run_exe_hidden.vbs ->
system pythonw -> run_cmd_hidden.py --cwd <repo> -- system pythonw -> earnings_calendar.py`)
into a new `setup/scripts/install-earnings-calendar.ps1`, registered `Gamma_EarningsCalendar`
at 07:50 ET weekdays (before `Gamma_Premarket` 08:30 ET, well inside the 48h window every
single day), manually fired it once to prove the whole hidden-relay chain actually runs
(`Start-ScheduledTask` -> `LastTaskResult=0` -> feed's `generated_at_et` refreshed ->
`self_check.py` verdict flipped BROKEN -> GREEN, live-verified, not assumed). Registered
in `automation/state/SCHEDULED-TASKS.md` next to `Gamma_MacroCalendar`.

## Suggested next step (bounded, Sonnet-appropriate)

Grep the repo for every `self_check.py#check_*_freshness` function, list the state file
each one guards, and for each one confirm a matching `Get-ScheduledTask` producer exists
with a firing cadence tighter than that check's own stale-threshold. Any check with no
matching producer is the SAME bug as this one, just not yet aged past its threshold —
fix it now rather than waiting for each one to independently go BROKEN on its own clock.

## Suggested L# slot

New lesson under C14 (Dead/translated-but-unapplied knobs) or C7 (Silent success is
failure) — this is the inverse of C14's usual shape (a knob nobody wired IN) and a sibling
of L252/the state-freshness-detector lesson (a check nobody wired a remediator FOR): here
neither a knob nor a remediator was missing, the PRODUCER'S OWN SCHEDULE was missing,
despite a working sibling installer sitting in the same directory the whole time.
