# TRENDLINE_BREAK_RETEST — real_fills

**Window:** 2026-03-15 → 2026-05-08
**Real fills:** True
**Min touches:** 3

## Summary

```json
{
  "trades": 20,
  "total_pnl": 189.42,
  "win_rate": 0.2,
  "avg_winner": 231.29,
  "avg_loser": -45.98,
  "wl_ratio": 5.03,
  "expectancy_per_trade": 9.47,
  "max_drawdown": -630.1,
  "puts_count": 10,
  "calls_count": 10,
  "by_exit_reason": {
    "ExitReason.EXIT_ALL_RIBBON_FLIP_BACK": 9,
    "ExitReason.EXIT_ALL_PREMIUM_STOP": 8,
    "ExitReason.TP1_THEN_RUNNER_TIME": 2,
    "ExitReason.EXIT_ALL_LEVEL_STOP": 1
  }
}
```

## Gate check

```json
{
  "passes_gate_trades": true,
  "passes_gate_wr": false,
  "passes_gate_wl": true,
  "passes_gate_expectancy": true
}
```
