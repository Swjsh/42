# DTE Live-Edge Risk Characterization — vwap_continuation ITM-2 / -8%

**Run:** 2026-06-21 | **Window:** 2025-01-02..2026-06-16 | **Family:** vwap_continuation (the LIVE edge) | **Cell:** ITM-2 strike, -8% premium stop (production tier)

## VERDICT: **SHARPE_TRADEOFF_J_CALL**

> 1DTE adds dollars but the variance is genuinely two-sided (the downside leg widened materially too) — a real risk-up tradeoff. Per L175 this is J's product call, not an auto-ship.

## The decomposition (REAL numbers, 0DTE vs 1DTE)

| Metric | 0DTE | 1DTE |
|---|---|---|
| n trades | 157 | 166 |
| win rate % | 45.9 | 42.8 |
| per-trade exp ($) | 51.27 | 67.25 |
| total ($) | 8050.02 | 11162.88 |
| **OOS total ($)** — ship-bar primary | 1817.16 | 3010.26 |
| OOS per-trade exp ($) | 36.34 | 59.02 |
| std ($) | 143.48 | 211.16 |
| Sharpe-style exp/std | 0.3574 | 0.3185 |
| downside deviation ($) | 56.87 | 85.77 |
| **Sortino (exp/downside-dev)** | 0.9016 | 0.784 |
| max drawdown ($, sim qty=3) | -939.12 | -1943.76 |
| worst day ($) | -223.68 (2025-04-07) | -313.68 (2025-04-07) |
| worst day @ LIVE qty=5 ($) | -372.8 | -522.8 |
| held overnight % | 0.0 | 0.0 |

## Upside vs downside variance split (where did the std go?)

| Leg | 0DTE n | 0DTE mean | 0DTE std | 1DTE n | 1DTE mean | 1DTE std |
|---|---|---|---|---|---|---|
| Winners | 72 | 197.41 | 66.15 | 71 | 298.28 | 90.21 |
| Losers | 85 | -72.51 | 26.9 | 95 | -105.42 | 41.96 |

- Winner-leg std widening 0DTE->1DTE (absolute $): **+24.06**
- Loser-leg std widening 0DTE->1DTE (absolute $): **+15.06**
- In ABSOLUTE $ the winner leg widened more (+24.06 vs +15.06); in RELATIVE terms the LOSER leg widened more (+56% vs +36%). The mean LOSS also grew -72.51 -> -105.42 (+45%) — the -8% stop caps the PERCENT but the bigger 1DTE entry premium means a bigger DOLLAR loss per stop-out. So the std inflation is **two-sided**, not pure upside: that is exactly why Sortino dips and maxDD ~doubles despite the +OOS-dollars.

## Kill-switch projection (live sizing)

- Worst single day at 1DTE, scaled to LIVE qty=5 (sim ran qty=3): **$-522.8**
- Safe-2 kill switch: **$-600.0/day** (-30% of $2K)
- Inside the Safe kill switch: **True**

## CLEAN-win bar checklist

- [x] More OOS dollars at 1DTE ($1817.16 -> $3010.26)
- [ ] Sortino holds/improves (0.9016 -> 0.784)
- [ ] maxDD not materially worse (ratio 2.07, tolerance 1.25x)
- [x] Projected worst-day inside Safe kill switch

## Method note

Reuses `_dte_expansion_sim.py` byte-for-byte: same vwap_continuation detector, same OPRA fill conventions, same overnight-gap + expiry-intrinsic settlement. Only the LIVE cell (ITM-2 / -8%) is run, at 0DTE and 1DTE, and the per-trade DteFill distribution it returns is decomposed. No production module (detector/params/risk_gate/orchestrator/heartbeat) was touched. Sortino uses downside deviation around a 0 MAR (absolute-dollar convention). maxDD is the peak-to-trough of the chronologically-ordered cumulative P&L at sim qty=3; worst-day is scaled to the live qty=5 tier for the kill-switch check.
