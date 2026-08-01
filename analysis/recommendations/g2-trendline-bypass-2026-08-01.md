# G2-TRENDLINE-BYPASS-INVERTS-PRIORITY -- A/B (2026-08-01)

Generated 2026-08-01T02:21:20.039966. Runner: `backtest/tools/g2_trendline_bypass_ab_2026_08_01.py`. Pre-reg: `analysis/recommendations/prereg-g2-trendline-bypass-2026-08-01.json`.

CONTROL: 211 raw entries (172 bear), 152 real-OPRA bear walks, total $+2,670.55.
Recent window: 2026-06-26..2026-07-31 (25 days).

## Arms

| arm | scope | full delta | recent delta | G1 | G2 | G3 | G4 | G5 | verdict |
|---|---|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|
| ARM_EXTEND | all_level_tied | $-2,061.65 | $+1,616.15 | UNDETERMINED | PASS | PASS | PASS | PASS | **NULL** |
| ARM_REMOVE | none | $+2,693.55 | $+279.60 | UNDETERMINED | PASS | PASS | FAIL | PASS | **NULL** |

## FINAL VERDICT: **NEITHER_SHIPS_STAYS_TRENDLINE_ONLY**

Neither arm clears all 5 gates. `trendline_bypass_scope` stays at the CONTROL default (`'trendline_only'`) -- the G2 finding is CONFIRMED as a real asymmetry but NOT acted on without evidence clearing the bar.

### ARM_EXTEND detail

Full: n_added=343 n_dropped=102 added_stats={'n': 343, 'total': -3573.1, 'wr': 0.2915, 'per_trade': -10.42, 'total_ex_best': -4677.4, 'n_days': 218}
Recent25: n_added=18 n_dropped=7 days_improved=8 days_worsened=6
Runner-cohort anchor: control={'n': 28, 'total': 12478.65} arm={'n': 57, 'total': 31262.8}
Added exit-reason mix: {'structure_stop': {'n': 171, 'pct': 49.9}, 'ribbon_flip_back': {'n': 114, 'pct': 33.2}, 'runner_stop': {'n': 40, 'pct': 11.7}, 'premium_stop': {'n': 11, 'pct': 3.2}, 'time_stop_15:50': {'n': 5, 'pct': 1.5}, 'time_stop_15:50 (runner)': {'n': 2, 'pct': 0.6}}
OPRA recent25 zero-coverage days: {'n': 3, 'days': ['2026-07-24', '2026-07-27', '2026-07-30']}

### ARM_REMOVE detail

Full: n_added=5 n_dropped=122 added_stats={'n': 5, 'total': 614.8, 'wr': 0.4, 'per_trade': 122.96, 'total_ex_best': 111.55, 'n_days': 5}
Recent25: n_added=0 n_dropped=6 days_improved=5 days_worsened=1
Runner-cohort anchor: control={'n': 28, 'total': 12478.65} arm={'n': 16, 'total': 8285.8}
Added exit-reason mix: {'premium_stop': {'n': 3, 'pct': 60.0}, 'runner_stop': {'n': 2, 'pct': 40.0}}
OPRA recent25 zero-coverage days: {'n': 3, 'days': ['2026-07-24', '2026-07-27', '2026-07-30']}

## Reconciliation

Disjoint mechanism/question from filter5-ribbon-2026-07-31.json (that study asks whether filter 5 itself should exist at all, both directions; this study asks whether the EXISTING bear-side trendline-only relaxation of filters 5/8/9 should be extended or removed). Same population/harness/OPRA-coverage gap inherited.

---
_Source: `backtest/tools/g2_trendline_bypass_ab_2026_08_01.py`. Full per-trade detail in the companion `.json`._
