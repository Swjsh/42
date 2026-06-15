# ORB Gate Analysis — Direction + OR-Range Gates
> Generated: 2026-05-21 00:48 ET
> Source: 391 graded ORB observations (watcher-observations.jsonl)

## Scenarios

| Scenario | N | WR% | P&L | Positive Qtrs |
|---|---:|---:|---:|---:|
| **ALL** | 391 | 61.9% | $7,161 | 2/2 |
| **LONG_ONLY** | 274 | 69.3% | $7,378 | 2/2 |
| **NARROW_OR** | 218 | 73.4% | $5,084 | 1/2 |
| **NARROW_OR_LONG** | 143 | 88.1% | $4,597 | 2/2 |

## Per-Quarter Breakdown

### ALL: ALL (baseline — 391 obs)

| Quarter | N | WR% | P&L |
|---|---:|---:|---:|
| 2025-Q4 | 22 | 36.4% | +$0 |
| unknown | 369 | 63.4% | +$7,161 |

### LONG_ONLY: LONG_ONLY — direction==long (274 obs)

| Quarter | N | WR% | P&L |
|---|---:|---:|---:|
| 2025-Q4 | 14 | 57.1% | +$169 |
| unknown | 260 | 70.0% | +$7,209 |

### NARROW_OR: NARROW_OR — or_range<=2.0 (218 obs)

| Quarter | N | WR% | P&L |
|---|---:|---:|---:|
| 2025-Q4 | 13 | 38.5% | $-99 |
| unknown | 205 | 75.6% | +$5,183 |

### NARROW_OR_LONG: NARROW_OR_LONG — or_range<=2.0 AND long (143 obs)

| Quarter | N | WR% | P&L |
|---|---:|---:|---:|
| 2025-Q4 | 5 | 100.0% | +$70 |
| unknown | 138 | 87.7% | +$4,527 |

## OR-Range Distribution
- Min: 0.51
- Max: 4.33
- Mean: 2.007
- % observations with OR-range ≤ 2.00: 55.8%

## Outcome Breakdowns

### ALL
| Outcome | N | P&L |
|---|---:|---:|
| stopped | 134 | $-7,136 |
| tp1_then_be_stop | 134 | $2,343 |
| runner_hit | 120 | $11,795 |
| tp1_partial_open | 3 | $159 |

### LONG_ONLY
| Outcome | N | P&L |
|---|---:|---:|
| tp1_then_be_stop | 110 | $1,883 |
| stopped | 81 | $-4,144 |
| runner_hit | 80 | $9,481 |
| tp1_partial_open | 3 | $159 |

### NARROW_OR
| Outcome | N | P&L |
|---|---:|---:|
| tp1_then_be_stop | 89 | $1,127 |
| runner_hit | 83 | $6,195 |
| stopped | 46 | $-2,238 |

### NARROW_OR_LONG
| Outcome | N | P&L |
|---|---:|---:|
| tp1_then_be_stop | 80 | $1,057 |
| runner_hit | 49 | $4,228 |
| stopped | 14 | $-688 |