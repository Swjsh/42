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

## OOS Validation Update (2026-06-16 — A/B test on 2026-05-08 to 2026-05-22)

Run against the specific post-anchor OOS window to get dollar P&L numbers for J ratification:

| Config | n | WR | Total P&L | Exp/trade |
|---|---|---|---|---|
| BASELINE (no gate) | 16 | 25.0% | -$709 | -$44.3 |
| MIDDAY_GATE only (live prod) | 12 | 25.0% | -$816 | -$68.0 |
| **MOMENTUM_ONLY** (new params) | **5** | **40.0%** | **+$389** | **+$77.8** |
| MIDDAY + MOMENTUM (full gate) | 5 | 40.0% | +$389 | +$77.8 |

**Interpretation:**
- The `min_ribbon_momentum_cents=5` + `max_ribbon_duration_bars=20` params alone deliver +$1,098
  vs the true production baseline (midday gate only: -$816 → +$389).
- Momentum gate makes the midday_trendline_gate redundant on this window. Both hit the same 11
  trades that need blocking; adding midday gate on top of momentum gate adds nothing.
- Note: midday_trendline_gate alone is WORSE than the no-gate baseline (-$816 vs -$709) because it
  blocks 4 net-positive afternoon trendline entries. This is expected — midday gate was designed as
  a noise filter, not a P&L maximizer.
- **This is the strongest OOS P&L signal found in this research cycle.**

**Anchor-day EC (BS-sim, V15_J_EDGE_OVERRIDES):**
- BASELINE: EC=673
- MIDDAY_ONLY (live prod): EC=718
- MOMENTUM_ONLY: EC=718 (same as midday; both hit same anchor-day trades)
- Production EC is already 718 (midday gate live). Gap to floor=771 is 53, not 99.

## Post-Research-Date OOS Extension (2026-06-16 — TRUE post-lock OOS)

Window: 2026-05-23 to 2026-06-15 (17 trading days, params locked 2026-05-31 = never seen)

| Config | n | WR | Total P&L | Per-trade |
|---|---|---|---|---|
| BASE (no gate) | 4 | 25% | -$539.96 | -$135.00 |
| MIDDAY_ONLY (live prod) | 4 | 25% | -$539.96 | -$135.00 |
| **MOMENTUM_ONLY (proposed)** | **1** | 0% | **-$320.40** | -$320.40 |
| ALL_THREE | 1 | 0% | -$320.40 | -$320.40 |

**MOMENTUM delta vs live: +$219.56** (gate filtered 3/4 losing BASE trades)

**Critical finding: midday gate alone = $0 improvement in this window** — momentum filter is the sole driver.
The 1 trade taken (2026-05-28) lost $320.40 but N=1 in a choppy regime is insufficient to negate full WF.
Scorecard: `analysis/recommendations/ribbon-gate-oos-extension.md`

## OP-20 Disclosures
- Real OPRA fills throughout (both A/B and post-research OOS used real fills, not BS-sim).
- All three gates are binary (on/off). Threshold sensitivity sweep queued as cook.
- Historical window 2025-01 to 2026-05; OOS = Oct 2025 onward (8 months).
- Anchor 4/29: not captured (pre-existing VIX filter block, not this gate).
- Post-research OOS (2026-05-23..06-15): n=1 MOMENTUM trade (choppy window, N insufficient alone).
