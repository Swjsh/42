---
name: direction-block-inventory
description: Full inventory of every direction-block + setup-scope restriction in the Gamma engine (J-directed 2026-06-26 target = trade validated set both directions, validation is the only scope)
metadata:
  type: project
---

J-DIRECTED TARGET STATE (2026-06-26): per account the engine trades EXACTLY the validated setup set, BOTH directions. Direction is NOT a scope; validation status is the only scope. Every direction-block must justify itself under the CURRENT engine (real-fills + ITM + managed-exit) or be removed.

**Why:** Old engine = OTM strikes + BS-sim + premium-stops (-8%/-10%). Current engine = real OPRA fills + ITM/ATM + chart-stop-primary (-50% catastrophe caps + chandelier). MOST bull-blocks were ratified on the OLD engine, so their evidence is stale.

**How to apply:** When asked to prune/re-validate blocks, re-validate with `backtest/lib/simulator_real.py` (`simulate_trade_real`) — the ONLY WR authority (C1). `backtest/run.py --real-fills` and the `mass_grind*` funnels drive it.

## The two routing structures
1. **Ribbon engine** (orchestrator.py run_backtest): bear=BEARISH_REJECTION_RIDE_THE_RIBBON, bull=BULLISH_RECLAIM_RIDE_THE_RIBBON. 15-gate battery in `backtest/lib/engine/gates.py` (GATE_ORDER). 7 of 15 gates are bull-direction suppressors.
2. **VWAP-family detectors** (all DORMANT enabled=false): vwap_continuation, vwap_reclaim_failed_break, vix_regime_dayside, gap_and_go. Direction set by per-detector `*_side` key (put/both).

## STRUCTURAL bull suppressor (NOT a params knob — hard-coded)
`orchestrator.py:767` `bull_min_triggers = max(2, min_triggers)` — bull ALWAYS needs >=2 triggers; bear needs >=1. Asymmetry survives even if params.json filter_10_min_triggers_bull is lowered (Safe=2, Bold=1 in params, but the max(2,..) floor on shared min_triggers can still bind). This is the deepest direction-scope, predates the real-fills engine, never re-validated on it.

## fleet/strategies.py = explicitly direction-AGNOSTIC
REGISTRY (RIBBON_RIDE, VWAP_CONTINUATION) has NO per-strategy direction lock — the comment calls the old per-strategy direction lock "the bug". So the fleet executor layer already matches the target state; the BLOCKS all live UPSTREAM in the orchestrator gate battery + params.json.

## Currently-TRUE bull blocks (Safe): block_elite_bull (VIX 0-25), block_bull_1100_1200, entry_bar_body_pct_min_bull(=0 -> OFF), VIX_BULL_HARD_CAP=18 (filter 9, hardcoded const in filters.py not params), block_bull_ribbon_flip(default False unless override). Bold: block_elite_bull (VIX 15-18), block_bull_morning_agg=false (J killed 2026-06-24).

## Most stale / weakest-evidence bull blocks (re-validate first)
- VIX_BULL_HARD_CAP 18: n_oos_blocked=1 (doc admits "evidence thin"). HARDCODED in filters.py line 805, NOT a params knob.
- block_elite_bull VIX-extension to [0,25): extension band had ZERO IS trades, pure OOS.
- block_bull_1100_1200: n_oos=1.
All ratified pre-2026-06-18 chart-stop-primary flip OR on BS-sim. None re-validated on the BULLISH_RECLAIM_RIDE_THE_RIBBON real-fills path post-flip.
