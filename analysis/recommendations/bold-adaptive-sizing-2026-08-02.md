# BOLD-ADAPTIVE-SIZING-TRY5-FALLBACK3 -- TRUE sequential replay, 2026-08-02

Generated 2026-08-02T00:54:11.390308. Runner: `backtest/tools/bold_adaptive_sizing_2026_08_02.py`.
Prereg (frozen first): `analysis\recommendations\prereg-bold-adaptive-sizing-2026-08-02.json` (2026-08-02T02:37:25-04:00).
Account: core_bold (Gamma-Bold-2, PA33W2KUAT40). Equity: $1,197.52. Window: 2025-01-02..2026-07-22. Gate state held fixed: block_elite_bull=True (current live).

## VERDICT: NULL

| Gate | Result |
|---|---|
| G1_recent25_positive_PRIMARY | PASS |
| G2_day_majority | FAIL |
| G3_drop_best_still_positive | PASS |
| G4_pnl_not_degraded_vs_both_baselines | PASS |
| G5_runner_cohort_ZERO_TOLERANCE | FAIL |
| G6_rule6_floor_respected | PASS |
| G7_kill_switch_and_risk_cap_guard_present | PASS |
| G8_not_a_dead_knob_C14 | PASS |
| G9_gain_is_not_mostly_preemption | PASS |

## Derived (naive union) vs honest replayed -- THE GAP

- Derived, exact-by-construction union (shipped in min-contracts-bold-2026-08-02.json, NOT sequential): n=286 total=$+10,528.60 recent25=$+470.25
- Reproduced fresh this session (parity check, one direct adaptive-mode pass, pre-sequential): 286 total=$+10,528.60 -- PARITY_OK=True
- **HONEST, sequentially-replayed (one position at a time)**: n=273 total=$+10,473.20
- **GAP**: $+55.40 (0.5% of the derived figure), 13 candidate trade(s) pre-empted. Mechanism: trades pre-empted because an earlier adaptive-only (fallback qty=3) trade's exit_time_et had not yet passed when this signal arrived -- the position slot was occupied.

## Control, also re-walked sequentially (apples-to-apples)

| | CONTROL_SEQUENTIAL (floor=5 only) | ADAPTIVE_SEQUENTIAL (try5/fallback3) |
|---|---|---|
| n | 153 | 273 |
| Total P&L | $+7,578.40 | $+10,473.20 |
| vs shipped CONTROL_RAW $+7,448.40 | -- | >= |
| Win rate | 0.3399 | 0.3333 |
| Avg $/trade | $+49.53 | $+38.36 |
| Drop-best remainder | $+6,583.40 (still +) | $+9,478.20 (still +) |
| Recent-25 total (PRIMARY gate) | $+2,841.40 | $+715.25 |

## Day-majority (G2, novel term, defined fresh in the prereg)

up_days=82 down_days=119 neutral_days=0 of n_days=201 -- **PASS=False**

(informational, NOT gated -- context for whether this is adaptive-specific or a pre-existing shape of the trade population) CONTROL_SEQUENTIAL day-majority: up=48 down=69 pass=False -- same shape as adaptive (few big winners, many small losing days -- a baseline strategy feature, not something the adaptive rule introduced)

## Bold's OWN runner cohort (G5, zero-tolerance)

n=32 (expected 32, crosscheck_ok=True) CONTROL total=$+14,539.40 (expected $+14,539.40) ADAPTIVE_SEQUENTIAL total=$+13,493.00 missing=2 flips=0 -- **PASS=False**

## Decomposition: added vs pre-empted (task step 3)

- ADDED cohort (only possible via the qty=3 fallback): n=130 total=$+3,080.20
- PRE-EMPTED cohort (current engine's own sequential trades displaced by an earlier fallback trade): n=10 total=$+185.40
- gain_over_control_sequential=$+2,894.80, identity_holds=True, pct_of_gain_from_preemption=-6.4

## Participation / fire counts (L243 discipline)

```
{
  "n_raw_signals": 334,
  "n_excluded_no_opra_cache": 18,
  "n_excluded_no_spy_day": 0,
  "control_n_excluded_risk_cap_deadlock": 160,
  "adaptive_n_excluded_risk_cap_deadlock_both_tiers": 30,
  "control_n_candidate": 156,
  "adaptive_n_candidate": 286,
  "adaptive_n_candidate_preferred_tier_qty5": 156,
  "adaptive_n_candidate_fallback_tier_qty3": 130,
  "adaptive_n_actually_placed_post_sequential": 273,
  "adaptive_n_fallback_actually_placed": 130
}
```

---
_Source: `backtest/tools/bold_adaptive_sizing_2026_08_02.py`. Raw JSON: `analysis/recommendations/bold-adaptive-sizing-2026-08-02.json`._
