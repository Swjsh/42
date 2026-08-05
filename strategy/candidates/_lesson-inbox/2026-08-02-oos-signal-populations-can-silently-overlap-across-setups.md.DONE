# Lesson candidate: two "independent" setups' OOS-validation populations can be a near-total same-day/same-side overlap -- quantify pooled distinct trials, not raw n, before trusting a combined trial count

**Filed:** 2026-08-02 (conductor, WEEKEND) -- closes the "STILL NOT DONE" historical-OOS half of
the ZERO-FOR-TWELVE-POSTMORTEM thread (`automation/overnight/queue.md`, live-sample half closed
2026-07-25 21:12-21:50 ET).

**Symptom:** `vwap_continuation` (armed at claimed OOS n=42, +$66.83/tr) and `vix_regime_dayside`
(armed at claimed OOS n=21, +$79.49/tr) went live and combined for a 0-for-12 stretch, initially
read as "p<1% against the claimed ~55-64% WR -- a validation-pipeline falsification." A same-day
CSV cluster pass (closed 07-25) already showed the LIVE sample was really only 4 distinct
day+side buckets, not 12 independent trials. This fire quantified the OOS-VALIDATION side of the
same question and found the SAME mechanism one layer up: re-running each setup's own detector
(byte-identical, no re-derivation) over the 2026 OOS window (through 2026-07-22) found
`vix_regime_dayside`'s 34 OOS signals are 94.1% (32/34) the SAME (date,side) as
`vwap_continuation`'s 61 OOS signals -- exactly matching a caveat
(`analysis/recommendations/vix_regime_dayside.json#L174`: "100% same-side subset of
vwap_continuation") that was **already written down at arm-time but never quantified**, so the
two setups' n=42+n=21=63 "combined evidence" was never 63 independent trials either.

**Root cause:** `vix_regime_dayside` is a VIX-favorable RE-CUT of `vwap_continuation`'s own
day-trend classifier (both derive `side` from the identical `session_vwap_asof`-based first-3-bar
trend read) -- it filters vwap_continuation's population down to VIX-favorable days rather than
sourcing an independent signal. Treating it as a second, additive edge (rather than an overlay
refinement of the first) double-counts every overlapping day toward "n trades validated" and
toward "how surprising is a losing streak."

**Generalizable rule:** before combining two setups' trade/signal counts into a single
independence claim (an OOS n, a live 0-for-N, a pooled expectancy), check whether either setup's
own doc/scorecard already discloses a same-classifier/subset relationship to the other (grep for
"NOT INDEPENDENT" / "subset of" in `analysis/recommendations/*.json`), and if a caveat like that
exists, POOL by (date,side) before quoting a combined n -- raw row-sum overstates independent
trials by exactly the overlap fraction.

**Candidate graduation:** a reusable helper (`pooled_distinct_trials(setups: list[{date,side}]) ->
{naive_sum, pooled_n, overlap_fraction}`) belongs next to `backtest/autoresearch/probe_stats.py`
(same canonical-stats-helper pattern as the day-concentration/slippage-sweep additions) so any
future "setup A + setup B combined n" claim runs through one audited function instead of an
ad-hoc sum. Not built this fire (scope: the queue item asked for the finding, not a new
canonical helper) -- flagged here so `skill-author`/`lesson-author` can decide graduation.

**Evidence:** `backtest/tools/zero_for_twelve_oos_day_cluster_2026_08_02.py` (detection-only, $0,
1.8s runtime) + `analysis/recommendations/zero-for-twelve-oos-day-cluster-2026-08-02.json` +
guard `backtest/tests/test_zero_for_twelve_oos_day_cluster.py` (3/3 green, golden-file pinned).
Zero trading-path touched (`git diff` scope: `backtest/tools/`, `backtest/tests/`,
`analysis/recommendations/`, `strategy/candidates/_lesson-inbox/`, `automation/overnight/`).
