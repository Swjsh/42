---
filed: 2026-08-23
filed_by: conductor-weekend fire (SPY 0DTE #1 desk pick, followed by desk_allocator false-positive investigation)
kind: lesson
status: pending
---

# A raw `age_h > STALE_H` freshness check on a weekday-market-hours-only producer is guaranteed to false-positive every weekend

## Symptom

`desk_allocator.py` (which ranks which of the firm's 4 desks earns the next conductor fire)
flipped its own ranking mid-fire: at 22:00:23 it reported the Futures desk as `#1 NEXT FIRE`
(60 pts, `+40 BROKEN (shadow desk)`), while at 22:00:57 — after a completely unrelated
`self_check.py` refresh happened to touch nothing futures-related — the SAME futures lanes
were still on-disk unchanged and the desk was STILL scored `+40 BROKEN`. Investigating: the
five futures lane files (`trader/heartbeat.json`, `shadow-progress.json`, etc.) all last wrote
Friday 2026-08-21 ~13:55-15:15 local (market close). The check ran on Sunday 2026-08-23
00:00 ET. `age_h` was therefore ~34-58h > the 24h `STALE_H` threshold — not because anything
broke, but because Saturday+Sunday exist and the lane only ticks during weekday RTH.

Same defect independently inflated `assess_multi_sector`'s `dead_signal=True` ("do not
polish a corpse") flag on the SAME desk-allocator run — a live, un-killed 15-min RTH shadow
lane (multi-1) was reported dead purely because it was the weekend.

## Root cause

`STALE_H = 24.0` is a flat wall-clock threshold applied via `_age_h(path) > STALE_H`. It has
no concept of "this producer only runs on weekdays." Any lane that ticks once per RTH day
crosses 24h stale reliably every Saturday and stays crossed through Sunday — the check cannot
distinguish "the market is closed" from "the process died."

## Why this is a CLASS, not a one-off

This is the exact same false-positive SHAPE as the 2026-08-21 `armable_unarmed` fix in the
same file (a static/wall-clock-derived signal read as permanently true once tripped, with no
mechanism to notice the underlying condition resolved) — just on a different field
(`broken`/`dead_signal` instead of `armable_unarmed`). The file had ALREADY paid the cost of
this bug class once and did not generalize the fix to its sibling staleness checks.

More generally: **any freshness/liveness check on a producer whose write cadence is gated by
a calendar (weekday-only, RTH-only, trading-day-only) must be judged against that calendar,
not against raw wall-clock hours.** `engine-health.json`'s own checks already encode this
correctly (`"market closed -- quiet OK"` branches throughout `engine_health.py`); this file's
own sibling desk assessor (`assess_spy`) inherits that correctness for free by reading
`engine-health.json`/`self-check-last.json` rather than raw file ages — but `assess_futures`
and `assess_multi_sector` compute staleness directly from `Path.stat().st_mtime`, bypassing
that protection entirely.

## The fix

Judge staleness against the most recently COMPLETED trading day (weekday, non-holiday, date
strictly before today), not raw hours — mirrors `self_check.py`'s own
`_last_completed_trading_day`, deliberately duplicated inline (not imported) to keep
`desk_allocator.py` free of cross-module import coupling per its own "pure Python, $0" header.
A lane is broken only if its last-write ET calendar date is before that day. This accepts the
same ~1-calendar-day detection lag `self_check.py`'s sibling check documents as an intentional
tradeoff (real intraday RTH liveness is owned by faster checks: `engine-health.json`'s
`heartbeat_safe`/`heartbeat_bold`, `self_check.py`'s own live-tick checks — this allocator's
job is next-fire *prioritization*, not incident *detection*).

Verified the fix still discriminates correctly: multi-1's `shadow-ledger.jsonl` last wrote
**Thursday** 2026-08-20 19:32, and Friday 2026-08-21 was a real, non-holiday trading day — so
after the fix it is STILL correctly flagged broken (a genuine, separate issue: multi-1
apparently did not tick at all on Friday — left as a follow-up, not fixed this fire, since
diagnosing it is a second bounded task).

## Guards

- `backtest/tests/test_desk_allocator_weekend_staleness_2026_08_23.py` — 5 tests: Friday-close
  read on Sunday is NOT broken; Thursday-dark-through-a-real-Friday-session STILL is broken
  (proves the fix isn't a rubber stamp); missing file is always broken; weekday-morning
  before today's session hasn't started is not broken; end-to-end `assess_futures()` no
  longer carries the false BROKEN penalty.

Fix: `d634614f` (`setup/scripts/desk_allocator.py`).

## Open follow-up (not this fire's scope)

`multi/shadow-ledger.jsonl` genuinely stopped ticking after Thursday 2026-08-20 19:32 despite
Friday 2026-08-21 being a real trading day with no holiday — `Gamma_MultiCore`'s Friday
session needs investigating (task scheduler history, log tail) by whoever next picks the
multi-sector desk. Not urgent (shadow-only, no money at risk) but is a genuine break the
weekend-staleness fix correctly continues to surface.
