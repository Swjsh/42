# SNIPER_LEVEL_BREAK VIX>=18 Regime Filter

**Type:** Filter / regime gate — SNIPER_LEVEL_BREAK (real-fills validated)  
**Filed:** 2026-05-23  
**Status:** NEEDS-MORE-DATA — passes WR gate, fails P&L and +quarters gates. Next: VIX-filtered grinder sweep  
**Scripts:** `autoresearch/_sniper_vix_regime_filter.py` + `autoresearch/_morning_filter_test.py`  

---

## Motivation

SNIPER best real-fills combo (strike_offset=2, stop=-10%, lock=5%/5%, tp1=50%, runner=2.0):
- wide_pnl: **-$91** (all 347 trade dates, 150 trades)
- Quarter breakdown confirms regime problem:
  - 2025-Q1: +$963 (high-VIX, trending)
  - 2025-Q2: -$1,062 (low-VIX, choppy summer)
  - 2025-Q3: -$1,875 (low-VIX, summer doldrums)
  - 2025-Q4: -$549 (moderate, mixed)
  - 2026-Q1: +$3,701 (very high-VIX, tariff spike)
  - 2026-Q2: -$1,270 (post-spike mean reversion)

Hypothesis: SNIPER level breaks only produce true breakouts when VIX is elevated.
Low-VIX level breaks tend to be false breakouts (price rotates back through the level).

---

## Morning Filter Result (before 10:30 is best, but regime dominates)

| no_trade_after | n_trades | wide_pnl | WR | +quarters |
|---|---:|---:|---:|---:|
| before 10:30 | 61 | +$1,051 | 54.1% | 2/6 |
| before 11:00 | 76 | -$651 | 50.0% | 2/6 |
| before 12:00 | 93 | -$2,427 | 47.3% | 2/6 |
| before 15:50 (baseline) | 150 | -$91 | 50.0% | 2/6 |

**Key finding:** Morning-only (before 10:30) is the only profitable time cut, but it still shows
only 2/6 positive quarters. The regime (VIX level) is more impactful than time-of-day.

---

## VIX Regime Filter Results

Tested: skip day if prior_day_VIX_close < threshold.

| Threshold | n_trades | wide_pnl | WR | +quarters | Days skipped |
|---|---:|---:|---:|---:|---:|
| no_filter | 150 | -$91 | 50.0% | 2/6 | 0 |
| VIX >= 14 | 149 | -$229 | 49.7% | 2/6 | 2 |
| **VIX >= 16** | **115** | **+$983** | **51.3%** | **2/6** | **74** |
| **VIX >= 18** | **70** | **+$1,472** | **54.3%** | **3/5** | **190** |
| VIX >= 20 | 41 | +$40 | 58.5% | 3/5 | 250 |
| VIX >= 22 | 27 | -$159 | 55.6% | 3/5 | 283 |

### Quarter breakdown by threshold

| Threshold | 2025-Q1 | 2025-Q2 | 2025-Q3 | 2025-Q4 | 2026-Q1 | 2026-Q2 |
|---|---:|---:|---:|---:|---:|---:|
| no_filter | +$963 | -$1,062 | -$1,875 | -$549 | +$3,701 | -$1,270 |
| VIX >= 16 | +$1,048 | -$1,062 | -$1,000 | -$648 | +$3,915 | -$1,270 |
| VIX >= 18 | +$1,637 | -$252 | $0 | +$522 | +$617 | -$1,051 |
| VIX >= 20 | +$856 | +$459 | $0 | -$1,119 | +$226 | -$382 |
| VIX >= 22 | +$25 | +$566 | $0 | -$816 | +$448 | -$382 |

**Best: VIX>=18** — $1,472 wide_pnl, 54.3% WR, 3/5 positive quarters.

---

## Gate Check (VIX >= 18)

| Gate | Result | Status |
|---|---|---|
| wide_pnl > $2,000 | $1,472 | ✗ FAIL |
| WR >= 45% | 54.3% | ✓ PASS |
| positive_quarters >= 4/6 | 3/5 | ✗ FAIL |

**FAILS 2 of 3 gates.** Not ready for ratification in this form.

---

## Analysis

The VIX>=18 filter:
1. Eliminates the catastrophic Q3 2025 ($0 trades — no VIX>=18 days that quarter)
2. Turns Q4 2025 from -$549 to +$522 (selective entry on high-VIX days)
3. Turns Q2 2025 from -$1,062 to -$252 (much smaller loss)
4. Q2 2026 is still -$1,051 (recent choppy regime despite 70 skipped days)

**Why VIX>=20 collapses:** Too few qualifying days (41 trades vs 150). The signal is thin.

**The remaining weakness:** Even with VIX>=18, the combo still uses stop=-10% which is tight
for real-fills. The sniper grinder is simultaneously testing wider stops (-0.15 to -0.25).
VIX filter + wider stop might unlock additional improvement.

---

## Recommended Next Steps

1. **VIX-filtered grinder sweep:** Bake VIX>=18 into the sniper real-fills grinder. Run the
   432-combo grid (wider stop + profit-lock variants) with VIX>=18 pre-filter. The current
   best combo (-$91) with VIX filter gives $1,472; a better stop width might clear the $2,000
   gate.

2. **Combined filter:** VIX>=18 AND no_trade_after=10:30. Morning breakouts in high-VIX
   environments only. This combination hasn't been tested.

3. **Q2 2026 deep-dive:** Why is SNIPER still losing in Q2 2026 even with VIX>=18?
   Check if the tariff-reversal regime (May 2026) has VIX above 18 but rapidly mean-reverting
   price action that kills level-break follow-through.

4. **Consider SNIPER as supplementary signal:** SNIPER might be better integrated as an
   additional trigger in the BEARISH_REJECTION_RIDE_THE_RIBBON orchestrator rather than a
   standalone strategy. The $42K real-fills result from v14_enhanced shows the RIBBON strategy
   is already capturing most of the available bear edge.

---

*Candidate filed by Gamma (engine calibration session, 2026-05-23 23:15 ET)*  
*Morning filter: `_state/morning_filter_results.json`*  
*VIX regime filter: `_state/sniper_vix_regime_results.json`*
