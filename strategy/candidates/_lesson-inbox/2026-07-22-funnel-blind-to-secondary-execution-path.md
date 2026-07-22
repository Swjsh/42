# Lesson candidate: a monitoring tool must enumerate every producer path, not just the primary one

> Queued by conductor (AFTERHOURS) 2026-07-22. lesson-author picks up at next wake fire.

## Symptom
`setup/scripts/fill_funnel.py` (the "is it actually trading?" instrument, OP-33e) read
`core:safe`'s 2026-07-22 day as `enter=0 / attempted=0 / accepted=0`, and its own
verdict line keyed **only** on `totals["enter"]` — so the whole day rendered
`[IDLE]`. That IDLE verdict propagated straight into a J-facing artifact:
`automation/state/gamma-narrative.json`'s `facts_digest` carried the IDLE funnel
line and its LLM narrative text told J **"the system stayed idle"** — on a day
that actually had 2 real broker-truth fills+exits (`exit_pass`, core:safe) and
4 secondary-setup `PLACED` orders (`vwap_continuation` x3, `bollinger_squeeze`
x1) fired via a *second* execution path (`extra_exec`) the funnel never
inspected at all.

## Root cause
`heartbeat_core.py` scores + can place orders for secondary/dormant setups
(`vwap_continuation`, `bollinger_squeeze`, `vix_regime_dayside`, `gap_and_go` —
the "four dormant setups" first flagged in the 2026-06-26 self-audit gap batch)
via an `extra_exec` list attached to each core-decisions row, entirely separate
from the primary `verdict`/`exec` ENTER pipeline. `fill_funnel.py`'s
`_acct_funnel()` was written against the primary pipeline only and had zero
references to `extra_exec`/`extra_signals` (confirmed via grep: 0 hits before
the fix). The funnel's own `filled`/`exited` stages DID stay correct (they read
broker-truth `exit_pass` records, which are populated independently of which
pipeline placed the order) — but `enter`/`attempted`/`accepted`, the printed
attribution, and critically the final GREEN-vs-IDLE verdict line, were blind to
the second producer. A monitoring tool that hard-codes "the ways work can
happen" as a closed set silently drifts out of sync the moment a new producer
path is added elsewhere in the codebase — exactly the class this repo already
names C7 (silent success is failure) and C14 (dead/translated-but-unapplied
knobs), but from the *observer's* side rather than the knob's side: the knobs
(dormant setups) were live and firing correctly: it was the **instrument
watching them** that had the blind spot.

## Fix
`setup/scripts/fill_funnel.py`: `_acct_funnel()` now tallies every `extra_exec`
row into `extra_setup_placed` (per-setup, per-action counts) and
`extra_placed_total`, additively — the primary `enter`/`attempted`/`accepted`
stages are untouched. The verdict line (`_evaluate()`) now reads
`GREEN if (enter>0 OR filled>0 OR extra_placed_total>0) else IDLE` instead of
`GREEN if enter>0 else IDLE` — closing BOTH root causes (extra_exec activity,
and a broker-truth fill+exit with zero primary-pipeline ENTER rows). Both
`render_text` and `render_markdown` now print the secondary-setup attribution
so it's visible, not just structurally present in the dict. Verified live:
re-ran `fill_funnel.py` against today's real `core-decisions.jsonl` before/after
— `[IDLE]` → `[GREEN]` with the `vwap_continuation=3PLACED / bollinger_squeeze=1PLACED`
line now printed. Re-wrote `automation/state/fill-funnel-2026-07-22.json`
(`--write`) so today's on-disk artifact carries the corrected verdict for the
next consumer read.

## Encoded in
`backtest/tests/test_fill_funnel_guard.py` — 5 new tests (`BUILD 6 guard`
section): `test_extra_exec_attribution_counts_by_setup_and_action`,
`test_extra_exec_placed_flips_idle_to_green` (the exact 2026-07-22 disease,
reproduced synthetically), `test_fill_via_exit_pass_alone_flips_idle_to_green`
(the sibling root cause), `test_genuinely_idle_day_stays_idle` (non-vacuous
bite the other direction — a truly empty day must still read IDLE). 26/26
`test_fill_funnel_guard.py` green (21 pre-existing + 5 new, zero regressions);
57/57 across all `test_self_check_*.py` files also green.

## L## (optional)
Suggested: next available under C7 (silent success is failure) — pattern name
"monitoring/attribution tool blind to a second producer path" — the generic
form: whenever a NEW execution/placement path is added to an engine, every
existing monitor/funnel/dashboard that claims to answer "did X happen today"
must be re-audited for whether it enumerates that new path, not just assumed
to still be complete.
