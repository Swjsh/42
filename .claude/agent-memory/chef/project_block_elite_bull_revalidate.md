---
name: block-elite-bull-revalidate
description: block_elite_bull (gate #3, Safe) re-validated on CURRENT engine = REVALIDATE_INCONCLUSIVE; unblock earns +$1602 AGG but is a 74%-one-trade fat-tail mirage, no broad per-trade edge
metadata:
  type: project
---

Re-validated `block_elite_bull` (gates.py gate #3: ELITE tier + level_reclaim trigger + bull/C, VIX [0,25) Safe / [15,18) Bold) on the CURRENT engine (real fills via `runner.run_with_params(use_real_fills=True)`, full 18mo 2025-01-02..2026-06-18, option-cache covers it). Verdict = **REVALIDATE_INCONCLUSIVE** — NOT a clean UNBLOCK, NOT a blind KEEP. Do NOT re-cook as a simple unblock.

**Why:** Aggregate real-fills A/B: BLOCK OFF earns **+$1,602** vs ON (raw P&L says unblock). BUT the 38 suppressed gate-target trades are a **fat-tail mirage**: +$3,297 total but **top1 = 74%** (05-13-2026 = +$2,452 — which was the scorecard's OLD-engine OOS *loser* −$29, now sign-flipped to winner under managed exits, confirming the task hypothesis). **ex-top3 per-trade = −$51.9; WR = 21%; flips NEGATIVE ex-top1 in EVERY sub-window** (2025-H1, 2025-09+, 2026). per-trade Sharpe 0.145. Blind UNBLOCK dilutes book per-trade $261→$151 AND forfeits a +$1,695 quality-slot cascade pair → `final_score` (OP-16) FALLS even as raw P&L rises = the "trade more on a tail" anti-pattern (L166/L178/C24). Anchor no-regression PASS (gate touches only BULL; 4/29/5/04/5/07 byte-identical).

**How to apply:** The old VIX[0,25) band evidence (scorecard `safe_block_elite_bull_all_vix.json`, ratified 2026-06-18 on BS-sim/OTM/−8% stops) is STALE/invalid under the current engine — the gate currently does the right *aggregate-quality* thing for the wrong reason. The genuine next step is NOT unblock-all but to find a **loser/tail discriminator** (likely trigger/time signature: morning level_reclaim breakouts = the 3 tails; midday/afternoon = the 30 bleeders) → propose a NARROWED carveout gate that keeps losers out + lets the tail through (a real `final_score` gain). Cap-admission ($2K/qty) likely clips the very tail winners → realized unblock upside < +$1,602 (L180), strengthening KEEP. Script: `backtest/autoresearch/_revalidate_block_elite_bull.py`. Candidate: `strategy/candidates/2026-06-26-092624-block-elite-bull-revalidate.md`. See [[project_direction_block_inventory]].
