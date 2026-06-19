# DRAFT: VIX-Character Regime x Level Confidence (L73)

**Status:** DRAFT
**Date:** 2026-06-15
**Verdict:** SEPARATES -- regime-confidence multiplier proposed
**Auto-ship gate:** FAIL (requires J ratification + A/B scorecard)

## Summary

Do levels respect at materially different rates in VIX-trending vs VIX-spike regimes?

Max regime spread: **9.7pp** (threshold: >3pp for significance).

VIX character: `trending` = today's VIX > 5-day rolling average (per L73, uniquely optimal window).

## Results

| Regime | N levels | Touch rate | Respect rate | DM-null lift |
|---|---|---|---|---|
| high_spike | 37 | 48.6% | 27.8% | +2.1pp |
| high_trending | 228 | 52.2% | 24.4% | -1.3pp |
| low_spike | 195 | 49.2% | 31.2% | +5.6pp |
| low_trending | 75 | 44.0% | 30.3% | +4.6pp |
| mid_spike | 1419 | 50.9% | 27.5% | +1.8pp |
| mid_trending | 1229 | 56.3% | 21.5% | -4.1pp |

## IS/OOS Validation (50/50 split)

| Regime | IS lift | OOS lift | WF ratio |
|---|---|---|---|
| high_spike | n/a | +2.1pp | n/a |
| high_trending | -17.3pp | +0.5pp | -0.029 |
| low_spike | +3.5pp | +31.5pp | 9.000 |
| low_trending | +4.6pp | n/a | n/a |
| mid_spike | +4.6pp | +0.1pp | 0.022 |
| mid_trending | -7.2pp | -1.3pp | 0.181 |

## Key Findings

Best regime:  **low_spike** (lift = +5.6pp)
Worst regime: **mid_trending** (lift = -4.1pp)

**SEPARATES**: Regime spread exceeds 3pp. VIX character provides actionable level confidence signal.

## Recommendation

Propose regime-confidence multiplier: levels in trending-high-VIX days get lower confidence weights (reduced size); levels in spike-revert-high-VIX days get higher confidence. Implement as `level_confidence_multiplier` in params.json after A/B scorecard + anchor-no-regression.

## OP-20 Disclosure

- N: 219 days, IS/OOS split 50/50 (~110/110)
- Metric: respect-rate-of-touched vs DM-null (0.2568)
- VIX character: trending = VIX_today > VIX_5d_avg (per L73 5-day window)
- SPY price-space only (L74)
- WF ratio = OOS_lift / IS_lift (L73 guard: must be > 0.5 for OOS validity)
