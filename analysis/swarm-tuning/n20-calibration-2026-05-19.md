# Swarm N20 Calibration Report — 2026-05-19

## Gate Status
- **N_untested_tradeable:** 22
- **Gate threshold:** 20
- **Gate met:** YES

## Calibration Metrics
| Metric | Value |
|---|---|
| ECE (all tradeable days) | 32.31% |
| ECE (UNTESTED days only) | 37.86% |
| Drift threshold | ±5.0pp |

## Per-Bucket Accuracy
| Battle Grade | N | WR% | Implied65 | Drift(65) | ActConf | Drift(Actual) | Recommendation |
|---|---|---|---|---|---|---|---|
| BROKE | 10 | 80.0% | 65 | +15.0pp | 74.1 | +5.9pp | current_adjustment=0 -> recommend 5 (drift_actual=+5.9pp, mean_actual_conf=74.1% vs WR=80.0%)  [NOTE: base-65 assumption invalid for BROKE — use actual-conf drift] |
| HELD | 14 | 50.0% | 45 | +5.0pp | 63.1 | -13.1pp | ✅ OK |
| TESTED_MIXED | 15 | 86.7% | 65 | +21.7pp | 65.8 | +20.9pp | current_adjustment=0 -> recommend 20 (drift_actual=+20.9pp, mean_actual_conf=65.8% vs WR=86.7%)  [NOTE: base-65 assumption invalid for TESTED_MIXED — use actual-conf drift] |
| UNTESTED | 22 | 54.5% | 50 | +4.5pp | 52.1 | +2.4pp | ✅ OK |

> **Drift(65):** WR% minus base-65-implied confidence. Valid for UNTESTED/HELD.
> **Drift(Actual):** WR% minus mean formula output. Corrects for base-65 assumption on
> BROKE/TESTED_MIXED (where 4/4-agree bonus inflates base above 65). Use this measure
> to diagnose whether formula needs a penalty/boost for high-agreement battle grades.

## Verdict
**PENALTY_UPDATE_RECOMMENDED**

## Required Updates to `synthesis_agent.md` Step 5
```
battle_grade == 'BROKE': current_adjustment=0 -> recommend 5 (drift_actual=+5.9pp, mean_actual_conf=74.1% vs WR=80.0%)  [NOTE: base-65 assumption invalid for BROKE — use actual-conf drift]
battle_grade == 'TESTED_MIXED': current_adjustment=0 -> recommend 20 (drift_actual=+20.9pp, mean_actual_conf=65.8% vs WR=86.7%)  [NOTE: base-65 assumption invalid for TESTED_MIXED — use actual-conf drift]
```

## Method
- Filtered `analysis/swarm-benchmark/aggregate.json` to tradeable days
  (direction_grade in CORRECT|WRONG).
- Grouped by battle_grade, computed observed WR per bucket.
- v5 implied confidence = 65 (typical base) + penalty.
- Drift = observed WR − v5 implied confidence.
- Penalty update recommended when |drift| > 5pp and bucket N ≥ 5.
- ECE = mean |avg_conf − WR| weighted by bin size (5 equal bins).
