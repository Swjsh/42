---
name: f8-bull-vix-gate-kept
description: F8 bull-VIX gate (filter 8, VIX<17.20 OR falling) re-validated KEEP under current real-fills+managed-exit engine; do not re-cook as unblock
metadata:
  type: project
---

F8 bull-VIX block (`VIX_BULL_LOW_THRESHOLD=17.20`, filters.py:804/885 — bull entry needs `VIX<17.20 OR vix_falling`) re-validated **KEEP** 2026-06-26 under the CURRENT engine (real OPRA fills + managed exits).

**Result:** unblocking (drop F8 on bull path) admits exactly **3 bull trades across full history (2025-01-02..2026-06-18)** that are net **LOSERS**: full −$892 (bull$ +3,650→+2,759), OOS −$310, train −$582; bull WR 33.3%→25.0%. All 3 biting quarters negative (2025Q1/Q3, 2026Q2), 0 positive — sign-stable. Anchor-no-regression PASS (all J anchors are PUTs, edge_capture delta $0). The "new ITM+managed exits turn the formerly-losing OTM bull config into winners" hypothesis is FALSIFIED for F8.

**Why F8 barely bites:** upstream bull gates (ribbon-BULL-stack, buyer-pressure, `bull_min_triggers>=2`) already exclude most VIX-elevated bull bars, so F8 only suppresses 3 trades over 18mo. KEEP earns its keep on the margin, not by volume.

**Don't re-cook** as an unblock. Tool: `backtest/autoresearch/f8_bull_vix_unblock_ab.py` (monkey-patches `evaluate_bullish_setup` to drop blocker 8, `use_real_fills=True`, `GAMMA_ENGINE_SCORE_ASSERT=0`). Scorecard: `analysis/recommendations/f8-bull-vix-unblock-ab-2026-06-26.json`. Candidate: `strategy/candidates/2026-06-26-094255-f8-bull-vix-block-revalidation-KEEP.md`.

**FOOT-GUN found (load-bearing for any block re-validation):** the TradeFill P&L field is **`dollar_pnl`** (lib/simulator.py:111), NOT `pnl_dollars`. `j_edge_tracker.py:70` reads `getattr(t,"pnl_dollars",0)` → its per-trade DISPLAY silently shows $0 (day totals still correct via `m.total_pnl`). The exit field is `runner_exit_premium`, not `exit_premium`. First A/B run read all bull P&L as $0 (false INCONCLUSIVE) until corrected to `dollar_pnl`. Always read `dollar_pnl` for per-trade P&L. Relates to [[direction-block-inventory]].
