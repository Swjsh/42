# Regime stand-down study -- REGIME-STANDDOWN-EARLY-CLASSIFIER-2026-08-02

Generated 2026-08-02T00:21:05.565066. Runner: `backtest/tools/regime_standdown_study.py`. Prereg: `analysis/recommendations/prereg-regime-standdown-2026-08-02.json (commit 60e1dcc8)`.

## VERDICT: NOT LIVE-EXECUTABLE with the current early-classifier methodology -- confirms the prereg's stated prior. Filed as a real, dated null result.

- ARM_1 (10:00 cutoff, primary) ships: **False**
- ARM_1B (09:45 cutoff, secondary) ships: **False**

## Scope

- 191 total trades in engine-fullhist-replay-2026-07-23.json
- 161 in-scope (both cutoffs have honest out-of-fold predictions)
- 30 excluded (21 dates, walk-forward seed window, no honest OOF prediction -- dropped from both arms identically)

## ARM_1_STANDDOWN_10AM

| Metric | Value |
|---|---|
| Control total P&L (in-scope) | $+5,376.30 (161 trades) |
| ARM total P&L (after stand-down) | $+5,397.00 (109 trades) |
| Removed (skipped) total P&L | $-20.70 (52 trades, 39 days) |
| Full-population delta | $+20.70 |
| Drop-best-day (kept book) | $+3,931.90 (still positive: True) |
| Recent-25-day window delta | $-632.95 |
| Removed-trades one-sided p (mean<0) | 0.4953 |

### Removed trades by TRUE archetype (hindsight label)

| Archetype | N trades | N days | Total $ removed |
|---|---:|---:|---:|
| gap-fade | 13 | 8 | $-733.90 |
| range-chop | 22 | 17 | $+683.55 |
| gap-go | 13 | 10 | $+163.85 |
| V-reversal | 3 | 3 | $-83.20 |
| pin-day | 1 | 1 | $-51.00 |

**gap-go specifically: 13 trades / 10 days removed, $+163.85** -- this is the book's single largest archetype (60.5% of ALL P&L per THE FINDING); any material removal here is a direct hit on the profit engine, not a side effect.

### Gates

| Gate | Pass | Detail |
|---|:---:|---|
| G1 recent-window positive (PRIMARY) | False | delta=$-632.95 |
| G2 day-majority | False | improved=4 worsened=6 |
| G3 survives worst-single-dodge | False | value=$-1,211.95 |
| G4 runner-cohort no-regression (ZERO tolerance) | False | kept 72.6% of control $ (22/32 trades), removed $+3,934.70 of runner P&L |
| G5 meaningful participation change | True | removed 52 trades / 39 days |
| **SHIPS (all gates)** | **False** | |

## ARM_1B_STANDDOWN_0945

| Metric | Value |
|---|---|
| Control total P&L (in-scope) | $+5,376.30 (161 trades) |
| ARM total P&L (after stand-down) | $+2,778.20 (79 trades) |
| Removed (skipped) total P&L | $+2,598.10 (82 trades, 57 days) |
| Full-population delta | $-2,598.10 |
| Drop-best-day (kept book) | $+1,313.10 (still positive: True) |
| Recent-25-day window delta | $-967.50 |
| Removed-trades one-sided p (mean<0) | 0.8648 |

### Removed trades by TRUE archetype (hindsight label)

| Archetype | N trades | N days | Total $ removed |
|---|---:|---:|---:|
| gap-go | 24 | 18 | $+2,218.70 |
| trend-up | 1 | 1 | $+752.00 |
| gap-fade | 17 | 11 | $+557.05 |
| range-chop | 31 | 21 | $-469.85 |
| V-reversal | 6 | 4 | $-270.80 |
| pin-day | 3 | 2 | $-189.00 |

**gap-go specifically: 24 trades / 18 days removed, $+2,218.70** -- this is the book's single largest archetype (60.5% of ALL P&L per THE FINDING); any material removal here is a direct hit on the profit engine, not a side effect.

### Gates

| Gate | Pass | Detail |
|---|:---:|---|
| G1 recent-window positive (PRIMARY) | False | delta=$-967.50 |
| G2 day-majority | False | improved=4 worsened=4 |
| G3 survives worst-single-dodge | False | value=$-1,546.50 |
| G4 runner-cohort no-regression (ZERO tolerance) | False | kept 52.6% of control $ (16/32 trades), removed $+6,799.70 of runner P&L |
| G5 meaningful participation change | True | removed 82 trades / 57 days |
| **SHIPS (all gates)** | **False** | |

## BH-FDR (advisory)

alpha=0.1, n_cells=2, survivors=[]

---
_Source: `backtest/tools/regime_standdown_study.py`. Raw JSON: `analysis/recommendations/regime-standdown-2026-08-02.json`._
