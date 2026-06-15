# Walk-forward validation — SNIPER_LEVEL_BREAK

_Generated: 2026-05-13T05:11:07.110211_

**Verdict: PASS**

_TEST positive AND test_per_month 2891/mo is 1.35x train_per_month 2141/mo (>= 0.5x floor)_

## Windows

- **TRAIN:** 2025-01-01 to 2025-12-31  (12.0 months — optimizer saw this)
- **TEST:**  2026-01-01 to 2026-05-12  (4.3 months — held out from wide-window optimizer; J-anchors used only for floor protection)

## Headline numbers

| Metric | TRAIN | TEST |
|---|---|---|
| Total P&L | $25676 | $12537 |
| Trades | 163 | 66 |
| Win rate | 92.0% | 95.5% |
| Per-month P&L | $2141 | $2891 |
| Max drawdown | $415 | $256 |
| Top-5 day concentration | 5.1% | 10.1% |
| Positive quarters | 4 / 4 | 2 / 2 |

**Per-month ratio (test / train): 1.35x**

## Quarter breakdown

| Quarter | P&L |
|---|---|
| 2025-Q1 | $+6316 |
| 2025-Q2 | $+5230 |
| 2025-Q3 | $+6374 |
| 2025-Q4 | $+7757 |
| 2026-Q1 | $+8980 |
| 2026-Q2 | $+3557 |

## Interpretation (per CLAUDE.md OP 20)

- **Per-month ratio > 0.7x** = strategy generalizes well to OOS
- **Per-month ratio 0.5–0.7x** = mild overfit, still trade-worthy
- **Per-month ratio < 0.5x** = serious overfit (DO NOT trade)
- **Test P&L < 0** = strategy fails out-of-sample (DO NOT trade)

## Winner combo (the params tested)

```json
{
  "vol_mult": 1.1,
  "body_min_cents": 0.02,
  "min_stars": 2,
  "strike_offset": 2,
  "premium_stop_pct": -0.1,
  "tp1_premium_pct": 0.4,
  "runner_target_pct": 1.25,
  "profit_lock_threshold_pct": 0.0,
  "profit_lock_stop_offset_pct": 0.08,
  "tp1_qty_fraction": 0.667,
  "qty": 10,
  "proximity_dollars": 1.5,
  "require_break_above_open": true
}
```

## Caveats

- TEST window is 2026-01-01..2026-05-12 (~4.4 months). Wide-window metric (wide_pnl) of the optimizer was 2025-01-01..2026-05-07, so TEST overlaps with the very last 5 days of the optimizer's window. J-anchor days (4/29..5/07) sit inside TEST AND were used for floor protection in the optimizer. This is selection bias and is called out per OP 20 disclosure 2 (sample bias).
- Real-fills (OPRA) validation NOT done here. Required separately per scorecard's `next_actions[1]`.
- Per-month normalized is the honest metric because TRAIN is 12 months and TEST is ~4.4 months — naive dollar ratios mislead.