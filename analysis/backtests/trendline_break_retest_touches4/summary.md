# TRENDLINE_BREAK_RETEST — touches4

**Window:** 2026-03-15 → 2026-05-08
**Real fills:** True
**Min touches:** 4

## Summary

```json
{
  "trades": 13,
  "total_pnl": 507.59,
  "win_rate": 0.231,
  "avg_winner": 306.94,
  "avg_loser": -41.32,
  "wl_ratio": 7.43,
  "expectancy_per_trade": 39.05,
  "max_drawdown": -315.05,
  "puts_count": 7,
  "calls_count": 6,
  "by_exit_reason": {
    "ExitReason.EXIT_ALL_RIBBON_FLIP_BACK": 6,
    "ExitReason.EXIT_ALL_PREMIUM_STOP": 4,
    "ExitReason.TP1_THEN_RUNNER_TIME": 2,
    "ExitReason.EXIT_ALL_LEVEL_STOP": 1
  }
}
```

## Gate check

```json
{
  "passes_gate_trades": false,
  "passes_gate_wr": false,
  "passes_gate_wl": true,
  "passes_gate_expectancy": true
}
```
