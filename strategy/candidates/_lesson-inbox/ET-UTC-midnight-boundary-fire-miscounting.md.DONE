# Lesson candidate: cross-midnight ET/UTC date matching via substring is wrong

> Queued by conductor 2026-07-29 ~20:30-21:00 ET. lesson-author picks up at next wake fire.

## Symptom
Self-audit (`analysis/self-audit/new-gaps-flagged.md`) flagged "conductor firing far more than
the documented max_fires (4/day), exhausting the after-hours budget" on THREE consecutive nights
(2026-07-27T17:31, 2026-07-28T17:31, 2026-07-29T17:31). STATUS.md's own QUIET-EXHAUSTED entries
on 2026-07-28 showed the daily fire count climbing past 4 (5, 6, 7, then 8 "fires" reported),
which the note-writer assumed meant duplicate/extra scheduled triggers were somehow firing —
they were not (Task Scheduler triggers were exactly the documented 3/day cadence, confirmed live
2026-07-29 via `Get-ScheduledTask`).

## Root cause
`setup/scripts/conductor_budget.py`'s `spend_today()` matched a `conductor-outcomes.jsonl` row to
a given ET calendar day by testing whether the day string (e.g. `"2026-07-28"`) was a **substring**
of the row's raw `fired_at` field, which is a **UTC** ISO timestamp. ET is UTC-4 (EDT) in July, so
the scheduled 20:30 ET evening fire on day D writes `fired_at` with a UTC **calendar date** of
D+1 (20:30 ET + 4h = 00:30 UTC the next day). Substring-matching against the raw UTC string means
that evening fire's row gets picked up by BOTH day D's own check (correct — it fired then) AND
day D+1's very first budget check the next morning (wrong — it leaked forward), because
`"2026-07-29"` genuinely is a substring of `"2026-07-29T00:30:52+00:00"` even though that instant
is 2026-07-28 20:30 in ET, the calendar the budget is actually kept in.

Net effect: every ET day silently started already "1 fire spent" (sometimes more, compounding
with late-night fires) before its own first legitimate tick — matching the self-audit's repeated
complaint exactly. Live-verified the bug's real-world bite: at STAGE 0 of THIS fire (2026-07-29
~20:30 ET, before the fix), `conductor_budget.py --check` read "2/4 fires" for today; after the
fix, `spend_today('2026-07-29')` correctly reads 0 (the two "fires" were 2026-07-28's own evening/
late-night fires that had leaked forward across the midnight boundary).

The project's existing test fixtures (`backtest/tests/test_conductor_budget.py`) had independently
fallen into the SAME trap: they used `f"{DAY}T02:00:00+00:00"` to represent "a fire during DAY",
but `T02:00:00+00:00` is `T22:00:00` ET the PREVIOUS day — the tests only passed because of the
same substring bug they were meant to be exercising.

This is the same anti-pattern class as the existing TZ-systemic lesson (Bash `TZ` returning UTC
on this Mountain-time box) but one level deeper: even code that correctly SOURCES its ET time via
`et_clock` can still get the comparison wrong if it compares a UTC-stamped log row to an ET
calendar-date string via naive substring/prefix matching instead of converting the UTC stamp to
its true ET date first.

## Fix
`setup/scripts/conductor_budget.py`: added `_stamp_to_et_date()` — parses `fired_at`
(or `ts_et`) via `datetime.fromisoformat`, converts an aware/UTC stamp to its true ET calendar
date via `et_clock.et_now(now_utc=...)`, and only falls back to the old substring match when the
stamp fails to parse (fail-open, C7 — a governor must never crash or block on a malformed row).
Naive stamps (the `ts_et` convention, already ET-local) are used directly with no conversion.
Commit `631798f0`. 3 new regression tests pin the exact incident shape (RED-proofed via
`git stash`, all 3 failed pre-fix with the predicted count, 16/16 green post-fix). Curated safety
gate 59/59 PASS. Zero trading-path touched.

## Encoded in
`backtest/tests/test_conductor_budget.py::test_evening_et_fire_does_not_leak_into_next_day`,
`::test_late_night_fire_counts_for_its_own_et_day_not_the_next`,
`::test_early_morning_utc_fire_counts_for_previous_et_day` — permanent regression guards against
this exact class recurring in `conductor_budget.py`. **Generalizable rule for lesson-author to
carry forward:** any code that buckets a UTC-stamped event by ET CALENDAR DATE must convert the
stamp to ET via `et_clock` before comparing dates — never substring/prefix-match a UTC ISO string
against an ET date string, even when the ET date itself was sourced correctly via `et_clock`.

## L## (optional)
Next available (lesson-author greps `markdown/doctrine/LESSONS-LEARNED.md` for max, currently
L249+1 = suggest L250). Cross-reference C6 (no-look-ahead/date-slice discipline) and C9
(anchor-to-truth-source discipline) — this is a new leaf of that same family, not a duplicate.
