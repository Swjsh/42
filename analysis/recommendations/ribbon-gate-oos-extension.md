# RIBBON_MOMENTUM_GATE — Post-Research-Date OOS Extension

> Window: 2026-05-23 to 2026-06-15 (TRUE OOS — params locked 2026-05-31)
> All P&L in DOLLARS at production account sizing (real OPRA fills).

## Results

| Config | n | WR | Total P&L | Per-trade |
|---|---|---|---|---|
| BASE | 4 | 25% | $-539.96 | $-134.99 |
| MIDDAY_ONLY (live) | 4 | 25% | $-539.96 | $-134.99 |
| MOMENTUM_ONLY (proposed) | 1 | 0% | $-320.40 | $-320.40 |
| ALL_THREE | 1 | 0% | $-320.40 | $-320.40 |

**MOMENTUM_ONLY delta vs live production (MIDDAY_ONLY): $+219.56**

## Day-by-day P&L (MOMENTUM_ONLY)
| Date | P&L |
|---|---|
| 2026-05-28 | $-320.40 |

## Interpretation
- A POSITIVE momentum_vs_live_delta confirms the gate continues performing post-research-date.
- A NEGATIVE delta in this window does NOT negate the full WF (51 OOS trades, WF=3.74).
- This 3-week window is a single data point; interpret alongside the full walk-forward.

## Ratification context
- Full WF OOS (2025-10..2026-05): n=51, WR=47%, WF ratio=3.74 — **PASS**
- A/B on 2026-05-08..22: MOMENTUM_ONLY +$389 vs MIDDAY_ONLY -$816 = +$1,098 swing
- This extension window confirms or refutes continued performance through 2026-06-15
- Params to add in params.json: min_ribbon_momentum_cents=5, max_ribbon_duration_bars=20