# B8 — Generalize the 2-bar Entry Refinement to Dormant Edges #2 + #4 (Angle C)

- Run: 2026-06-21  |  Window: 2025-01-01..2026-05-15  |  Trading days: 342
- Fills: real OPRA via lib.simulator_real.simulate_trade_real (C1)
- OOS split: IS=2025 / OOS=2026
- Refinement: replace the first-trigger bar with a 2-bar WITH-TREND confirmation (reclaim-and-extend for #2; VWAP touch-and-resume for #4) — generalizes B7 S1 touch-and-go that lifted the LIVE #1
- Gate bar: 9-gate bar incl OOS-ALONE drop-top5 (L173) + random-null (L172) + no-trunc (L171) + NO-REGRESSION
- Edge#4 regime cut (fixed): {'slope_rule': 'not_rising', 'low_margin': 0.25, 'note': 'fixed at the B5 robust clearing cell; B8 isolates the entry refinement'}
- Tiers: {'ATM': 0, 'ITM2': -2}  |  premium_stop_pct: -0.08  |  qty: 3

## VERDICT ROLLUP

- **edge2_vwap_reclaim_failed_break** -> **DEAD**  (per-tier {'ATM': 'DEAD', 'ITM2': 'DEAD'})
- **edge4_vix_regime_dayside** -> **DEAD**  (per-tier {'ATM': 'DEAD', 'ITM2': 'DEAD'})

## edge2_vwap_reclaim_failed_break
- baseline fires: {'n_signals': 99, 'fire_day_pct': 28.9, 'side_count': {'C': 57, 'P': 42}}
- refined fires:  {'n_signals': 63, 'fire_day_pct': 18.4, 'side_count': {'C': 37, 'P': 26}}

| tier | variant | n | oos_n | OOS/tr | dropT5_OOS | dropT5_full | top5%_full | posQ | clears | fails |
|---|---|---|---|---|---|---|---|---|---|---|
| ATM | baseline | 93 | 22 | 16.58 | -26.34 | 15.52 | 53.6 | 5/6 | no | 9_oos_drop_top5_gt0 |
| ATM | refined | 58 | 12 | 31.1 | -35.01 | -0.02 | 100.1 | 5/6 | no | 5_drop_top5_full_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |
| ITM2 | baseline | 93 | 22 | 33.63 | -50.45 | 37.47 | 41.3 | 5/6 | no | 9_oos_drop_top5_gt0 |
| ITM2 | refined | 58 | 12 | 76.23 | -36.51 | 19.26 | 67.5 | 6/6 | no | 9_oos_drop_top5_gt0 |

| tier | OOS/tr lift (ref-base) | no-regression | dropped winner days | net removed $ | verdict |
|---|---|---|---|---|---|
| ATM | 14.52 | FAIL | 15 ($1413.0) | 752.52 | DEAD |
| ITM2 | 42.6 | FAIL | 14 ($2538.2) | 1205.96 | DEAD |

## edge4_vix_regime_dayside
- baseline fires: {'n_signals': 78, 'fire_day_pct': 22.8, 'side_count': {'C': 50, 'P': 28}}
- refined fires:  {'n_signals': 51, 'fire_day_pct': 14.9, 'side_count': {'C': 33, 'P': 18}}

| tier | variant | n | oos_n | OOS/tr | dropT5_OOS | dropT5_full | top5%_full | posQ | clears | fails |
|---|---|---|---|---|---|---|---|---|---|---|
| ATM | baseline | 74 | 19 | 75.65 | 10.75 | 19.83 | 52.6 | 5/6 | YES | - |
| ATM | refined | 49 | 12 | 62.86 | -38.13 | 1.43 | 95.8 | 4/6 | no | 9_oos_drop_top5_gt0 |
| ITM2 | baseline | 74 | 19 | 125.83 | 27.05 | 32.44 | 48.9 | 5/6 | YES | - |
| ITM2 | refined | 49 | 12 | 81.5 | -46.58 | 22.19 | 66.9 | 4/6 | no | 9_oos_drop_top5_gt0 |

| tier | OOS/tr lift (ref-base) | no-regression | dropped winner days | net removed $ | verdict |
|---|---|---|---|---|---|
| ATM | -12.79 | FAIL | 8 ($998.2) | 369.16 | DEAD |
| ITM2 | -44.33 | FAIL | 9 ($2215.8) | 1165.56 | DEAD |

## Disclosure
- Per-trade EXPECTANCY reported, not WR alone (OP-14).
- IS=2025 AND OOS=2026; gate 9 (OOS-ALONE drop-top5) is the decisive de-concentration gate (L173).
- Random-entry null (L172) + no-truncation (L171) via fraud_gates.verify_candidate on the REFINED variant.
- NO-REGRESSION: the refinement may only drop net-negative/neutral DAYS; dropping any net-winning day FAILS.
- Both validated tiers reported (ATM Safe-2 + ITM-2 Bold); C29 — knobs do not transfer across tiers.
- Edge#4 regime cut held FIXED (B5 robust cell) so B8 isolates the entry-refinement effect.
- Real OPRA fills; SPY-direction != option edge (C3/L58); WR is a theta trap (OP-14).
- LIVE_EDGE_IMPROVEMENT iff refined lifts OOS per-trade AND clears all 9 gates AND passes no-regression.
