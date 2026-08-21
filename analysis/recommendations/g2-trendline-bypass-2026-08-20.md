# G2-TRENDLINE-BYPASS-INVERTS-PRIORITY -- A/B (2026-08-01)

Generated 2026-08-20T18:58:49.783642. Runner: `backtest/tools/g2_trendline_bypass_ab_2026_08_01.py`. Pre-reg: `analysis/recommendations/prereg-g2-trendline-bypass-2026-08-01.json`.

CONTROL: 227 raw entries (184 bear), 167 real-OPRA bear walks, total $+5,480.25.
Recent window: 2026-07-17..2026-08-20 (25 days).

## Arms

| arm | scope | full delta | recent delta | G1 | G2 | G3 | G4 | G5 | verdict |
|---|---|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|
| ARM_EXTEND | all_level_tied | $+78.15 | $-561.55 | UNDETERMINED | FAIL | FAIL | PASS | PASS | **NULL** |
| ARM_REMOVE | none | $-984.70 | $-1,498.10 | FAIL | FAIL | FAIL | FAIL | PASS | **NULL** |

## FINAL VERDICT: **NEITHER_SHIPS_STAYS_TRENDLINE_ONLY**

Neither arm clears all 5 gates. `trendline_bypass_scope` stays at the CONTROL default (`'trendline_only'`) -- the G2 finding is CONFIRMED as a real asymmetry but NOT acted on without evidence clearing the bar.

### ARM_EXTEND detail

Full: n_added=369 n_dropped=113 added_stats={'n': 369, 'total': 1240.05, 'wr': 0.3686, 'per_trade': 3.36, 'total_ex_best': 135.75, 'n_days': 232}
Recent25: n_added=30 n_dropped=13 days_improved=8 days_worsened=10
Runner-cohort anchor: control={'n': 23, 'total': 10609.15} arm={'n': 42, 'total': 23654.9}
Added exit-reason mix: {'structure_stop': {'n': 168, 'pct': 45.5}, 'ribbon_flip_back': {'n': 120, 'pct': 32.5}, 'premium_stop': {'n': 49, 'pct': 13.3}, 'runner_stop': {'n': 30, 'pct': 8.1}, 'time_stop_15:40': {'n': 1, 'pct': 0.3}, 'time_stop_15:40 (runner)': {'n': 1, 'pct': 0.3}}
OPRA recent25 zero-coverage days: {'n': 1, 'days': ['2026-08-20']}

### ARM_REMOVE detail

Full: n_added=6 n_dropped=134 added_stats={'n': 6, 'total': 823.3, 'wr': 0.5, 'per_trade': 137.22, 'total_ex_best': 320.05, 'n_days': 6}
Recent25: n_added=1 n_dropped=14 days_improved=5 days_worsened=5
Runner-cohort anchor: control={'n': 23, 'total': 10609.15} arm={'n': 12, 'total': 6659.75}
Added exit-reason mix: {'premium_stop': {'n': 4, 'pct': 66.7}, 'runner_stop': {'n': 2, 'pct': 33.3}}
OPRA recent25 zero-coverage days: {'n': 1, 'days': ['2026-08-20']}

## Reconciliation

Disjoint mechanism/question from filter5-ribbon-2026-07-31.json (that study asks whether filter 5 itself should exist at all, both directions; this study asks whether the EXISTING bear-side trendline-only relaxation of filters 5/8/9 should be extended or removed). Same population/harness/OPRA-coverage gap inherited.

---
_Source: `backtest/tools/g2_trendline_bypass_ab_2026_08_01.py`. Full per-trade detail in the companion `.json`._
