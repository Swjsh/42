# DRAFT: Star-Rating vs Respect Study (B4)

**Status:** DRAFT — data-driven finding, no live action
**Date:** 2026-06-15
**Verdict:** DOES_NOT_SEPARATE (spread=3.4pp < 5pp threshold)
**Gate status:** Instrumentation/observability — no live-order impact

## Finding

The star formula (score_level) does NOT reliably predict forward respect rate.
Higher stars correlate with LOWER respect rate (counter-intuitive):

| Star tier | N levels | Touch rate | Respect rate (of touched) |
|---|---|---|---|
| 1-star (★) | 114 | 34.2% | **28.2%** (highest) |
| 2-star (★★) | 683 | 26.1% | 27.0% |
| 3-star (★★★) | 2386 | 61.4% | **24.8%** (lowest) |

Max spread: **3.4pp** (below 5pp significance threshold → does not separate).

## Root Cause

The formula gives weight to **touch_count** (log2 curve, max 2 pts), which boosts
stars for levels that have been approached many times in history. But:

- High touch count = price approaches this level often
- Being approached often correlates with *being traversed* (broken), not *being bounced*
- 3-star levels have the highest touch rate (61.4%) precisely because they sit at prices
  that are revisited, which also means more breaking events

The `recency` and `confluence` components add points for levels that are "busy"
but don't predict the directional quality of the bounce when the level is finally reached.

## Proposal: Formula Reweight (DRAFT)

Instead of fixing the bug that premarket doesn't call score_level() (that would just
propagate stale/incorrect signals), the formula itself should be reweighted to predict
BOUNCE quality, not visit frequency:

1. **Add false_break penalty**: levels that have broken multiple times should lose stars,
   not gain them from high touch count. Use `broken_count / touch_count` ratio.
2. **De-emphasize raw touch_count**: cap at log2(3+1) ~ 1 pt max, reducing the pull
   toward "busy = strong"
3. **Add hold_count bonus**: from count_touches, `held_count / touch_count` = the
   historical hold rate. Levels that held >= 60% of historical touches score higher.
4. **Confluence still valid**: multi-source agreement is structural, not touch-frequency.

**Note:** This proposal would require live-behavior testing before ratification (Rule 9).
The premarket.md edit would expose these reweighted stars to trigger decisions.
Must clear A/B scorecard showing OP-16 anchor-day no-regression before applying.

## AC-2.1 Verdict

- Stars do NOT correlate with respect (DOES_NOT_SEPARATE) → formula reweight needed
- Fix is NOT "just call score_level() in premarket" — that would propagate a formula
  that inversely correlates with the desired outcome
- DRAFT proposal: add hold_rate bonus + false_break penalty to score_level()

## OP-20 Disclosure

- N: 219 days, 3183 levels (full benchmark window)
- No IS/OOS split (formula audit, not forward prediction)
- Metric: respect_rate_of_touched ($0.30 reaction in 6 bars)
- SPY price-space only — real-fills required for option P&L (L74)
- Stars computed with: touch_count from prior 30d window, recency, confluence,
  no MTF (5m only), no EMA alignment (no ribbon data in backtest)
