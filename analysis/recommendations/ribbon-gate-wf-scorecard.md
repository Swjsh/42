# RIBBON_MOMENTUM_GATE — Ratification Scorecard

> Generated 2026-05-31. All numbers computed in-process from real OPRA fills (L77).
> Gate: `min_ribbon_momentum_cents=5, max_ribbon_duration_bars=20, midday_trendline_gate=True`

## What the gate encodes (human chart reading)
- **Ribbon spreading ≥5¢ over 3 bars**: the EMAs are actively separating — trend accelerating, not topping
- **Ribbon age ≤20 bars**: fresh flip, not a 2-hour stale trend near exhaustion
- **No midday single-trendline**: block weak 1-trigger trendline entries 11:30–14:00 ET

## Walk-Forward Results

| Window | n | WR | per-trade /c | total /c | months+ |
|---|---|---|---|---|---|
| IS BASE 2025-01..09 | 154 | 0.27 | +1.1 | +175 | 4/9 |
| IS GATED 2025-01..09 | 35 | 0.31 | +7.2 | +253 | 5/9 |
| OOS BASE 2025-10..2026-05 | 158 | 0.33 | +6.1 | +956 | 6/8 |
| **OOS GATED** 2025-10..2026-05 | **51** | **0.47** | **+26.9** | **+1373** | **8/8** |

**WF ratio (OOS/IS per-trade): 3.736** → PASS ✓ (gate ≥0.50)

## OP-11 Gate Checklist
| Gate | Required | Actual | Status |
|---|---|---|---|
| WF ratio | ≥ 0.50 | 3.736 | PASS ✓ |
| OOS WR | ≥ 0.40 | 0.47 | PASS ✓ |
| OOS per-trade | > 0 | +26.9 | PASS ✓ |
| Top-5 concentration | < 80% | 56.0% | PASS ✓ |
| Anchor (5/04 721P) | kept | 53.6 | PASS ✓ |
| Anchor window total | > 0 | +33.8 | PASS ✓ |

## Monthly OOS P&L breakdown
| month | /c |
|---|---|
| 2025-10 | +47 |
| 2025-11 | +330 |
| 2025-12 | +199 |
| 2026-01 | +279 |
| 2026-02 | +249 |
| 2026-03 | +28 |
| 2026-04 | +7 |
| 2026-05 | +235 |

## VERDICT: **RATIFICATION_READY**
Signal count IS 35 → OOS 51 (takes 32% of base signals).
Rule 9: params.json + heartbeat.md update requires J ratification on a weekend.
Implementation: `orchestrator.py` kwargs already live (default=off). Params candidate below.

## Params.json candidate (after ratification)
```json
"min_ribbon_momentum_cents": 5.0,
"max_ribbon_duration_bars": 20,
"midday_trendline_gate": true
```