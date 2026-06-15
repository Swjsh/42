# SNIPER v1 — Real-Fills (OPRA) Validation

**Run:** 2026-05-13
**Pipeline:** `backtest/autoresearch/sniper_real_fills.py`
**Combo:** sniper-v1 winner (vol_mult=1.1, body_min=0.02, min_stars=2, strike_offset=2 (ITM-2), premium_stop=-10%, tp1=+40%, runner_target=125%, profit_lock thresh=0%/offset=8%, qty=10)
**Window:** 2025-01-01 → 2026-05-12 (229 trading days with SNIPER trades)
**Verdict:** **CAVEAT** — BS sim materially disagrees with real OPRA fills on 4/4 measured days. Max |diff| 583%.

---

## TL;DR

The SNIPER winner combo's Black-Scholes-based backtest is **NOT validated by real OPRA fills**. Of the 4 days we could test with real option bars, BS sim said all 4 would be small winners (+$180 to +$222 each); real fills produced 1 huge winner and 3 stop-outs — none within the ±20% diff threshold. This is a HIGH-severity caveat against any live deployment of sniper-v1 based on its BS-backed P&L numbers.

The OPRA cache also covers only a tiny slice of the 16-month window (≈ 1.5 months Mar-May 2026, narrow strike bands), so the absolute top-3 BS P&L days could not be tested directly — we ran on the top-3 days that had OPRA coverage instead.

## Top-3 BS P&L days (absolute — NO OPRA data available)

| Date | BS P&L | Side | Strike | OPRA |
|---|---:|---|---:|---|
| 2025-04-07 | +$287.89 | C | 511 | ❌ |
| 2025-04-08 | +$278.07 | C | 521 | ❌ |
| 2026-03-26 | +$263.86 | C | 652 | ❌ |

OPRA cache is overwhelmingly puts at those dates. The SNIPER detector's call-side trades cluster around 2025 spring (when SPY was ~$510-525); the cache for that era is empty. Even Mar 2026 cache is puts-only at strikes 633-655.

## Fallback: Top-3 BS P&L days WITH OPRA coverage

| Date | Side | Strike | BS P&L | Real P&L | Diff% | Status |
|---|---|---:|---:|---:|---:|---|
| 2026-04-09 | C | 675 | +$221.51 | **+$1,514.20** | **+583.6%** | TP1 + runner ran to time-stop with massive favorable move |
| 2026-04-10 | C | 679 | +$218.71 | **−$270.00** | **−223.5%** | Hit premium stop (-10%); BS sim said it would TP1 |
| 2026-04-24 | C | 711 | +$214.79 | **−$285.00** | **−232.7%** | Hit premium stop (-10%); BS sim said it would TP1 |

## J anchor day with OPRA coverage

| Date | Side | Strike | BS P&L | Real P&L | Diff% |
|---|---|---:|---:|---:|---:|
| 2026-04-29 | P | 711 | +$181.84 | **−$329.00** | **−280.9%** |

This is the **most decision-relevant data point**: the SNIPER detector picked the exact same direction and strike (711P) on J's 4/29 trade date. BS sim said +$182; real fills said -$329. **The same setup, on a day J actually won, the engine's BS sim is mispricing by ~3x in the wrong direction.**

## Summary of measured diffs

| | n | min | max | mean abs diff |
|---|---:|---:|---:|---:|
| All 4 measured days | 4 | −280.9% | +583.6% | 330.2% |

No measured day fell within the ±20% threshold required for the gate to clear.

## What's going on (hypothesis)

The BS sim in `sniper_evaluator.py` uses VIX→IV mapping + a simple Black-Scholes model, with same-bar premium computed from SPY high/low spot. This:

1. **Ignores the bid/ask spread** (real-fills script applies $0.02 entry + exit slippage, but this is small compared to the BS modelling error).
2. **Uses constant IV across the bar** — real 0DTE IV moves with realized vol intraday.
3. **Doesn't model the gamma-driven asymmetry** of 0DTE near expiry.
4. **`require_break_above_open=True`** plus the ITM-2 strike means the engine sometimes picks contracts already in the money where the model premium is well off the real market.

Bottom line: BS sim's +$200 winners turning into -$300 stop-outs is consistent with the entry premium being modelled too low — real fills enter much higher, then the same -10% stop bites way faster.

The +$1514 outlier on 4/09 is the opposite issue — real fill happened to have a strong directional move within the bar that the BS-sim's bar-end model never gives credit for.

## OPRA cache gap (the real blocker)

OPRA coverage:
- Total contracts cached: 109
- Date range: 2026-03-16 → 2026-05-07 (≈ 6 weeks)
- 2025: **0 days cached**
- 2026-Q1: ~13 days cached
- 2026-Q2: ~17 days cached
- Strikes per day: typically 1–6 contracts, narrow band around J's actual trades

Of the 229 trading days the SNIPER detector fires on, only ~23 dates have ANY OPRA cache, and of those, even fewer match the SNIPER-selected strike + side. **Real-fills validation cannot be completed against the wide window until the OPRA ingest is expanded.**

## Recommendation for J

1. **DO NOT LIVE-PROMOTE sniper-v1 based on BS sim numbers.** The walk-forward PASS verdict is contingent on a sim layer that does not survive contact with OPRA reality.
2. **OPRA ingest expansion is a P0 prerequisite** to any further SNIPER iteration. Need at least the J-anchor days + top-20 BS P&L days fully cached (all SNIPER candidate strikes ±2).
3. **Investigate the BS-sim premium estimator.** The systematic underestimate of entry premium (which would cause real-stop-outs on BS-winners) is the most likely root cause. Compare BS-computed entry premium vs OPRA bar.open on the 4 measured days as a unit test.
4. **Watch-only deployment ONLY** (per OP 21) until the BS sim is recalibrated against OPRA. Log to `watcher-observations.jsonl`; do NOT trade.

## Reproducibility

- Script: `backtest/autoresearch/sniper_real_fills.py`
- Inputs: `analysis/recommendations/sniper-v1.json` (winner combo), `backtest/data/options/*.csv` (OPRA cache)
- Output JSON: `analysis/recommendations/sniper-v1-realfills.json`
- Run cmd: `python backtest/autoresearch/sniper_real_fills.py`
- Wall time: ~10s (BS sweep) + <1s (real-fills 4 days)
- Cost: $0 (pure Python, no LLM)
