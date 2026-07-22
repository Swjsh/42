# QQQ divergence/confluence -- first-pass information test

Generated 2026-07-21T18:50:32.409639. Verdict: **QQQ_AGREEMENT_INFORMATIVE**.

## Method (disclosed proxy, NOT a real-fills P&L study)
- QQQ own-level window: 20 bars
- Forward horizon: 30 min
- Outcome metric: direction-aligned SPY spot return over forward_horizon_minutes from signal entry_ts (NOT a $ P&L, NOT a real fill -- MODELED spot-return information-test proxy, disclosed per OP-20)

## Signal cohort
- 250 total signals (2025-01-01..2026-06-18), 250 usable (0 dropped for missing QQQ/SPY bars)

## Strata by QQQ label
- **reclaimed** (n=21): mean aligned return=1.0833, median=0.77, %positive=81.0%, n=21 >= 10: sample sufficient
- **failed** (n=27): mean aligned return=0.5455, median=0.69, %positive=70.4%, n=27 >= 10: sample sufficient
- **none** (n=202): mean aligned return=0.0662, median=-0.0175, %positive=48.5%, n=202 >= 10: sample sufficient

## Reclaimed vs other mean spread: 0.9606

## By direction
{
  "bull": {
    "n": 59,
    "n_reclaimed": 8,
    "n_failed": 12,
    "n_none": 39
  },
  "bear": {
    "n": 191,
    "n_reclaimed": 13,
    "n_failed": 15,
    "n_none": 163
  }
}

## Next step
If verdict == QQQ_AGREEMENT_INFORMATIVE: fund the full real-fills replay (ribbon_ride_strike_exit_ab.py-class per-strike OPRA replay, stratified by qqq_label) before any wiring proposal. If NO_SIGNAL or INVERSE: do not fund the expensive replay; close the chef-inbox item as explored-and-not-promising.