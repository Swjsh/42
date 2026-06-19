# SNIPER_CS_CHART_STOP — Chart-stop SNIPER_LEVEL_BREAK redesign

**Filed:** 2026-06-16  
**Status:** NEEDS-REALFILLS  
**Leaderboard rank:** #23  
**Confidence:** 5/10  

## What it is

SNIPER_LEVEL_BREAK with chart-stop exit instead of premium-percentage stop. Stop placed at `level_price ± chart_stop_buffer` SPY points. TP1 and runner are R-multiples of the chart-stop distance in SPY space, then converted to option P&L via Black-Scholes at the target SPY price.

This redesign is the direct fix for L99 + L100 + L51 + L55 artifact chain:
- L51/L55: premium % stop fires on bid/ask whipsaw before directional move occurs
- L99: profit_lock_threshold=0.0 created fake WR artifacts in BS-sim
- L100: all realistic premium-stop combos negative across 36-combo sweep

## Sweep results (2026-06-16)

64-combo sweep: buffer=[0.30, 0.50, 0.75, 1.00] × tp1_r=[1.5, 2.0, 2.5] × runner_r=[2.5, 3.0, 3.5] × strike_offset=[0, 2]  
n=170 SNIPER signals over 231 trading days (Q1 2025 – Q2 2026)

**50/64 combos positive** (vs all-negative premium exits)

### Top combos by wide_pnl

| buf | tp1_r | run_r | off | wide_pnl | WR% | pos_q | WF |
|-----|-------|-------|-----|----------|-----|-------|----|
| 0.75 | 2.0 | 3.5 | 0 | $24,943 | 32.9% | 5/6 | 0.187 |
| 0.75 | 2.0 | 3.0 | 0 | $24,418 | 32.9% | 5/6 | 0.208 |
| 0.75 | 1.5 | 3.5 | 0 | $21,858 | 37.1% | 4/6 | 0.226 |
| 0.75 | 2.0 | 3.5 | 2 | $22,155 | 40.0% | 5/6 | 0.282 |

### WF-passing combos (WF >= 0.5)

| buf | tp1_r | run_r | off | wide_pnl | WR% | pos_q | WF |
|-----|-------|-------|-----|----------|-----|-------|----|
| 0.75 | 2.5 | 3.5 | 2 | **$19,692** | 36.5% | **6/6** | **0.621** |
| 0.75 | 1.5 | 3.5 | 2 | $19,085 | 43.5% | 4/6 | 0.622 |
| 0.75 | 2.5 | 3.0 | 2 | $19,391 | 36.5% | 4/6 | 0.545 |
| 1.00 | 2.5 | 3.0 | 2 | $13,790 | 37.1% | 4/6 | 1.381 |
| 1.00 | 2.5 | 3.5 | 2 | $12,530 | 37.1% | 4/6 | 1.685 |
| 0.50 | 1.5 | 3.0 | 2 | $930 | 41.8% | ? | 2.255 |

**Recommended top combo:** buf=0.75, tp1_r=2.5, runner_r=3.5, strike_offset=2  
→ $19,692, WR=36.5%, 6/6 quarters positive, WF=0.621

## Key structural findings

1. **Buffer=0.75 sweet spot** — 16/16 combos positive ($18K–$24K). Buffer=0.30 too tight (initial retest chop stops out), buffer=1.00 R-ratio too low.

2. **ATM beats ITM-2 for wide_pnl** — opposite of L74 (TBR ATM FAIL for premium-stop scalpers). Chart-stop removes the delta-buffer need: stop fires on SPY price, not premium %, so ATM's lower delta is compensated by smaller absolute stop.

3. **Concentration in vol-spike events** — top5_pct=1.0–1.6 for best combos. P&L concentrated in Liberation Day Q1/Q2 2025 VIX spike events. OOS (Q4 2025 + 2026) WF=0.19–0.26 for ATM combos.

4. **J anchor mismatch (L97 pattern)** — J's 4/29 (+$342), 5/01 (+$470), 5/04 (+$730) anchor wins are BEARISH_REJECTION_RIDE_THE_RIBBON entries (ribbon-flip + trendline reject), NOT SNIPER_LEVEL_BREAK fires. SNIPER fires on vol-spike level crosses at different bars. All J floor checks fail but this is structural — the OP-16 gate is inapplicable until SNIPER-specific anchor days are identified.

## SNIPER-specific anchor days (identified 2026-06-16)

Full day-level trade extraction from the best WF-pass combo (buf=0.75, tp1=2.5, runner=3.5, off=2):

**Top 5 SNIPER winners:**
| Date | P&L | Exit | vol_ratio |
|------|-----|------|-----------|
| 2025-04-09 | +$3,489 | TIME_STOP_ALL | 2.68 |
| 2025-10-10 | +$1,789 | TP1_THEN_RUNNER_TARGET | 9.03 |
| 2025-05-21 | +$1,485 | TP1_THEN_TIME_STOP | 2.63 |
| 2026-03-02 | +$1,435 | TP1_THEN_RUNNER_TARGET | 1.97 |
| 2025-04-30 | +$1,379 | TP1_THEN_TIME_STOP | 1.91 |

**Worst 5 SNIPER days:**
| Date | P&L | Exit | vol_ratio |
|------|-----|------|-----------|
| 2025-04-07 | -$969 | CHART_STOP_ALL | 9.04 |
| 2025-04-23 | -$877 | TIME_STOP_ALL | 2.01 |
| 2026-04-02 | -$763 | CHART_STOP_ALL | 5.20 |
| 2025-03-04 | -$759 | CHART_STOP_ALL | 4.41 |
| 2025-01-06 | -$646 | TIME_STOP_ALL | 2.65 |

**Key insight:** 2025-04-09 (+$3,489, Liberation Day bounce) and 2025-04-07 (-$969, Liberation Day itself) are the extreme bookends. VIX>35 filter (L99) would remove 4/07 loss but also risk removing 4/09 winner (VIX was still elevated on 4/09 but dropping). The VIX regime filter study in kitchen task `snip4-vix-regime-filter-01` should test VIX>15, VIX>18, and VIX>25 thresholds — NOT VIX>35 which may remove the best winner day.

**Candidate anchor days for J confirmation** (SNIPER-specific, NOT BEARISH_REVERSAL):
- 2025-04-09: Liberation Day bounce put-entry at vol-spike level
- 2025-10-10: High vol_ratio=9.03 SNIPER fire with full TP1+runner
- 2025-05-21: vol_ratio=2.63, TP1+runner

## Pre-promotion requirements

- [ ] **Real-fills N≥5** on non-extreme-VIX SNIPER fires (VIX<30 per L99)
- [ ] **SNIPER-specific anchor days identified** — find 3+ actual vol-spike level break wins to use as OP-16 floors
- [ ] **VIX regime filter study** — test VIX>15 or VIX>18 gate; VIX-escalating (L73) not applicable to SNIPER per L93; test non-directional VIX>15 threshold
- [ ] After VIX filter: re-run sweep; if ATM OOS WF lifts to ≥0.5, advance to PROMISING

## Graduated guards

`backtest/tests/test_graduated_guards.py` → `test_sniper_cs_uses_chart_stop_not_premium_stop`
- Asserts `SniperCSCombo` has `chart_stop_buffer` field
- Asserts no `premium_stop_pct` field
- Asserts `chart_stop_spy` string present in simulation logic
- Asserts `_simulate_cs_trade` function exists

## Files

- `backtest/autoresearch/sniper_cs_evaluator.py` — chart-stop evaluator (340 lines)
- `backtest/autoresearch/sniper_cs_sweep.py` — 64-combo sweep
- `analysis/recommendations/sniper-cs-sweep.json` — full sweep results
- `docs/LESSONS-LEARNED.md#L101` — full lesson write-up
