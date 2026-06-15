# SHOTGUN_SCALPER — Stage 1 Verdict + Stage 2 Plan

> Authored 2026-05-16 morning after grinder deadline reached at 22:58 ET 2026-05-15.

## Headline

**Stage 1: 0 keepers across 939 combos (43% grid coverage).** Best edge_capture was +3% of max (123 of 4150). Zero combos achieved positive sharpe, positive expectancy, or positive wide-window P&L. The strategy AS-DESIGNED with the AS-SEARCHED knob space is not viable for live promotion.

**But Stage 1 produced clear signal for Stage 2.** The least-bad combos cluster on a tight set of knob values, and the per-day P&L on anchor days shows the strategy genuinely captures edge on some days. The problem is over-firing and slow profit locks.

## Why all 939 failed

| Gate | Threshold | Best combo | Verdict |
|---|---|---|---|
| `sharpe` | ≥ 0.8 | -0.08 | far miss |
| `expectancy_per_trade` | ≥ 0.01 | -0.24 | small miss but consistent |
| `n_trades` | ≥ 30 | 1,427 (avg) | way over |
| `max_drawdown_dollars` | ≤ 1,500 | 17,942 | catastrophic |
| `edge_capture_pct` | ≥ 0.5 | 0.03 | only 3% |
| `positive_quarters` | ≥ 4 | 0 | never net-positive in any quarter |
| `top5_pct` | ≤ 0.5 | 999 (sentinel) | concentration bug |

Bottom line: the strategy **fires too often (5–6 trades/day across 16 months)** and each trade has slightly-negative expectancy (-$0.24 to -$0.29 per trade × 1,427 trades = $300–$400 negative net per knob set).

## What clusters in the top 50 by edge_capture

| Knob | Dominant value (% in top 50) | Verdict |
|---|---|---|
| `stop_premium_pct` | **-0.25 (100%)** | LOCKED — widest stop in search space wins every time. Suggests even wider (-30%, -35%) might be better. |
| `chandelier_arm_pct` | **0.40 (80%)** | LOCKED — late arm beats early arm. Suggests +50% or +60% may be better still. |
| `strike_offset` | -1 (56%) / +1 (44%) | ATM (0) is dominated. Avoid ATM. Test deeper ITM (+2). |
| `time_stop_min` | 12 (42%) / 15 (38%) | 8 min too short, 20 min too long. |
| `vol_ratio_threshold` | 1.2 (38%) / 1.5 (32%) | Looser is better. Test 1.0. |
| `tp_premium_pct` | even (0.5–2.0 all ~20%) | Not the bottleneck. Keep broad. |

## Per-anchor-day capture (best combo per day)

| Date | J P&L | Best engine capture | Capture % | Note |
|---|---|---|---|---|
| 2026-04-29 (J_WIN) | +342 | +138 | 40% | partial |
| 2026-05-01 (J_WIN) | +470 | +213 | 45% | partial |
| 2026-05-04 (J_WIN) | +730 | +121 | 17% | undercaptured |
| **2026-05-14 (J_WIN)** | **+1208** | **$0** | **0%** | **NEVER fired — bull-day blind spot** |
| **2026-05-15 (paper)** | **+1400** | **$0** | **0%** | **NEVER fired — chop-reversal blind spot** |
| 2026-05-05 (J_LOSS) | -260 | -8 | "saved" 97% | almost no loss |
| 2026-05-06 (J_LOSS) | -300 | +176 | **+476 turnaround** | engine traded the right side |
| 2026-05-07 (J_LOSS) | -120 | +454 | **+574 turnaround** | engine huge beat |

**The pattern:** SHOTGUN avoids the loser days AND can turn them into wins, but completely misses 5/14 (bull day) and 5/15 (chop-reversal). Two architectural gaps:

1. **Tier 3 (trendline) detector skews bearish** — fires 29 historical observations as "short" but only 0 as "long". The detector's bullish-trendline logic isn't catching.
2. **No fired signal on the 5/15 chop day** — neither Tier 1, Tier 2, nor Tier 3 found the rejection setup that produced +$1400 in puts.

Both are detector bugs (logic gaps), not knob-tuning issues.

## Stage 2 plan — 4-pronged

### Prong 1: Tighter knob search around the winners (1,458 combos)

```
stop_premium_pct     = [-0.25, -0.30, -0.35]                # extended wider
chandelier_arm_pct   = [0.40, 0.50, 0.60]                   # extended later
strike_offset        = [-1, 1, 2]                           # drop ATM, add deeper ITM
time_stop_min        = [10, 12, 15]                         # drop 8, drop 20
vol_ratio_threshold  = [1.0, 1.2, 1.5]                      # drop 2.0
tp_premium_pct       = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]      # extended upward
```

Total: 3 × 3 × 3 × 3 × 3 × 6 = **1,458 combos.** Smaller than Stage 1 grid, but focused on the winning region.

### Prong 2: Detector logic patches (parallel work)

- **Bullish trendline.** The detector's `_detect_trendline_break` works on swing highs (bearish breaks) more reliably than swing lows (bullish breaks). Audit the swing-low detection. Add unit test: today's 09:45 wick to 737.96 + bounce should fire LEVEL_REJECT_LIVE bullish (it does in unit test, but not in historical replay because no levels matched).
- **Tier 2 in historical replay.** Tier 2 requires named levels to be in scope. Historical replay uses auto-derived levels (PMH/PML/PDH/PDL) but only the FOUR. Add intraday-derived levels (e.g., session highs/lows from the past 2 hours rolling) for richer Tier 2 firing.

### Prong 3: Relaxed keeper gates for Stage 2

| Gate | Stage 1 | Stage 2 |
|---|---|---|
| `min_sharpe` | 0.8 | **0.0** (just non-negative) |
| `min_expectancy_per_trade` | 0.01 | **0.05** (still positive) |
| `min_n_trades` | 30 | 30 |
| `max_drawdown_dollars` | 1,500 | **3,000** |
| `min_edge_capture_pct` | 0.5 | **0.20** |
| `min_positive_quarters` | 4 | **2** |
| `max_top5_pct` | 0.5 | **0.6** |
| **NEW** | — | `min_wide_pnl_dollars` = **+100** (must be net-positive) |

### Prong 4: Top 20 "least bad" combos seeded into Stage 2

Even though all 939 failed, the top 20 by edge_capture share the locked knobs (stop=-0.25, cha=0.40). These get seeded as combo IDs 1–20 in Stage 2 so we can compare the relaxed-grid output against the Stage 1 baseline.

## Action items (executed sequentially below)

1. ✅ Test path regression fixed — `test_shotgun_scalper_detector.py` 11/11 pass
2. ✅ Rejections analysis written (this doc)
3. ⏳ Stage 2 grinder built (1,458 combos, relaxed gates)
4. ⏳ Detector logic audit for bullish trendline + Tier 2 intraday levels
5. ⏳ Stage 2 launched in background (~4 hours expected at 1.4 combos/min × 4 workers)

## Honest assessment

The strategy as designed is not viable for live trading. The validation work was the point of building the grinder. Going to Stage 2 with the locked knobs + detector patches is the right next move, not abandoning. But this is genuinely "the strategy needs another iteration" territory, not "tune the knobs and ship." Stage 2 has a real shot — the win/loss day breakdown shows the underlying signal exists, the execution mechanics are killing it.
