# DRAFT: Wick-Rejection vs Close-Based Filter Study (C2)

**Status:** DRAFT
**Date:** 2026-06-15
**Verdict:** wick_valuable=False
**Auto-ship gate:** FAIL — edge gap too large

## Finding

Wick-only rejections show 91.6% respect vs 97.5% close-based (gap=-6.0pp, above 5pp tolerance). Significant edge gap. Wick-rejection entries are materially weaker than close-confirmed ones. STAY with close-based filter 10.

## Data

| Filter type | N events | Respect rate | Median reaction |
|---|---|---|---|
| Close-based (production) | 939 | 97.5% | $1.375 |
| Wick-only (wick miss) | 723 | 91.6% | $0.889 |
| Gap | | -6.0pp | |

## J's 4/29 Archetype

The 4/29 10:25 SPY 710P entry was a bearish ribbon-rejection setup where J visually
read the wick penetration of a resistance level as the trigger (bar high > L, close < L).
The close-based detector in production filter 10 WOULD catch this specific case
(bar.high > L AND bar.close < L = close-based rejection). The "wick-only" case here
is specifically when close REMAINS above (resistance not confirmed by close) — which
J would not take based on his own rules.

The real gap L75 identified was the FALSE BREAK case (bear trap), not wick-rejection.

## Recommendation

Keep close-based filter. Wick-only entries show materially weaker respect. The production filter is correct. Do not add wick-only as a trigger.

## OP-20 Disclosure

- N: 219 days, 939 close-based + 723 wick-only events
- No IS/OOS split (filter characterization)
- Metric: forward respect ($0.30 reaction in 6 bars)
- SPY price-space only (L74)
