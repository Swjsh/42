# B8 — Anchored-VWAP Structural Setups (Angle A) — Scorecard

- Run: 2026-06-21  |  Window: 2025-01-01..2026-05-15  |  Trading days: 342
- Fills: real OPRA via lib.simulator_real.simulate_trade_real (C1)
- OOS split: IS=2025 / OOS=2026
- Anchors: A1=PDL-anchored aVWAP, A2=PDH-anchored aVWAP, A3=prior-swing-anchored aVWAP
- Gate bar: 9-gate bar incl OOS-ALONE drop-top5 (L173) + random-null (L172) + no-trunc (L171) + independence-vs-#1
- Independence: day-overlap vs LIVE #1 vwap_continuation; EDGE requires overlap<=0.8  (LIVE #1 fires on 158 days)
- Tiers: {'ATM': 0, 'ITM2': -2}  |  premium_stop_pct: -0.08  |  qty: 3

## VERDICT: 0 cell(s) clear ALL 9 gates AND are independent of #1

- **NONE** — no cell clears all 9 gates while staying independent of the live #1. Anchored-VWAP variants either die on theta (C3/L58: SPY-price edge != option edge; WR is a theta trap, OP-14) or simply re-detect the same days the shipped session-VWAP continuation already trades.
- NOTE: 1 cell(s) cleared all 9 gates but were blocked by >80% day-overlap with the live #1 (not materially independent).

## A1_reclaim_pdl_avwap
- signals=4  fires 1.2% of days  side={'C': 4, 'P': 0}
- overlap vs LIVE #1: 0.75 (3 shared days)  => independent=True

| tier | side | n | OOS/tr | dropT5_full | dropT5_OOS | top5%_full | posQ | null | notrunc | gates | indep | EDGE | fails |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ATM | BOTH | 4 | -33.6 | None | None | 100.0 | 2/3 | False | True | no | YES | no | 1_oos_pt_gt0,2_pos_q_ge4of6,4_n_ge20,5_drop_top5_full_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |
| ATM | C | 4 | -33.6 | None | None | 100.0 | 2/3 | False | True | no | YES | no | 1_oos_pt_gt0,2_pos_q_ge4of6,4_n_ge20,5_drop_top5_full_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |
| ATM | P | 0 | None | None | None | None | 0/0 | None | None | no | YES | no | no_fills |
| ITM2 | BOTH | 4 | -58.08 | None | None | 100.0 | 2/3 | False | True | no | YES | no | 1_oos_pt_gt0,2_pos_q_ge4of6,4_n_ge20,5_drop_top5_full_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |
| ITM2 | C | 4 | -58.08 | None | None | 100.0 | 2/3 | False | True | no | YES | no | 1_oos_pt_gt0,2_pos_q_ge4of6,4_n_ge20,5_drop_top5_full_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |
| ITM2 | P | 0 | None | None | None | None | 0/0 | None | None | no | YES | no | no_fills |

## A2_reject_pdh_avwap
- signals=12  fires 3.5% of days  side={'C': 0, 'P': 12}
- overlap vs LIVE #1: 1.0 (12 shared days)  => independent=False

| tier | side | n | OOS/tr | dropT5_full | dropT5_OOS | top5%_full | posQ | null | notrunc | gates | indep | EDGE | fails |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ATM | BOTH | 11 | -40.92 | -48.12 | None | None | 0/5 | False | True | no | no | no | 1_oos_pt_gt0,2_pos_q_ge4of6,3_top5_full_lt200,4_n_ge20,5_drop_top5_full_gt0,6_is_first_half_pt_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |
| ATM | C | 0 | None | None | None | None | 0/0 | None | None | no | no | no | no_fills |
| ATM | P | 11 | -40.92 | -48.12 | None | None | 0/5 | False | True | no | no | no | 1_oos_pt_gt0,2_pos_q_ge4of6,3_top5_full_lt200,4_n_ge20,5_drop_top5_full_gt0,6_is_first_half_pt_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |
| ITM2 | BOTH | 11 | -5.61 | -64.8 | None | None | 2/5 | False | True | no | no | no | 1_oos_pt_gt0,2_pos_q_ge4of6,3_top5_full_lt200,4_n_ge20,5_drop_top5_full_gt0,6_is_first_half_pt_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |
| ITM2 | C | 0 | None | None | None | None | 0/0 | None | None | no | no | no | no_fills |
| ITM2 | P | 11 | -5.61 | -64.8 | None | None | 2/5 | False | True | no | no | no | 1_oos_pt_gt0,2_pos_q_ge4of6,3_top5_full_lt200,4_n_ge20,5_drop_top5_full_gt0,6_is_first_half_pt_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |

## A3_swing_avwap_retest
- signals=147  fires 43.0% of days  side={'C': 83, 'P': 64}
- overlap vs LIVE #1: 0.973 (143 shared days)  => independent=False

| tier | side | n | OOS/tr | dropT5_full | dropT5_OOS | top5%_full | posQ | null | notrunc | gates | indep | EDGE | fails |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ATM | BOTH | 141 | 22.46 | 2.14 | -7.02 | 86.9 | 5/6 | False | True | no | no | no | 7_beats_random_null,9_oos_drop_top5_gt0 |
| ATM | C | 80 | 29.13 | -0.44 | -17.89 | 102.1 | 6/6 | False | False | no | no | no | 5_drop_top5_full_gt0,7_beats_random_null,8_no_truncation,9_oos_drop_top5_gt0 |
| ATM | P | 61 | 12.45 | -7.71 | -30.33 | 166.9 | 3/6 | False | True | no | no | no | 2_pos_q_ge4of6,5_drop_top5_full_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |
| ITM2 | BOTH | 140 | 59.23 | 20.94 | 15.59 | 43.2 | 6/6 | True | True | YES | no | no | overlap_vs_#1=0.973>0.8 |
| ITM2 | C | 80 | 73.66 | 27.7 | -2.92 | 50.9 | 6/6 | True | True | no | no | no | 9_oos_drop_top5_gt0 |
| ITM2 | P | 60 | 37.58 | -8.37 | -26.56 | 161.5 | 3/6 | True | True | no | no | no | 2_pos_q_ge4of6,5_drop_top5_full_gt0,6_is_first_half_pt_gt0,9_oos_drop_top5_gt0 |

## Disclosure
- Per-trade EXPECTANCY reported, not WR alone (OP-14).
- IS=2025 AND OOS=2026; gate 9 (OOS-ALONE drop-top5) is the decisive de-concentration gate (L173).
- Random-entry null (L172) + no-truncation (L171) via fraud_gates.verify_candidate.
- aVWAP is causal: re-anchored cumulative TP*vol accumulated FORWARD from the anchor bar only.
- Independence vs LIVE #1 (vwap_continuation) by entry-DAY overlap; EDGE requires <=80% overlap.
- Both tiers (ATM Safe-2 + ITM-2 Bold, C29) + both sides reported, no survivor cherry-pick (2.10).
- Real OPRA fills; SPY-direction != option edge (C3/L58).
