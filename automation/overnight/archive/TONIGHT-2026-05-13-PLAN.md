# TONIGHT'S OVERNIGHT GRIND PLAN — 2026-05-13 → 2026-05-14

> Drafted 09:14 ET morning of 5/13. Will execute starting ~17:07 ET after EOD reflection.

## Goal

**Retire BS sim entirely. Re-run all strategies on real OPRA fills. Make every wide_pnl number honest.**

## Tonight's task priority order

1. **T41 (CRITICAL)** — Retire BS sim. Refactor `simulator.py` to be a thin wrapper around `simulator_real.py`. Hard dep on warm OPRA cache. Adds 20-30x slowdown per combo.
2. **T42 (HIGH)** — Re-run SNIPER pipeline Stages 1-5 against real OPRA. Expected: `premium_stop_pct=-0.10` widens to -0.20. Output: `sniper-v2.json`.
3. **T44 (HIGH)** — Re-test v14_enhanced front-runner combo (4/29 +$293 / 5/12 +$241 BS) on real OPRA. If it holds, this is a RATIFIABLE candidate (engine BEATS J on 5/07 loser).
4. **T37 (HIGH)** — REGIME_SWITCHER Stage 2: re-tune per-regime sub-strategy combos. Read tonight's v14_enhanced keepers and pick best per regime. Re-derive spec section 3 mappings against real measured bars.
5. **T40 (HIGH-Maybe)** — Wire `heartbeat-v15-draft.md` to paper-trade new strategies via Alpaca (only after T42 cleared).
6. **T43 (LOW)** — Re-ingest OPRA with ±10 strike window to close 2 still-blocked top-3 days.
7. **T38 (LOW)** — T12 audit + queue 3 high-leverage items from FUTURE-IMPROVEMENTS.md.
8. **T39 (LOW)** — Profile v14e grinder memory to understand silent-death pattern.

## Cron schedule (proposed)

- Evening grind: `7,37 17-23 * * *` — 14 fires from 17:07 to 23:37 ET
- Night grind: `7,37 0-6 * * *` — 14 fires from 00:07 to 06:37 ET
- Total: 28 fires × ~$0.80/fire (with subagents) = ~$22 budget
- Hard cap: $50

## Pre-flight checks before firing cron

1. Verify Claude Code session alive (cron is session-scoped — `durable=true` lets it survive)
2. Verify PC sleep settings (powercfg -change -standby-timeout-ac 0 done 2026-05-12)
3. STATUS.md updated with `last_fire_at` = post-EOD timestamp
4. queue.md has all tonight tasks queued
5. wake-protocol.md hardened with all 5 foot-guns absorbed today

## Self-test the cron template before firing

Run one `--print` invocation manually to make sure the prompt template works:
```powershell
claude --print --output-format json "You are a gamma-overnight-grinder wake fire. Read STATUS.md ..."
```

## Expected morning state (06:55 ET 5/14)

- `analysis/recommendations/sniper-v2.json` (real-fills version)
- `analysis/recommendations/v14_enhanced-v1.json` (re-tested on real fills)
- `strategy_pnl_matrix.json` re-built with simulator_real
- `regime_switcher-v2.json` with retuned sub-strategies
- `docs/MORNING-BRIEF-2026-05-14.md` synthesizing all results

## Banned tonight (per OP 24 + 25)

- DO NOT modify `automation/prompts/heartbeat.md` (production)
- DO NOT modify `automation/state/params.json` (production rule version pin)
- DO NOT place live Alpaca orders
- DO NOT sign off / go dark
- DO NOT mark task "blocked on J input" — find the next task on queue
