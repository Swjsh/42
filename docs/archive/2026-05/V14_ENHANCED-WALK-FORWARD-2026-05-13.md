# v14_enhanced Walk-Forward Validation — 2026-05-13

_Generated: 2026-05-13T19:44:18.537440_

**Verdict: PASS**

_TEST positive ($17901) AND per_month_ratio 2.67x >= 0.5x floor._

## Context (T44c — the OOS gate)

T44b real-fills test (this evening 17:49 ET) PASSED all 3/3 candidates over the wide window. Top combo (this script's WINNER): `stop=-0.20, PL=0.05/0.10, no_trade=09:35, tp1=0.30, runner=2.5, tp1_qty_fraction=0.5, strike_offset_bear=0` → real wide_pnl $36,450 / 4/29 +$869 / 5/12 +$464 / 6/6 quarters / DD $2,857.

T44c (this script) is the OOS gate per CLAUDE.md OP 20 disclosure 3: split data into TRAIN (2025-01-01 → 2025-12-31, 12 months — optimizer saw this) and TEST (2026-01-01 → 2026-05-12, ~4.4 months — held out from wide-window optimizer; J-anchors used only for floor protection). Run BOTH on the same combo and compare per-month normalized P&L.

## Windows

- **TRAIN:** 2025-01-01 to 2025-12-31  (12.0 months — optimizer saw this)
- **TEST:**  2026-01-01 to 2026-05-12  (4.3 months — held out from wide-window optimizer; J-anchors used only for floor protection)

## Headline numbers

| Metric | TRAIN | TEST |
|---|---|---|
| Total P&L | $18,549 | $17,901 |
| Trades | 225 | 92 |
| Win rate | 52.4% | 67.4% |
| Per-month P&L | $1,547 | $4,128 |
| Max drawdown | $2,857 | $1,235 |
| Top-5 day concentration | 65.5% | 50.4% |
| Positive quarters | 4/4 | 2/2 |
| BS-fallback % | 7.1% | 8.7% |

**Per-month ratio (test / train): 2.67x**

## Monthly breakdown (per-month P&L)

| Month | P&L |
|---|---|
| 2025-01 | $+458 |
| 2025-02 | $+579 |
| 2025-03 | $+1,672 |
| 2025-04 | $+3,288 |
| 2025-05 | $-607 |
| 2025-06 | $-1,882 |
| 2025-07 | $+2,852 |
| 2025-08 | $-774 |
| 2025-09 | $+3,941 |
| 2025-10 | $+1,055 |
| 2025-11 | $+7,288 |
| 2025-12 | $+680 |
| 2026-01 | $+8,287 |
| 2026-02 | $+3,208 |
| 2026-03 | $+2,869 |
| 2026-04 | $+1,683 |
| 2026-05 | $+1,854 |

## Quarter breakdown

| Quarter | P&L |
|---|---|
| 2025-Q1 | $+2,708 |
| 2025-Q2 | $+799 |
| 2025-Q3 | $+6,019 |
| 2025-Q4 | $+9,023 |
| 2026-Q1 | $+14,364 |
| 2026-Q2 | $+3,537 |

## Interpretation (per CLAUDE.md OP 20 walk-forward gate)

- **Per-month ratio > 0.7x** = strategy generalizes well to OOS
- **Per-month ratio 0.5–0.7x** = mild overfit, still trade-worthy
- **Per-month ratio < 0.5x** = serious overfit (DO NOT trade)
- **Test P&L < 0** = strategy fails out-of-sample (DO NOT trade)

## Winner combo (the params tested)

```json
{
  "strike_offset_bear": 0,
  "min_triggers_bear": 1,
  "premium_stop_pct_bear": -0.2,
  "tp1_qty_fraction": 0.5,
  "no_trade_before": "09:35",
  "profit_lock_threshold_pct": 0.05,
  "profit_lock_stop_offset_pct": 0.1,
  "tp1_premium_pct": 0.3,
  "runner_target_premium_pct": 2.5
}
```

## Caveats (OP 20 disclosures)

- TEST window overlaps J anchors (4/29..5/12). These days were used for floor protection in the v14_enhanced grinder, so they are NOT fully out-of-sample. Per OP 20 disclosure 2 (sample bias).
- Profit-lock NO-OP in real-fills (simulator_real does not implement it). T44b documented this; same caveat applies here.
- Per-quality exit-knob matrix NO-OP in real-fills (uniform exits across qualities). T44b documented this; same caveat applies here.
- Per-month normalized is the honest metric because TRAIN is 12 months and TEST is ~4.4 months — naive dollar ratios mislead.

## Provenance

- Script: `backtest/autoresearch/v14_enhanced_walk_forward.py`
- Real-fills runner: `lib.orchestrator.run_backtest(use_real_fills=True)`
- Module-level exit-knob patch: `_patched_sim_real_constants` (mirrors T44b)
- T44b reference: `docs/V14_ENHANCED-REAL-FILLS-2026-05-13.md`
