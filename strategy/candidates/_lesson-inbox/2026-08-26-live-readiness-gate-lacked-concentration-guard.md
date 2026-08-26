# The single highest-stakes monitoring instrument (live-money readiness) was the 4th confirmed instance of "mean without a concentration guard is not a verdict"

**Found:** 2026-08-26, conductor AFTERHOURS fire (05:30 ET), picked via `desk_allocator.py` +
`task_scorer.py` STAGE 1 sweep of `MONITORING-INSTRUMENTS-LACK-CONCENTRATION-GUARDS`
(queue.md, filed 2026-08-23 Opus adjudication).

**Root cause:** `setup/scripts/live_readiness.py::score_round_trips` — the instrument that
computes CLAUDE.md's "Live threshold (per account independently): >=20 trades, WR>=45%,
positive expectancy, <=2 rule breaks" — emitted a bare `PASS` off `statistics.fmean(pnls)` >
0 with no concentration term, the same shape already caught and fixed THREE times the same
week in `gate_expiry_check.py::costing_verdict` (structure_veto_enabled,
require_bearish_fill_bar — commit `71c39545`) and `core_strategy_recency.py::direction_verdict`
(the 2,767%-of-net-from-2-days BULL GREEN that triggered a 13-agent investigation into a
mechanism that did not exist). `live_readiness.py` was even NAMED as a candidate in the
tracking queue item, but nobody had gotten to it — it sat unaudited for 3 days despite being
arguably the highest-stakes instance of the whole class: a bare PASS there is the evidence base
CLAUDE.md cites for a live-money conversation with J.

**Generalizable pattern (this is now confirmed a CLASS, 4 instances, not a one-off):** any
instrument that computes an actionable verdict from `mean(per_trade_or_per_day_pnl) > threshold`
without also checking whether that mean survives dropping its top-N winning trades/days is
lying about its own confidence — 2-3 outlier events can carry an otherwise-flat or negative
population across the line. This is NOT the same as C4's general "disclose concentration"
guidance (which is about analysis/reporting); this is specifically about **gate/verdict logic**
that other code or humans ACT on (arm/disarm, RED/GREEN, PASS/FAIL).

**Fix:** `backtest/lib/concentration.py` (built 2026-08-23) is now the single shared
implementation (`drop_top_n`, `drop_bottom_n`, `drop_best_days`, `drop_worst_days`,
`top_day_share`) — every instrument in this class calls it, none reimplement the math.
`live_readiness.py::score_round_trips` now downgrades an otherwise-clean 4-condition PASS to
`PASS_CONCENTRATED` when the positive expectancy does not survive dropping the top 3 winning
trades (`CONCENTRATION_DROP_TOP_N`). Downgrade-only: never touches FAIL/UNKNOWN/INSUFFICIENT.
`_book_wide_rollup` counts `arms_pass_concentrated` on its own key rather than silently folding
it into `arms_pass` (folding it back in would erase the exact distinction the verdict exists to
draw). Zero live behavior change today — all 5 real arms currently read UNKNOWN off unattributed
rule-breaks, which short-circuits before the concentration term is even consulted; this is a
forward-looking correction that activates the day rule-break attribution (or the AND-gate) ever
lets an arm reach the PASS branch.

**Guard:** `backtest/tests/test_live_readiness.py` — `test_score_round_trips_concentration_downgrades_pass`,
`test_score_round_trips_concentration_survives_stays_plain_pass`,
`test_score_round_trips_concentration_never_upgrades_a_fail`,
`test_book_wide_rollup_counts_pass_concentrated_separately`. RED-proofed via `git stash`
(3 new tests correctly `KeyError` pre-fix; 23/23 pass post-fix). Curated safety gate 59/59 PASS.

**Still open (per the parent queue item, NOT done this fire):** desk_allocator.py scoring, chop
meter, ladder-rung tally, entry-quality scorers, shadow-tally/summary writers under
`analysis/recommendations/*-shadow-summary.json`, and the general `*_verdict`/`*_check.py`
sweep across `setup/scripts/` + `backtest/autoresearch/` have not been audited for this shape
yet. A doctrine line in BACKTESTING-PLAYBOOK ("a mean without a drop-topN is not a verdict")
is also still unwritten. Recommend a future fire finish the sweep rather than treating this
4th-instance fix as closing the class.
