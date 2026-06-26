---
name: block-bull-1100-1200-revalidated
description: block_bull_1100_1200 (Safe) RE-VALIDATED under the current real-fills engine 2026-06-26 -- KEEP, still earns its keep (5/5 blocked midday bulls are real-fills losers)
metadata:
  type: project
---

block_bull_1100_1200 (Safe, gates.py gate #5, blocks ALL bull/C entries 11:00-12:00 ET) RE-VALIDATED 2026-06-26 under the CURRENT engine (real OPRA fills via simulate_trade_real, Safe $2K / OTM-2, managed exit_manager) -> **VERDICT KEEP, block STILL justified.**

**Why:** A/B (block ON vs OFF, full production params armed, use_real_fills=True, 2025-01-02..2026-06-18): under the current engine only 5 bull setups survive upstream gates to reach this gate (the old BS-sim n=11 shrank because block_level_rejection/block_elite_bull/doji gates now suppress the rest upstream). ALL 5 are LOSERS: WR=0%, total -$1,299, every one exits EXIT_ALL_PREMIUM_STOP (-50% cap). Block removes -$1,299 of pure loss. Aggregate: unblocking costs the whole engine ~-$1,014 real-fills. The "ITM+managed exits rescue midday bulls" hypothesis is EMPIRICALLY FALSE here -- OTM-2 + premium-stop still bleeds these out. Anchor/bear no-regression CONFIRMED: bear trade set byte-identical (n=38, $2,464 both runs) -- bull-only gate never touches the bearish source-of-truth.

**How to apply:** Do NOT re-cook an UNBLOCK of block_bull_1100_1200. The block earns its keep under the current engine. The 5 blocked dates: 2025-01-03, 2025-02-10, 2025-09-26, 2025-12-09, 2025-12-11 (all 11:0x-11:30 ET CALLs, all -50% stop-outs). ONE soft spot per OP-22: G2 OOS_delta = $0 (zero OOS victims survive upstream under the current engine, so no fresh OOS confirmation) -- but G1 IS is unambiguous and aggregate + anchor both pass. Contrast w/ [[project_direction_block_inventory]]: this was flagged "most stale, n_oos=1, re-validate first" -- re-validation says KEEP, not every old-engine block is stale. Script: backtest/autoresearch/_revalidate_block_bull_1100_1200.py (reusable A/B pattern for the other direction-blocks: load params.json minus _doc keys, toggle one gate, diff trade sets, score real fills).
