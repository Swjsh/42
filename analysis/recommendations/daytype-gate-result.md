# Ex-ante day-type gate — JOB2 result

Pre-registration: `analysis\recommendations\prereg-daytype-gate-2026-07-15.json` (preflight ok=True). Cost: $0. Generated 2026-07-14T23:04:26.169791.

**Day coverage funnel:** 365 calendar days -> 236 with full 09:30-10:25 coverage -> 216 classifiable (>=20-day trailing baseline).

**Population (JOB1 honest OTM-2, entry>=10:30 ET):** 250 raw signals -> 32 dropped (before 10:30) -> 0 dropped (no local bars) -> **218 retained**. Pre-split battery: n=218 exp=$-35.07 WR=0.271.

## Variants

| variant | trend n | trend exp | chop n | chop exp | p_null | BH-survivor | anchor catch | verdict |
|---|--:|--:|--:|--:|--:|:--:|:--:|---|
| V1 | 29 | $-97.26 | 92 | $-24.22 | 0.8131 | N | 0.333 | **KILL** |
| V2 | 12 | $-250.87 | 109 | $-18.7 | 0.9935 | N | 0.0 | **KILL** |
| V3 | 48 | $-53.8 | 73 | $-33.79 | 0.5812 | N | 0.333 | **KILL** |

### V1

- trend: n=29 total=$-2820.4 exp=$-97.26 WR=0.241 OOS+=False stable=False drop3=$-221.62
- chop: n=92 total=$-2228.2 exp=$-24.22 WR=0.283 OOS+=False stable=False
- pooled: n=121 exp=$-41.72 | unclassifiable: n=97 exp=$-26.77
- null: n_trend_days=47/98, observed(trend-chop)=$-73.04, null_mean=$-1.71, p_null=0.8131, BH-survivor=False
- J-anchor: 1/3 caught (0.333) -- 2026-04-29=CHOP(missed); 2026-05-01=TREND(caught); 2026-05-04=CHOP(missed)
- conditions: {'1_direction_correct': False, '2_trend_bucket_positive': False, '3_bh_fdr_survivor': False, '4_trend_bucket_robust': False, '5_j_anchor_catch': False}
- **VERDICT: KILL** | chop_unrescuable_confirmation=True

### V2

- trend: n=12 total=$-3010.4 exp=$-250.87 WR=0.083 OOS+=False stable=False drop3=$-368.56
- chop: n=109 total=$-2038.2 exp=$-18.7 WR=0.294 OOS+=False stable=False
- pooled: n=121 exp=$-41.72 | unclassifiable: n=97 exp=$-26.77
- null: n_trend_days=24/98, observed(trend-chop)=$-232.17, null_mean=$-2.83, p_null=0.9935, BH-survivor=False
- J-anchor: 0/3 caught (0.0) -- 2026-04-29=CHOP(missed); 2026-05-01=CHOP(missed); 2026-05-04=CHOP(missed)
- conditions: {'1_direction_correct': False, '2_trend_bucket_positive': False, '3_bh_fdr_survivor': False, '4_trend_bucket_robust': False, '5_j_anchor_catch': False}
- **VERDICT: KILL** | chop_unrescuable_confirmation=True

### V3

- trend: n=48 total=$-2582.2 exp=$-53.8 WR=0.292 OOS+=False stable=False drop3=$-131.76
- chop: n=73 total=$-2466.4 exp=$-33.79 WR=0.26 OOS+=True stable=False
- pooled: n=121 exp=$-41.72 | unclassifiable: n=97 exp=$-26.77
- null: n_trend_days=78/98, observed(trend-chop)=$-20.01, null_mean=$-1.97, p_null=0.5812, BH-survivor=False
- J-anchor: 1/3 caught (0.333) -- 2026-04-29=CHOP(missed); 2026-05-01=TREND(caught); 2026-05-04=CHOP(missed)
- conditions: {'1_direction_correct': False, '2_trend_bucket_positive': False, '3_bh_fdr_survivor': False, '4_trend_bucket_robust': False, '5_j_anchor_catch': False}
- **VERDICT: KILL** | chop_unrescuable_confirmation=True

## Disclosures

- MEASURED (real OPRA local cache), not REALIZED -- scorecard/simulation-replay artifact; episode pnl is exactly JOB1's honest OTM-2 control replay, unmodified.
- entry_ts>=10:30 filter drops any signal firing in the first hour -- see population.counts.before_1030 for the exact count; this population is NOT the same as JOB1's full 250-signal OTM-2 cell and its own battery is reported (population.pre_split_battery) before any day-type split so the two are never conflated.
- day_classifiability requires FULL 12-bar 09:30-10:25 coverage (strict, no partial-window imputation) AND >=20 prior classifiable days for the trailing baseline -- see day_coverage for the funnel from raw calendar days to classifiable days.
- V1's condition is a strict superset of V3's (V1 = V3's range-expansion test AND the OR-hold confirmation) -- comparing V1 vs V3's pass/kill outcome directly answers whether the hold-confirmation leg adds anything beyond pure range expansion, not 3 independent guesses.
- shuffle_null preserves the REAL classifier's TREND-day COUNT (draws n_trend_days random days from the same classifiable-day universe) -- it tests whether THIS classifier's specific day selection beats a random subset of the same size, not whether trend days in general differ from chop days by construction.
- No re-tuning of K_RANGE/K_RVOL/K_LOC after seeing any result -- frozen in the pre-reg before this script was run; a KILL is not grounds to adjust and re-run under this study's own name (a materially different classifier design would be a new, separately pre-registered study).

---
_Source: `backtest/tools/daytype_gate_study.py`. A CANDIDATE_PASS is SPECIFIED, never auto-built or auto-wired -- still owes a J-visible REVOKE window per standing doctrine._
