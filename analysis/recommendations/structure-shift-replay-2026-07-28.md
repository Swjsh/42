# Structure-shift confirmation replay -- THE PHILOSOPHY BUILD (2026-07-28)

Generated 2026-07-28T10:12:40.747242. Runner: `backtest/tools/structure_shift_replay.py`. Pre-reg: `analysis/recommendations/prereg-structure-shift-confirmation-2026-07-28.json (commit 773a17f0)`. Runtime: 101.7s total (68.6s entry/scoring layer).

## VERDICT: 1/5 gates pass -- ALL_PASS=False

| Gate | Pass |
|---|---|
| G1 positive aggregate delta (K=3 vs baseline level-tied) | False |
| G2 day-majority of changed days positive | False |
| G3 survives dropping single best changed trade | False |
| G4 anchor-no-regression (35 RUNNER_TRAIL, +$15,774) | False |
| G5 both incident anchors captured (bear 07-27 + bull 07-28) | True |

## Book totals

| Book | N trades | Total P&L | N expired unconfirmed | N excluded synthetic |
|---|---|---|---|---|
| **BASELINE (level-tied subset, this window)** | 68 | +$7039.25 | -- | -- |
| **K=3 (primary)** | 1668 | +$931.40 | 1265 | 844 |
| **K=2 (sensitivity)** | 1670 | -$409.20 | 1601 | 769 |

## G4 detail -- 35 RUNNER_TRAIL anchor (stored total +$15774.05)

n_in_scope=21/35 (rest pass-by-scope, trendline-only). n_degraded=18. **G4 pass = False**.

## G5 detail -- incident anchors

**Bear 2026-07-27 09:40 @744.9:** found_bar=True, candidate_found=True
  - K=3: confirmed=True, confirmation_time=2026-07-27T09:45:00, confirmation_close=743.8
  - K=2: confirmed=True, confirmation_time=2026-07-27T09:45:00, confirmation_close=743.8

**Bull 2026-07-28 11:05 @~738.1:** found_bar=True (ENTRY-SIGNAL-LEVEL VERIFICATION ONLY -- no OPRA cache for 2026-07-28, so no option premium/P&L computed. Trigger+level (level_reclaim+ribbon_flip+confluence @738.1, blocked) cited from markdown/doctrine/J-MARKET-PHILOSOPHY.md, not re-derived via a second orchestrator run. feed_used=iex (SIP attempted first per this codebase's established convention; fell back to free IEX on a 403 -- confirmed live this session to be a same-day real-time-SIP entitlement gap, not a recency block, since the fetch ran at 12:06 ET, ~1hr after the anchor bar). Checks ONLY whether the frozen structure-shift predicate's price-action condition confirms, against freshly-fetched real 5-min bars.)
  - K=3: confirmed=True, confirmation_time=2026-07-28T11:10:00, confirmation_close_spy=739.41
  - K=2: confirmed=True, confirmation_time=2026-07-28T11:10:00, confirmation_close_spy=739.41

## Also-entered cohort (engine's lagging gates already passed): n=72

- entered: 24
- expired_unconfirmed: 8
- skipped_not_flat: 37
- excluded_synthetic: 3

---
_Raw JSON with full per-trade/per-candidate detail: `analysis/recommendations/structure-shift-replay-2026-07-28.json`._
