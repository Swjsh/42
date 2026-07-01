# Lesson: a hardcoded recent-window data file + a stale comment can fake a "data-blocked" wall over data you already have

**Date:** 2026-07-01
**Surfaced by:** conductor fire (range-scalp wide-window probe)
**Theme fit:** C14 (dead/stale knob — vary-and-assert), C4 (disclosure/OOS), C7 (silent-success — audit the actual data span, not a comment's claim)

## Symptom
The range-scalp thread was declared CLOSED / DATA-GATED across ~10 consecutive fires:
"n=8 on the 25-day OPRA window, cannot tune to significance, WIDEN THE DATA WINDOW —
and data-widening is BLOCKED." That "25-day OPRA wall" was then cited as a *shared*
constraint blocking multiple other threads (bull frontier, GEX rung), reinforcing an
"everything is data-gated, no armable edge" standing conclusion.

## Root cause
`range_scalp_probe.py` hardcoded `RECENT_SPY_CSV = spy_5m_2026-05-19_2026-06-26.csv`
(25 days) with the comment: *"the grinder's _runner.load_data master only covers
through ~2026-05-22."* That comment was STALE. Verified 2026-07-01:
- `spy_5m_2025-01-01_2026-06-18.csv` + matching VIX master = **533 days** on disk.
- OPRA real-fills cache = **370 0DTE days** (2025-01-02..2026-06-26, 8505 contract files).
The full history to widen the window ALREADY EXISTED. The probe never hit a real data
wall — it read a narrow file because a one-line comment (true when written, false a
few master-refreshes later) was taken as ground truth and never re-verified.

## Why it persisted 10 fires
No one re-checked the actual data span; each fire inherited the previous fire's
"data-blocked" conclusion from STATUS/queue and reasoned forward from it. A stale
*claim about data* propagated as if it were a *measured fact about data*.

## Fix (shipped this fire)
- Verified the real span (data-coverage.json + globbed the option contract files).
- New `range_scalp_widewindow_probe.py` runs the SAME regime-gated Tier-2 fade over
  the FULL 2025-01..2026-06-18 history: n went **8 -> 155**. Honest verdict =
  DIES_ON_SLIPPAGE (gross +$3.97/tr, breakeven 0.66c << 5c realistic; top-3 days 161%
  of net; flat in-sample 2025). The thread now closes for the RIGHT, data-rich reason.
- Guard `test_range_scalp_widewindow.py` asserts the probe points at the FULL master
  (window > 12 months, files exist, not the retired 25-day CSV) so the false
  "data-blocked" conclusion cannot silently return.

## The rule
When a probe or conclusion rests on a data-coverage claim ("the data only goes to
X" / "we only have N days"), **re-measure the data span from the source before
inheriting the claim** — especially a claim carried in a code comment or a prior
STATUS entry. A hardcoded window file is a C14 stale knob: vary it (point at the
master) and assert the sample actually widens. "Data-blocked" is a testable
statement, not a standing assumption — test it before it closes a thread, and never
let it become a *shared* wall cited by other threads without one fresh measurement.
