---
name: chart-reading-gym
description: Gym-scale replay of historical bars through the chart-reading pipeline (detectors + fast_path_executor). Validates correctness, latency, and decision density across N trading days. Pure Python — $0 cost. Per OP-26 + ENGINE-EYES doctrine, ratified 2026-05-18 evening per J's "take the new chart reading system to the gym" directive.
context: session
allowed-tools: Bash Read
---

# chart-reading-gym — replay historical bars through the new detection pipeline

## When to invoke

- **Before any production-affecting change to chart_patterns.py** — re-validates the new logic against 60+ days of historical bars
- **After adding a new detector** to confirm it integrates without crashes
- **Periodically (weekly)** to catch detector drift
- Ad-hoc when J asks "did the new detector break anything?" or "is the chart-reading still fast enough?"

## How to invoke

- **Slash:** `/chart-reading-gym` (default 10 days back from CSV end)
- **With days:** `/chart-reading-gym 60` (last 60 trading days)
- **With range:** `/chart-reading-gym 2025-01-02 2026-05-15` (16 months)
- **Direct:** `python backtest/autoresearch/chart_reading_gym.py [--days N | --range START END]`

## What it does

1. Loads `pattern_backtest.py` + `fast_path_executor.py` in-process (no subprocess overhead).
2. For each weekday in range:
   - Runs all 7 detectors against the day's bars
   - Filters to alert-class hits (confidence ≥ 0.65 + contra-trend + regime-known)
   - Replays each alert through `fast_path_executor` with mocked RTH + favorable VIX (16.5 falling) + neutral account
   - Records per-decision: account, decision, elapsed_ms
3. Aggregates: total hits, alert-class hits, fast-path decisions, ENTER/SKIP breakdown, errors, p95/max latency.
4. Writes `analysis/chart-reading-gym-{timestamp}.json` (full per-day detail).
5. Prints summary + verdict.

## Pass criteria

- **Errors: 0** across all days (detector + executor must not crash on any historical bar)
- **Latency budget: max < 5s/decision** (5x headroom vs production 30s budget)
- **Decision density: > 1.0 fast-path decision per day on average** (sanity — system actually fires sometimes)

## Output shape

```
=== CHART READING GYM — {start} to {end} (CSV: {csv}) ===

Days scanned:                  357
Total pattern hits:            6,187
Alert-class hits:              1,902
Fast-path decisions evaluated: 3,804
  ENTER decisions:             2,202
  SKIP decisions:              1,602
Errors:                        0

FPE latency p95 across days:   0ms
FPE latency max across days:   1ms
Latency budget (<5s/bar):      PASS

Gym wall time:                 33.1s
Scorecard:                     analysis/chart-reading-gym-{ts}.json
```

## Last validation (2026-05-18 evening)

- 357 days (16 months), 0 errors, 3,804 fast-path decisions evaluated
- Max latency: 1ms (mocked Alpaca; real production ~200ms)
- GREEN — full pipeline correctness validated for tomorrow's first live-mode trading day
