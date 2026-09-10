# Trendline fitter v2 -- TRADE-OUTCOME A/B (2026-09-10)

Prereg: [`analysis/recommendations/prereg-trendline-fitter-v2-swap-10-30-2026-09-09.json`](../recommendations/prereg-trendline-fitter-v2-swap-10-30-2026-09-09.json)
(FROZEN, decision rule NOT modified by this file -- this is the evidence file the prereg's
own `disclosure_OP20` block calls for). Scripts: [`ab_replay_2026_09_10.py`](ab_replay_2026_09_10.py),
raw output [`ab_replay_results_2026_09_10.json`](ab_replay_results_2026_09_10.json),
sweep raw output `param_sweep_results_2026_09_10.json`.

Prior WS-C geometric-reproduction finding (0/24 J-drawn lines): [`RESULTS-2026-09-09.md`](RESULTS-2026-09-09.md).
This file answers a DIFFERENT question -- not "does v2 reproduce J's hand-drawn lines" but
"does v2's fitter gate the trades v1 actually took, and does either fitter's parameters
change the trade-outcome metric" -- per J's 2026-09-10 pushback that the prior work never
touched trading outcomes.

## Headline verdict

**Outcome 1 (of the prereg's 3 expected outcomes): v2 is worse -- specifically, on the
real-fill population, v2 is UNDECIDABLE-by-construction because it never coincides with a
real fill. v1 STAYS. No swap. No new prereg for the parameter sweep either (see below).**

This is NOT a forward-window read against the prereg's own decision rule -- the prereg's
window is the 40 scored sessions ending 2026-10-30, which have not happened yet as of today
(2026-09-10). Everything below is the **in-sample prior** the prereg explicitly carves out
("every session on or before 2026-09-09 is an IN-SAMPLE PRIOR... reported honestly alongside
the decision and never used to gate it"). The forward decision cannot be made today; this
file exists so the machinery is built, tested, and ready to re-run once forward sessions
exist, and so the in-sample signal (strongly negative for v2) is on record.

## What was actually run

1. Loaded every REAL, ALREADY-FILLED entry (`analysis/trades-enriched.jsonl`, `attribution
   == "engine"`, arm in the 4 real-fills arms `{safe-2, bold-2, safe-3, risky-1}`) whose
   `triggers` list includes `trendline_rejection` (the ONLY population `statistical_criterion`
   is allowed to decide anything from, per L50/L71 and the prereg's own population clause).
   **N = 45 entries, 19 distinct trading days, 2026-07-02 through 2026-09-08.** (safe-3 and
   risky-1 contributed 0 of the 45 -- all 45 are safe-2/bold-2; disclosed, not hidden.)
2. For each entry, loaded the SAME single-day 5m bar frame v1's own tests use
   (`autoresearch.runner.load_data` -> filter to date, `reset_index`), located the triggering
   bar by CLOSE-time label (verified against `test_trendline_trigger.py`'s worked 5/1 example:
   bar labeled 13:35, J's entry logged 13:36 -- bars are labeled by their own close time, and
   the entry timestamp lands 1-3 minutes after that label).
3. **v1 sanity check**: re-ran `filters.py::detect_trendline_rejection_bearish` UNCHANGED
   (imported, never edited) on that exact bar/prior_bars. Fired on **16 of 45 (35.6%)**.
   This is a REAL, disclosed limitation of the harness, not of v1's live behaviour -- the
   remaining 29 likely reproduce with the engine's actual continuous (cross-day) bar window
   rather than this harness's single-day-reset-to-04:00 frame, or fired via a DIFFERENT one
   of the several triggers also present in that entry's `triggers` list (an entry can carry
   `trendline_rejection` alongside `confluence`/`level_reclaim`/etc.; this harness cannot
   tell from the ledger which trigger was load-bearing for that specific fill). Only the
   16-row reproduced subset is a harness-VERIFIED like-for-like comparison; the full 45 is
   reported alongside it, not instead of it.
4. **v2 check (the actual A/B)**: for the identical bar, with bars converted 1:1 to `BarV2`
   (same OHLC, same order -- ONLY the fitter differs), called
   `trendline_fit_v2.detect_trendlines_v2(..., kinds=("resistance",), families=("wick","body"),
   query_index=bar_idx-1, require_confirmed=True)` (query strictly BEFORE the entry bar --
   no lookahead, C6), projected each CONFIRMED line to the entry bar
   (`current_value + slope_per_bar * 1`), and applied v1's OWN 3-part rejection test (high
   reaches line within the line's own ATR tolerance, close below, red bar) -- i.e. the fitter
   is swapped, the rejection semantics are held constant, matching the prereg's "only the
   fitter swapped" instruction as closely as a single detector-level harness can.

## Result: v2 fires on 0 of 45 real-fill bars (0 of the 16 harness-verified bars too)

```
{
  "n_entries_total": 45,
  "n_ok_bar_lookup": 45,
  "n_v1_reproduces_real_entry": 16,
  "n_v2_also_fires_same_bar": 0,
  "n_paired_v1_and_v2_both_fire": 0,
  "n_v1_fires_v2_does_not_regression_candidates": 16
}
```
(quoted verbatim from `ab_replay_results_2026_09_10.json`, this session's run)

**v2 is not a dead/never-firing detector** -- a full-day scan (every bar, 5 sample days)
shows v2 DOES fire CONFIRMED resistance rejections elsewhere: 0/143 (07-02), 4/144 (07-17),
3/144 (08-11), 4/144 (08-20), 9/144 (09-01) bars. So the finding is not "v2 never triggers";
it is "v2's geometrically-different, stricter (ATR-tight tolerance, zero-close-through hard
disqualify, CONFIRMED-3-touch) lines pick different bars than v1's looser sequential-
descending-peak lines, and the two sets do not overlap on this sample." This corroborates
WS-C's independent 0/24 J-drawn-line finding from a completely different angle (real fills
vs hand-drawn lines) -- convergent evidence, not a restatement of the same test.

## statistical_criterion() -- REUSED VERBATIM from setup/scripts/go_live_gate.py (L251)

**v1, all 45 real trendline_rejection entries (19 days):**
```
as_traded:      ci_lower_2.5 = 0.257   (pf_point 0.886, total_pnl -$271.00)
ex_best_day:    ci_lower_2.5 = 0.167   (pf_point 0.669, dropped 2026-08-20, total_pnl -$784.00)
cost_adjusted:  ci_lower_2.5 = 0.254   (pf_point 0.878, total_pnl -$290.67)
pass: false (criterion requires ALL THREE > 1.0)
```

**v2: n = 0 real-fill entries.** `statistical_criterion([], None)` returns, verbatim:
```
{"insufficient_data": true, "pass": false, "note": "zero engine-attributed round trips for this scope"}
```
**v2 cannot be scored on option P&L at all in this population** -- it never gates a bar
where a real fill exists, so there is no real premium P&L to attach to it. Per the prereg's
own confound disclosure ("if option P&L is unavailable for a variant's counterfactual entries,
say so explicitly -- that is a real limitation, not something to paper over"): this session
did NOT sim/BS-price v2's counterfactual bars (the 20 confirmed-firing bars from the 5-day
scan above) to manufacture a P&L number for v2, because the prereg is explicit that sim/BS
rows are ranking-only and may never decide this comparison, and fabricating a "v2 P&L" from
option-pricing-at-a-different-bar would not be ranking-only either -- it would be presenting
a number shaped exactly like the real one it cannot actually produce. The honest number here
is **n=0, undecidable.**

## Decision-rule check (prereg's own 5 ACT clauses, all must pass to swap)

| Clause | Requirement | Result |
|---|---|---|
| (a) n >= n_min (15 entries, 20 days) BOTH variants | v1: 45 entries/19 days (fails 20-day bar too). v2: 0 entries/0 days | **FAIL -- v2 has zero N** |
| (b) v2 ex-best-day PF CI-lower >= v1's | v2 has no CI (undefined on 0 entries) | **FAIL -- undefined** |
| (c) OP-16 anchor no-regression | v2 misses ALL 16 harness-verified real anchor bars (0 preserved) | **FAIL** |
| (d) advantage not concentrated in 1 day/arm | N/A, no advantage exists | **FAIL (moot)** |
| (e) WS-C reproduction ledger >=80% | WS-C measured 0/24 (2026-09-09) | **FAIL** |

**KILL_v1_stays fires on every one of the 5 clauses independently.** This is about as
unambiguous a KILL as the prereg's own rubric can produce. `/fable-too-good` was not run --
the result is not extraordinary in v2's favor, it is uniformly negative, so the suspicion
protocol (reserved for results that look too good) does not apply here.

## Secondary finding: v1 parameter sensitivity sweep (lookback_bars / min_swings / proximity_pct)

**Separate question, separate N, NOT conflated with the fitter-swap verdict above.** Method:
for each parameter value (one knob varied at a time, other two held at production defaults
`lookback_bars=60, min_swings=3, proximity_pct=0.0010`), re-ran v1's UNCHANGED formula on the
same 45 real-fill bars and kept only the subset it would still recognize, then scored that
subset with the same `statistical_criterion()`. This can only ever SUBSET the 45 real bars
(a param cannot manufacture new real fills) -- it cannot test whether a looser/tighter param
would have caught MORE real winners than the 45 actually taken; that would need a full
counterfactual replay with sim pricing, which is out of scope for "cheapest possible win"
sanity-checking and is explicitly not attempted here.

```
lookback_bars=40  n=15 (9d)  as_traded_ci_lower=0.030  ex_best_day_ci_lower=0.005  pnl=-$1069
lookback_bars=50  n=14 (9d)  as_traded_ci_lower=0.148  ex_best_day_ci_lower=0.038  pnl=+$49
lookback_bars=60  n=16 (9d)  as_traded_ci_lower=0.159  ex_best_day_ci_lower=0.031  pnl=+$104  <- PRODUCTION
lookback_bars=70  n=11 (7d)  as_traded_ci_lower=0.000  ex_best_day_ci_lower=0.000  pnl=-$1007
lookback_bars=80  n=10 (7d)  as_traded_ci_lower=0.000  ex_best_day_ci_lower=0.000  pnl=-$700

min_swings=2      n=3  (2d)  as_traded_ci_lower=0.000  ex_best_day_ci_lower=None(n<2 days)  pnl=-$4
min_swings=3      n=16 (9d)  as_traded_ci_lower=0.159  ex_best_day_ci_lower=0.031  pnl=+$104  <- PRODUCTION
min_swings=4      n=9  (7d)  as_traded_ci_lower=0.058  ex_best_day_ci_lower=0.000  pnl=+$160

proximity_pct=0.0005  n=12 (8d)   as_traded_ci_lower=0.031  ex_best_day_ci_lower=0.000  pnl=+$10
proximity_pct=0.0010  n=16 (9d)   as_traded_ci_lower=0.159  ex_best_day_ci_lower=0.031  pnl=+$104  <- PRODUCTION
proximity_pct=0.0015  n=18 (11d)  as_traded_ci_lower=0.169  ex_best_day_ci_lower=0.085  pnl=-$60
proximity_pct=0.0020  n=18 (11d)  as_traded_ci_lower=0.169  ex_best_day_ci_lower=0.085  pnl=-$60
proximity_pct=0.0030  n=20 (11d)  as_traded_ci_lower=0.160  ex_best_day_ci_lower=0.084  pnl=-$268
```
(quoted from `param_sweep_results_2026_09_10.json`, this session's run)

**No knob clears anything close to a decision bar.** Every single variant, at every value
tested, has ex-best-day PF CI-lower under 0.1 (vs the >1.0 bar) on N well below the
prereg's own 15-entries/20-days minimum (max N reached is 20 entries/11 days, at
proximity_pct=0.003, and that variant's total P&L is MORE negative than production, not
better). The proximity_pct=0.0015-0.002 cells show a marginally higher as_traded CI-lower
(0.169 vs 0.159) but a WORSE total P&L (-$60 vs +$104) and a smaller reproduced-day count
below the 20-day bar -- textbook small-N noise, not a signal. **No parameter change is
recommended; no new prereg is warranted from this sweep.**

## OP-20 disclosure

- **N**: v1 = 45 entries / 19 days (16/45 harness-verified reproduced). v2 = 0 entries / 0
  days (real-fill population). Parameter sweep: 3-20 entries / 2-11 days per cell, all below
  the prereg's n_min.
- **IS vs OOS**: 100% in-sample prior (2026-07-02 to 2026-09-08, all <= 2026-09-09). Zero
  forward-window (2026-09-10 to 2026-10-30) data exists yet -- the window hasn't started.
- **Null/baseline**: v1 as-is, same sessions, same bars, ONLY the fitter changed for v2's
  side. This IS the paired comparison the prereg calls for; it is undecidable in v2's favor
  purely because v2 structurally never lands on a bar with a real fill.
- **Known confounds**: (1) harness bar-framing reproduces only 16/45 of v1's own real
  entries -- a data-alignment limitation of THIS script, disclosed above, not a claim about
  live v1 behaviour. (2) v2 was given the SAME single-day bar frame as v1 (no cross-midnight
  premarket carry-forward from a prior day), which may understate v2's canon-rule-5
  premarket-anchor advantage relative to its intended design. (3) Option P&L (not SPY-price
  P&L) was used throughout via the real `pnl_dollars` field -- per L74/C3 -- but v2 has zero
  entries to price, option or otherwise. (4) The parameter sweep can only subset the existing
  45 real fills, never add new ones, so it structurally cannot detect a param value that
  would have caught additional real winners.

## What this session did NOT do

- Did not edit `backtest/lib/filters.py`, `setup/scripts/heartbeat_core.py`, any `params*.json`,
  or the frozen prereg's `decision_rule`/`classification`/`ACT_swap_v2_into_filters` fields.
- Did not use `GAMMA_FREEZE_OVERRIDE`.
- Did not tune v2's parameters after seeing the 0/45 result.
- Did not fabricate sim/BS P&L for v2's counterfactual firings to manufacture a comparable
  number -- reported the real limitation (n=0, undecidable) instead.
- Did not commit anything (per task instruction).
- Placed no orders, touched no scheduled task, changed no live state.
