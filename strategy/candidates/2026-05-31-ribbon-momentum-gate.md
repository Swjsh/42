# RIBBON_MOMENTUM_GATE — RATIFICATION_READY

**Filed:** 2026-05-31 (evening grind session)
**Type:** Entry filter — three visual conditions J evaluates before entering
**Status:** RATIFICATION_READY (Rule 9 — J ratification weekend required)
**Source:** backtest/tools/ribbon_signal.py + full_walkforward.py (real OPRA fills)

## What this gate is

When J reads a chart before entering, he checks three things in ~2 seconds:
1. **Are the EMAs spreading apart?** (ribbon widening = trend accelerating)
2. **Is this a fresh flip or a 2-hour stale trend?** (fresh = edge, stale = near exhaustion)
3. **Is this a weak midday trendline setup?** (if so, skip unless conviction)

These three checks are now encoded as engine parameters:
-  — spread must have widened ≥5¢ in last 3 bars
-  — ribbon must be ≤20 bars old in current direction
-  — block single-trigger trendline entries in 11:30-14:00 ET

## Walk-Forward Results (PASS — 16-month full IS/OOS split, real OPRA fills)

| Window | n | WR | per-trade /c | WF ratio |
|---|---|---|---|---|
| IS (2025-01..09) | 35 | 0.31 | +7.2 | — |
| **OOS (2025-10..2026-05)** | **51** | **0.47** | **+26.9** | **3.736** |

WF ratio **3.736** >> 0.50 threshold. OOS outperforms IS — genuine generalization.

## OP-11 Gate Checklist
- WF ratio >= 0.50: **PASS (3.736)**
- OOS WR >= 0.40: **PASS (0.47)**
- OOS per-trade > 0: **PASS (+26.9/c)**
- Top-5 concentration < 80%: **PASS (56.0%)**
- Anchor 5/04 721P: **PASS (+53.6)**
- Anchor window total: **PASS (+33.8/c)**

## What the full OOS picture looks like

Gate takes **51 of 86 total signals** (selective).
8 of 8 OOS months profitable.
Max drawdown (per-contract): -98.6/c — acceptable.

## Params.json change (when ratified)


## Implementation (already live in orchestrator.py, default=off)
All three gates are implemented as kwargs in .
No production change until J ratifies + gamma-sync updates heartbeat.md + params.json simultaneously.

## OP-20 Disclosures
- Real OPRA fills; /usr/bin/bash.02 slippage. Expect +/-5-10% vs live.
- All three gates are binary (on/off). Threshold sensitivity sweep queued as cook.
- Historical window 2025-01 to 2026-05; OOS = Oct 2025 onward (8 months).
- Anchor 4/29: not captured (pre-existing VIX filter block, not this gate).
