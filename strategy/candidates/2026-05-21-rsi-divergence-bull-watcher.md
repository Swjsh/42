# CANDIDATE: RSI_DIVERGENCE_BULL_WATCHER

**Filed:** 2026-05-21
**Type:** watcher_proposal (OP-21 WATCH-ONLY path)
**Status:** WATCH_FRAGILE — accumulating live observations
**Lead researcher:** Gamma (interactive session, 08:23 ET pre-market)

---

## Hypothesis

Classic 5-minute RSI(14) bullish divergence (price makes lower swing low, RSI makes higher swing low) identifies genuine momentum exhaustion with positive expectancy in the 0DTE intraday window.

---

## Stage-1 Scan Results (16-month SPY 5m backfill)

**File:** `analysis/backtests/rsi-divergence-scan/results.json`
**Script:** `backtest/autoresearch/rsi_divergence_scan.py`

| Metric | Value |
|---|---|
| Total BULL signals | 42 |
| Distinct dates | 41 (no single-day concentration) |
| Overall WR | 81.0% (34/42) |
| Win definition | Next 6 bars: close ≥ entry + $0.25 |
| Loss days | 8 (all single losses, no blowup days) |

**VIX regime stratification:**

| VIX Regime | N | WR |
|---|---|---|
| ELEVATED (≥25) | 6 | 66.7% |
| HIGH (20-25) | 9 | 77.8% |
| MODERATE (15-20) | 27 | **85.2%** |

**BEAR divergence:** N=21, WR=47.6% — no edge, excluded from candidate.

**Monthly WR range:** 0% (Apr 2026, N=1) to 100% (multiple months). April months are consistently weak — strong trend periods override divergence signals.

---

## J Anchor Day Coverage

| Day | Label | Signals | WR |
|---|---|---|---|
| 2025-04-29 | WINNER | None | — |
| 2025-05-01 | WINNER | None | — |
| 2025-05-04 | WINNER | None | — |
| 2025-05-05 | LOSER | None | — |
| 2025-05-06 | LOSER | BULL@09:55 | 100% (price reversed up) |
| 2025-05-07 | LOSER | None | — |

**OP-16 edge_capture assessment:** ZERO standalone. No signals on J winner days (4/29, 5/04). Cannot pass OP-16 edge_capture ≥ $771 as a standalone entry trigger. This is a **COMPLEMENTARY signal**, not a primary entry trigger.

---

## Use Cases

1. **Bull setup entry trigger:** In a BULL_RECLAIM session (if J promotes it), BULL divergence at a named level = high-confidence entry confirmation.
2. **Bear exit signal (hypothesis, unvalidated):** When BULL divergence fires against an active short position, it may signal reversal = accelerate TP1 or exit runner.
3. **Bear entry filter (hypothesis):** When BULL divergence fires at a support level, it creates a "contested" zone — consider tightening stops on any concurrent bear entry.

Use case #2 (exit signal) is the highest-value near-term path given the engine is bear-dominant.

---

## OP-20 Disclosures

1. **Account-size assumption:** Watcher-only, no sizing. If promoted to entry trigger: qty=3 at $1K (standard watcher knobs per OP-21).
2. **Sample bias:** 16-month backfill, mechanical scan, RSI period=14, swing_lookback=5. No look-ahead. Overfit risk: 2 free parameters only. WIN definition (6-bar, +$0.25) is loose — actual option P&L would differ.
3. **Out-of-sample:** NOT DONE. Walk-forward required before any live promotion.
4. **Real-fills check:** NOT DONE. SPY price scan WR ≠ option P&L (per L50). Must run simulator_real.py before any entry trigger use.
5. **Failure modes:** Fails in strong trend months (April periods). If macro regime shifts to persistent bear (tariff shock, credit event), WR could drop to 33%. Max consecutive losses on month: 3 (Apr 2025).
6. **Concentration:** Top 5 dates = 2 signals each (none > 3). No concentration risk.

---

## OP-21 Promotion Path

**Current status:** WATCH-ONLY (historical backtest only, 0 live observations)

**Promotion to WATCH-STABLE (minimum gate):**
- N ≥ 15 live observations (watcher_live + watcher_replay)
- WR ≥ 70% on live obs
- ≥ 8 distinct live dates
- At least 1 of: J confirms seeing the pattern, OR grader confirms match vs live SPY chart

**Promotion to USE-AS-FILTER (complementary use gate):**
- N ≥ 25 live BULL divergence obs
- At least 5 obs where BULL divergence coincided with a concurrent active bear position
- Confirmed via watcher_grader.py that signal fired before price reversal in ≥3 of 5 cases
- J explicit approval per Rule 9

**Standalone entry trigger gate:** NOT RECOMMENDED without OP-16 anchor day coverage.

---

## Next Steps

- [ ] Build `backtest/lib/watchers/rsi_divergence_watcher.py` (watcher module for live observation)
- [ ] Add to `watcher_live.py` runner stages
- [ ] Run watcher_grader.py to grade historical observations
- [ ] Seed exit-enhancer hypothesis to kitchen: "Does BULL divergence improve bear position exit timing?"
- [ ] VIX MODERATE sub-tier: accumulate N ≥ 27 live obs at WR ≥ 80% for standalone bull entry consideration

---

## Parameters

```python
RSI_PERIOD = 14
SWING_LOOKBACK = 5       # bars for prior swing detection
MIN_SWING_SIZE = 0.30    # price swing minimum ($SPY)
MIN_RSI_DIVERGENCE = 2.0 # RSI must diverge ≥ 2 points
WIN_BARS = 6             # lookforward for win check
WIN_MOVE_CENTS = 0.25    # minimum reversal to count WIN
```
