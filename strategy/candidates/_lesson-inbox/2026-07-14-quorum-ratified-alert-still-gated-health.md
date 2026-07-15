# Lesson candidate: a self-diagnosed benign alert still gated overall_health RED

**Date:** 2026-07-14/15 (overnight Lane C, CRYPTO-GYM-V02-V12-FOLLOWUP)
**Source:** queue.md CRYPTO-GYM-V02-V12-FOLLOWUP root-cause task
**Theme fit:** C7 (silent success/noise -- audit outputs, not exit codes) + L169's harvester
fix, but at a DIFFERENT layer (`track_drift.py`'s health rollup, not `gym_harvester.py`'s
CRITICAL-queueing) -- the same anti-pattern reappeared one hop upstream.

## Symptom
`crypto/data/scorecards/drift_report.json` `overall_health` flipped RED on `v02_source_parity`
dips repeatedly (STATUS.md 2026-07-02 and 2026-07-11 entries, 370+ consecutive fail-streak
episodes), even though `track_drift.py::build_report` was ALREADY computing and printing
the correct diagnosis in the alert text itself: `"-- but v15 (3-source) = 100.0% in same
window, likely single-provider artifact"`. The code knew the answer and reported RED anyway.
The 2026-07-11 09:47 ET note explicitly deferred this ("separate pre-existing rolling-window
degradation... not chased tonight") without ever closing the loop.

## Root cause
`crypto/benchmarks/track_drift.py::build_report` (pre-fix) appended EVERY stage dip
(`rate < 95%`) to a single flat `alerts` list, including v02's, then computed
`overall_health = "RED" if alerts else "GREEN"`. The v15 ratifier's own pass rate was already
being READ into the message string for context, but never used to decide whether the alert
should actually be load-bearing. Diagnosing an artifact and still gating on it is "papering"
by omission -- the fix (5bp->7bp tolerance, 2026-05-23) had already been tried once for the
underlying validator and didn't help, because the true mechanism is v02 being a strict
2-source check that structurally cannot avoid disagreeing when one source (yfinance) settles
its close after the other (coinbase) -- documented in `v15_three_source_parity.py`'s own
docstring, which exists specifically as v02's "outer-layer ratifier."

Separately, `crypto/validators/v12_multi_timeframe.py::_compare` used a ZERO-tolerance
pass criterion (`len(vol_disagreements) == 0`) against a confirmed-rare (2 incidents in
17,656 grinder iterations spanning a month, both isolated single bars, both agg>native,
never reconciling over ~3h in-window) same-provider cross-granularity Coinbase settlement
artifact -- letting one rare, real-but-benign glitch flip `pass=False` for the ~91 fetches
(~3h) it stayed inside the live 200-bar fetch window, dragging the 24h rolling rate to ~87.5%.

## Fix (shipped this fire)
1. `track_drift.py::build_report` now splits `alerts` (all, unchanged, for OP-33 visibility)
   from a new `blocking_alerts` field (the subset that drives `overall_health`). A v02 dip is
   demoted to informational-only when v15's SAME-WINDOW quorum vote is healthy (>=95%); the
   grinder-level `source_parity_drift_24h` alert is similarly demoted only when >=90% of the
   drifting iterations are same-ITERATION ratified by v15's per-iteration `pass`. Both stay
   fully visible in `alerts`/console output (tagged `[info-only]` vs `[BLOCKING]`), never hidden.
   `setup/scripts/run-crypto-regression.ps1`'s STATUS.md writer now keys its change-detection
   text off `blocking_alerts` instead of the full `alerts` list.
2. `crypto/validators/v12_multi_timeframe.py::_compare` gained `max_vol_outlier_bars` (default
   1): volume disagreements tolerate up to 1 isolated bar per run (matches the confirmed
   real-world incident shape); price stays true zero-tolerance (0/17,656 price disagreements
   ever, so a real price-aggregation bug would still fail hard).
   Guarded by `crypto/benchmarks/test_track_drift.py` (5 tests: ratified-informational,
   unratified-still-blocks, unrelated-stage-still-blocks, grinder-level ratified/unratified)
   and `v12_multi_timeframe.py::run_offline` T7-T9 (isolated outlier tolerated, 2 outliers
   still fail, price disagreement still fails).
   Verified: `python crypto/validators/runner.py --skip-replay` -> `passed=103/103
   overall_pass=True`; `python -m pytest crypto/ -q` -> `91 passed`.

## Generalizable principle
When a monitor computes the SAME diagnostic evidence a human would use to dismiss an alert
(a ratifier/second-opinion check, a rarity count, a self-heal-over-time pattern) but then
still gates severity on the raw symptom alone, the diagnosis is decorative, not functional.
If the code can already tell you "this is benign," that conclusion must reach the
pass/fail or RED/GREEN decision, not just the log line next to it. Applies one layer above
L169 (gym_harvester's CRITICAL-queueing): the same discipline is needed at EVERY layer
between "raw stage failure" and "the human-facing health verdict," not just the first one
that got fixed.

## Encoded in
`crypto/benchmarks/track_drift.py` (`build_report`, `_grinder_source_parity_drift`),
`crypto/validators/v12_multi_timeframe.py` (`_compare`, `MAX_VOL_OUTLIER_BARS`),
`setup/scripts/run-crypto-regression.ps1`, guard tests
`crypto/benchmarks/test_track_drift.py` + `v12_multi_timeframe.py::run_offline` T7-T9.

## L## (optional)
Suggested L201 (L200 is the latest as of 2026-07-14 per LESSONS-LEARNED.md); lesson-author
greps for max and assigns next.
