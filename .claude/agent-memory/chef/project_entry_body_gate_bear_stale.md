---
name: entry-body-gate-bear-stale
description: entry_bar_body_pct_min (gate #13) is a BEAR doji block, ratified on OLD engine, now stale under real fills — Chef recommended UNBLOCK 2026-06-26
metadata:
  type: project
---

`entry_bar_body_pct_min` = `backtest/lib/engine/gates.py` **gate #13**. Fires **ONLY when `side=="P"` (BEAR/puts)** — `if _body_min > 0.0 and side == "P"`. Blocks bear entries whose trigger-bar body_pct < 0.20 (doji/wick). Bull twin = gate #14 `entry_bar_body_pct_min_bull`, separate, default 0.0/OFF. params.json Safe = 0.20 (armed).

**Re-validated 2026-06-26 (J direction-block prune) → recommended UNBLOCK (still_justified=false).** Scorecard `analysis/recommendations/safe_entry_body_gate.json` ratified 2026-06-18 on OLD engine (BS-sim discovery + OTM + −10% bear premium stop): IS +$295, OOS +$566, WF 7.193.

Under CURRENT real-fills engine (full OPRA 2025-01-02..2026-06-18, `run_backtest(use_real_fills=True, entry_bar_body_pct_min=X)`):
- BLOCKED(0.20) 291 tr +$10,329 vs UNBLOCKED(0.0) 331 tr +$8,383 → aggregate +$1,946 LOOKS pro-block.
- **BUT that aggregate is a CASCADE ARTIFACT** (L15): 4 unrelated state-shuffle "added" trades = +$2,146.
- **DIRECT causal effect** (side+date+time+strike identity diff): gate removes **44 BEAR doji entries netting +$200** (15 W +$4,649 / 29 L −$4,448, WR 34.1%) → **direct block delta = −$200** (removes a net-WINNER set).
- Suppresses 5 fat-tail bear winners: +$1,361 / +$881 / +$841 / +$493 / +$320.
- doji=loser mechanism was TRUE on BS-sim/wide-stops, FALSE under managed exits (weak-bodied entry still rides the runner). Textbook C3/L182 stale-BS-sim block.
- Anchor-no-regression PASS: neither arm fires on any of the 6 in-range anchor dates; delta_edge_capture=0.0.

Param diff to unblock: `entry_bar_body_pct_min` 0.20→0.0 (Safe). Candidate: `strategy/candidates/2026-06-26-113700-entry-body-gate-bear-revalidation.md`. Confidence 7/10 (direct delta small/noisy, but wrong sign + fat-tail amputation + stale engine).

**PATTERN (foot-gun for future revals):** the work-item label "bull-direction block" was WRONG — this is BEAR-only. Always read the gate code (`side=="P"` vs `=="C"`) before trusting the work-item direction label. Also: the orchestrator aggregate diff is cascade-confounded (L15); the HONEST causal measure is the side+strike+date+time identity diff of removed trades, NOT the run totals. See [[short-level-rejection-killed]] for the inverse (a block that DID earn its keep).
