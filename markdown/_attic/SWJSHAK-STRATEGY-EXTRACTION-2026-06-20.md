# SwjshAlgoKnife — Strategy Extraction (read-only pull) — 2026-06-20

> **Source:** `C:\Users\jackw\Desktop\SwjshAlgoKnife` (J's first project — 68,114 files, ~95% build bloat). **Read-only** — nothing in the old project was modified. Extracted surgically via 3 read-only Explore agents; build dirs (`.next`, `.next.bak`, `node_modules`, `__pycache__`, `backups`, `_archive`) ignored.
> **Mandate:** pull *strategies for testing* + genuinely-useful bits, **without dragging the bloat / overengineering** the current project. J fed his old strats into agent "personalities" (`scripts/agent_personas.*`, `data/brain/agents/*`, `Library/agent-souls/`) — that's where most of these live.

## The distinct strategies (deduped)

| # | Strategy | Instrument (orig) | Core rule (concise) | SPY-0DTE / futures testable? | Status here |
|---|---|---|---|---|---|
| 1 | **Pivot rejection** (Pivot Pete) | ES/NQ/GC 5m | Floor pivots (R1-3/S1-3, multi-TF); wick/pinbar rejection at a confluence pivot + volume → trade to next pivot | ✅ SPY 5m / MNQ-MES | **≈ already in running hunt** (`cpr_pivot_bounce`) |
| 2 | **VWAP mean-reversion** | all, 5m | Price ≥ N% (or N-σ band) from session VWAP → fade back to VWAP | ✅ SPY 5m | **≈ already in running hunt** (`vwap_extension_reversion`) |
| 3 | **RSI mean-reversion** | crypto/range 5m | RSI<30 + bullish-confirm bar → long; RSI>70 + bearish-confirm → short | ✅ SPY 5m | **≈ already in running hunt** (`rsi2_mean_reversion`) |
| 4 | **Inverse-ORB / OR fade** | MNQ 15m | When OR is wide, FADE the OR extreme (mean-revert) instead of breaking out | ✅ SPY/futures | **≈ already in running hunt** (`opening_range_fade`) |
| 5 | **Supply/Demand zone reversal** (Boba) | SPY/QQQ 15m | Mark fresh (untested) 15m S/D zones from an impulse candle (body>2×ATR); reversal entry on first retest, 9:30-11:00 ET | ✅ SPY | **NEW — queue for hunt** |
| 6 | **EMA(9/21) + ADX>25 filter** | futures 15m | EMA cross, but ONLY take it when ADX>25 (trend, not chop). Claimed 45%→55-60% WR with the filter | ✅ SPY/futures | **NEW — queue** (an ADX *regime gate* we don't have) |
| 7 | **Three Ducks (MTF align)** | FX | 4H price>SMA60 + 1H>SMA60 + 5m SMA60 cross → entry (all 3 TFs agree) | ✅ SPY/futures | **NEW — queue** |
| 8 | **Bollinger squeeze breakout** | all | BB(20,2) bandwidth squeeze → expansion + volume → breakout entry | ✅ SPY/futures | **NEW — queue** |
| 9 | **ES/NQ divergence** | ES+NQ | Both indices outside their ORs; one breaks back inside → trade the laggard | ⚠️ futures (needs 2 feeds) | NEW — futures-only, lower priority |
| 10 | **SPX Sniper** (0DTE VWAP+momentum) | SPX 0DTE | VWAP filter + momentum burst, 10:30 gate, 45-min max hold, 40% stop | — | **We already have this** (≈ live engine + vwap_continuation) |
| 11 | Set & Forget (FXAlexG S&D swing) | FX, multi-day | Weekly→Daily→4H top-down S&D zones, limit orders, 1:3-1:6 RR | ❌ multi-day swing | Out of scope (logic ≈ #5). *Note: their only real backtest — S&D beat VWAP on GBPUSD, WR 61.7% vs 47.7%* |
| 12 | Gold-DXY mismatch | XAU/DXY | Z-score correlation-break retracement | ❌ correlation pair | Out of scope |
| 13 | Bitcoin Bob (volume-impulse/HODL), Grid | crypto | impulse-zone + POC; grid range | ❌ crypto | Out of scope (impulse-zone logic ≈ #5) |

## What to actually test (the new-to-us shortlist)
The running new-strategy hunt already covers #1-4. The **genuinely-new additions worth a second hunt** (all SPY-5m / futures testable, all classes we lack):
1. **Supply/Demand zone reversal** (#5) — impulse-candle zone, fresh-only, reversal on retest. (Our nearest is named-level interactions; true S/D-zone is new.)
2. **EMA(9/21) + ADX>25 regime gate** (#6) — not the EMA cross itself but the **ADX trend-vs-chop filter** is the reusable idea; could also gate our *existing* setups.
3. **Three Ducks MTF alignment** (#7) — a clean multi-TF momentum confirmation.
4. **Bollinger squeeze → expansion breakout** (#8) — volatility-regime entry.

These will go through the same real-fills harness (OOS-split, drop-top-5, OP-20) as the current hunt. Expectation set honestly: 0DTE theta is brutal — several will likely fail, same as our own fleet.

### TESTED 2026-06-25 — all 4 ground through matrix → funnel → null (`markdown/research/GRIND-NEW-FAMILIES-2026-06-25.md`)

Built `backtest/autoresearch/family_detectors.py` (4 causal per-session detectors + look-ahead-guard TDD) + `family_grind.py` (strike×stop×exit matrix → qpf/realizability funnel → random-entry null, real OPRA fills C1) + `_verify_bollinger.py` (the direction-controlled null). Verdicts:

| # | Family | Verdict | Why |
|---|---|---|---|
| 8 | **Bollinger squeeze → expansion breakout** | ✅ **FORWARD-VALIDATE** | The ONE survivor. $34.9/tr, **WF 1.43 (OOS>IS)**, qpf 1.0, **two-sided** (C +$29 / P +$41), 13/13 coherent strike/stop surface; survives BOTH the stock null AND the stricter direction-controlled null. Registered as a fleet challenger (in-sample search → forward-validate, not a flip). |
| 5 | Supply/Demand zone reversal | ❌ DEAD | 1/28 null-pass = below chance for 28 shots; the lone cell's drop-top5 per-trade is negative (concentration-driven). |
| 6 | EMA(9/21) + ADX>25 gate | ❌ DEAD | 0/15 null-pass — exit-structure artifact; the ADX-gated cross adds nothing over random entry through the same bracket. |
| 7 | Three Ducks MTF | ❌ DEAD | Passed the stock (random-side) null 4/8 but COLLAPSES vs the direction-controlled null — pure direction-following, no selection alpha; fires 98% of days (C27 noise). |

**Net: 1 of 4 widens the strategy table (bollinger_squeeze, as a forward-validation fleet challenger); 3 eliminated, each for a distinct documented reason. A wall is progress.**

## "Other useful things" — and why I'm NOT porting them (anti-overengineer)
The old project has a backtest harness + `anti_cheat.py` (flags Sharpe>5 / WR>90% / >500% return as overfit) + `fee_model.py` + a walk-forward optimizer + genetic mutation params. **Recommendation: do NOT port any of it.** We already have stronger equivalents — `simulator_real.py` (real OPRA fills, the C1 authority — beats their synthetic harness), the 5-stage grinder + OOS/walk-forward, and OP-20/the verify gates (our anti-overfit). Porting theirs = re-introducing the exact bloat that killed the old project. The **one idea worth borrowing as a concept** (not code): `anti_cheat`'s "auto-flag a result that's too good to be true" — but we already enforce that via the drop-top-5 + concentration + OOS gates. Net: take the **strategies**, leave the **infrastructure**.

## Provenance (read-only sources)
`data/brain/strategies.md`, `data/brain/strategies-overview.md`, `data/brain/pivot-strategy.md`, `data/brain/{orb,vwap-reversion,ema-crossover-adx,rsi-mean-reversion,three-ducks,bollinger-breakout,never-stopped-out}.md`, `data/brain/agents/*.md`, `docs/boba_strategy/STRATEGY_RULES.md`, `docs/fxalexg/STRATEGY_SPEC.md`, `docs/agent-strategy-map.md`, `.claude/plan/gold-dxy-mismatch-strategy.md`, `data/backtests/BACK-25_Sterling_FX_Strategy_Comparison.md`, `scripts/auto_research/candidate_strategy.py`, `scripts/agent_personas.*`.
