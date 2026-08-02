# min_contracts (Bold) A/B -- 2026-08-02

Generated 2026-08-02T00:20:21.397125. Runner: `backtest/tools/min_contracts_bold_ab_2026_08_02.py`.
Prereg (frozen first): `analysis\recommendations\prereg-min-contracts-bold-2026-08-02.json` (2026-08-02T02:06:26-04:00).
Account: core_bold (Gamma-Bold-2, PA33W2KUAT40). Equity: $1,197.52 (live-verified 2026-08-02). Window: 2025-01-02..2026-07-22. Gate state held fixed: block_elite_bull=True (current live).

## VERDICT: NULL

| Gate | Result |
|---|---|
| G1_participation_up_ge_15pct | PASS |
| G2_pnl_not_degraded | FAIL |
| G3_runner_cohort_zero_tolerance | FAIL |
| G4_rule6_floor_respected | PASS |
| G5_risk_reduced | PASS |
| G6_kill_switch_cap_guard_present | PASS |

## Participation (primary metric)

- Raw signal entries (identical, same gate state): 334
- CONTROL (floor=5) excluded by risk-cap deadlock: 160
- VARIANT (floor=3) excluded by risk-cap deadlock: 30
- CONTROL replayed (placeable): 156
- VARIANT replayed (placeable): 286
- **Delta: +130 trades (83.3%)**
- Monotonic superset check: {'is_strict_superset': True, 'n_control_trades_missing_from_variant': 0}

## P&L / WR / per-trade

| | CONTROL (floor=5) | VARIANT (floor=3) |
|---|---|---|
| n | 156 | 286 |
| Total P&L | $+7,448.40 | $+7,367.40 |
| Win rate | 0.3333 | 0.3287 |
| Avg $/trade | $+47.75 | $+25.76 |
| Drop-best remainder | $+6,453.40 (still +) | $+6,608.40 (still +) |
| Recent-25 total | $+2,864.40 (n=25, 2026-05-07..2026-07-21) | $-105.75 (n=25, 2026-06-22..2026-07-21) |
| Avg notional/trade | $428.85 | $345.63 |
| Max notional/trade | $595.00 | $591.00 |

## Bold's OWN runner cohort (zero-tolerance check, task step 4)

n=32 CONTROL total=$+14,539.40 VARIANT total=$+8,630.20 delta=$-5,909.20 winner-to-loser flips=0 missing-in-variant=0 -- **PASS=False**

## EXPLORATORY (not gated, NOT shipped tonight): adaptive try-5-fallback-3

n=286 total=$+10,528.60 WR=0.3287 avg=$+36.81 recent25=$+470.25 drop-best remainder=$+9,533.60 (still +)

vs CONTROL (floor=5 only) n=156 total=$+7,448.40, and pure VARIANT (floor=3 only) n=286 total=$+7,367.40. Blocked by: setup/scripts/heartbeat_core.py:1964 is on tonight's DO-NOT-TOUCH list.

> Task-cited '35 winners / +$15,774' disclosure: exit_armscope_ab_2026_07_28.py ANCHOR_RUNNER_N=35 / ANCHOR_RUNNER_PNL=15774.05 -- SAFE's ribbon_ride runner cohort (automation/state/params.json population). Reachable by this change: False (this study edits ONLY automation/state/aggressive/params.json; Safe's params.json / engine / fills are structurally untouched).

---
_Source: `backtest/tools/min_contracts_bold_ab_2026_08_02.py`. Raw JSON: `analysis/recommendations/min-contracts-bold-2026-08-02.json`._
