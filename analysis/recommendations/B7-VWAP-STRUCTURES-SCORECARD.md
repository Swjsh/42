# B7 — New VWAP-Native Structural Shapes (Angle A) — Scorecard

- Run: 2026-06-21  |  Window: 2025-01-01..2026-05-15  |  Trading days: 342
- Fills: real OPRA via lib.simulator_real.simulate_trade_real (C1)
- OOS split: IS=2025 / OOS=2026
- Gate bar: 9-gate bar incl OOS-ALONE drop-top5 (L173) + random-null (L172) + no-trunc (L171)
- Tiers: {'ATM': 0, 'ITM2': -2}  |  premium_stop_pct: -0.08  |  qty: 3

## HONESTY CHECK — these are NOT 3 independent new edges (overlap with LIVE #1)

The 9-gate pass is real, but the call-day overlap with the ALREADY-LIVE #1
vwap_continuation (the shipped Bold ITM-2 call edge) is decisive:

| shape | C-days | overlap w/ LIVE #1 | unique C-days |
|---|---|---|---|
| S1 vwap_touch_and_go | 68 | **67 (99%)** | 1 |
| S2 vwap_band_ride | 80 | **79 (99%)** | 1 |
| S3 vwap_opening_drive | 88 | 66 (75%) | 22 |

S1 and S2 trade ~the SAME days as #1 — they are the SAME edge re-detected with a
different trigger label, NOT new edges. S3 is more differentiated (75% overlap).

Bull-drift artifact REJECTED (C3/L58): the call-side random-entry null mean is flat
($-2.2 to +$1.2/tr) — a coin-flip call entry in this 2025-26 tape does NOT print money,
and every chosen cell beats the null MAX (not just the mean). So the call edge is the
STRUCTURE, not the tape. Every PUT cell fails gate 9 (OOS-alone drop-top5 negative) —
the put side is the bull-tape casualty, correctly rejected.

## APPLES-TO-APPLES vs the LIVE #1 baseline (same harness, same window)

LIVE #1 vwap_continuation on this identical harness:
- ITM2-C: n=82, OOS/tr $120.11, OOS-drop-top5 $37.98, posQ 6/6
- ITM2-BOTH: n=149, OOS/tr $94.84, OOS-drop-top5 $49.25, posQ 6/6
- ATM-C: n=82, OOS/tr $72.55, OOS-drop-top5 $13.04

The ONLY cell that BEATS the live engine:
- **S1 vwap_touch_and_go ITM2-C — OOS/tr $178.32 (vs #1 $120) and OOS-drop-top5 $82.01
  (vs #1 $38, +2.2x).** A tighter ENTRY (touch-VWAP + next-bar resume past the touch
  extreme) on the same edge. S2/S3 ITM2-C (~$118/tr) are flat-to-#1 → no improvement.

**VERDICT: LIVE_EDGE_IMPROVEMENT** — not a fresh independent edge. The touch-and-go
two-bar confirmation is a better entry trigger for the already-shipped vwap_continuation
(Bold/ITM-2/call), improving OOS expectancy and de-concentration. S2/S3 add nothing
over #1.

## RAW 9-GATE RESULTS (all cells, no cherry-pick)

### 11 cell(s) clear ALL 9 gates

- **EDGE** S1_vwap_touch_and_go / ATM / BOTH — OOS/tr $53.21, OOS-drop-top5 $17.91
- **EDGE** S1_vwap_touch_and_go / ATM / C — OOS/tr $78.81, OOS-drop-top5 $23.32
- **EDGE** S1_vwap_touch_and_go / ITM2 / BOTH — OOS/tr $103.13, OOS-drop-top5 $39.26
- **EDGE** S1_vwap_touch_and_go / ITM2 / C — OOS/tr $178.32, OOS-drop-top5 $82.01
- **EDGE** S2_vwap_band_ride / ATM / BOTH — OOS/tr $40.21, OOS-drop-top5 $4.68
- **EDGE** S2_vwap_band_ride / ATM / C — OOS/tr $64.43, OOS-drop-top5 $4.67
- **EDGE** S2_vwap_band_ride / ITM2 / BOTH — OOS/tr $83.49, OOS-drop-top5 $29.01
- **EDGE** S2_vwap_band_ride / ITM2 / C — OOS/tr $118.65, OOS-drop-top5 $26.43
- **EDGE** S3_vwap_opening_drive / ATM / C — OOS/tr $56.54, OOS-drop-top5 $1.61
- **EDGE** S3_vwap_opening_drive / ITM2 / BOTH — OOS/tr $76.39, OOS-drop-top5 $28.52
- **EDGE** S3_vwap_opening_drive / ITM2 / C — OOS/tr $118.35, OOS-drop-top5 $37.88

## S1_vwap_touch_and_go
- signals=124  fires 36.3% of days  side={'C': 68, 'P': 56}

| tier | side | n | OOS/tr | dropT5_full | dropT5_OOS | top5%_full | posQ | null | notrunc | clears | fails |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ATM | BOTH | 117 | 53.21 | 12.95 | 17.91 | 55.5 | 4/6 | True | True | YES | - |
| ATM | C | 65 | 78.81 | 19.15 | 23.32 | 57.1 | 5/6 | True | True | YES | - |
| ATM | P | 52 | 15.81 | -12.3 | -43.83 | 198.7 | 3/6 | False | True | no | 2_pos_q_ge4of6,5_drop_top5_full_gt0,6_is_first_half_pt_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |
| ITM2 | BOTH | 116 | 103.13 | 33.25 | 39.26 | 40.7 | 4/6 | True | True | YES | - |
| ITM2 | C | 65 | 178.32 | 53.89 | 82.01 | 43.3 | 5/6 | True | True | YES | - |
| ITM2 | P | 51 | -6.78 | -20.29 | -67.71 | 281.2 | 3/6 | False | True | no | 1_oos_pt_gt0,2_pos_q_ge4of6,3_top5_full_lt200,5_drop_top5_full_gt0,6_is_first_half_pt_gt0,7_beats_random_null,9_oos_drop_top5_gt0 |

## S2_vwap_band_ride
- signals=144  fires 42.1% of days  side={'C': 80, 'P': 64}

| tier | side | n | OOS/tr | dropT5_full | dropT5_OOS | top5%_full | posQ | null | notrunc | clears | fails |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ATM | BOTH | 136 | 40.21 | 20.73 | 4.68 | 41.7 | 5/6 | True | True | YES | - |
| ATM | C | 77 | 64.43 | 18.78 | 4.67 | 51.3 | 6/6 | True | True | YES | - |
| ATM | P | 59 | 4.7 | 2.12 | -45.19 | 93.9 | 5/6 | True | True | no | 9_oos_drop_top5_gt0 |
| ITM2 | BOTH | 136 | 83.49 | 50.03 | 29.01 | 26.7 | 5/6 | True | True | YES | - |
| ITM2 | C | 77 | 118.65 | 55.03 | 26.43 | 36.1 | 6/6 | True | True | YES | - |
| ITM2 | P | 59 | 31.93 | 9.56 | -64.75 | 81.1 | 5/6 | True | True | no | 9_oos_drop_top5_gt0 |

## S3_vwap_opening_drive
- signals=165  fires 48.2% of days  side={'C': 88, 'P': 77}

| tier | side | n | OOS/tr | dropT5_full | dropT5_OOS | top5%_full | posQ | null | notrunc | clears | fails |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ATM | BOTH | 154 | 30.22 | 10.76 | -2.16 | 54.5 | 4/6 | True | True | no | 9_oos_drop_top5_gt0 |
| ATM | C | 84 | 56.54 | 10.76 | 1.61 | 63.1 | 5/6 | True | True | YES | - |
| ATM | P | 70 | -6.34 | -6.04 | -53.72 | 132.1 | 4/6 | False | False | no | 1_oos_pt_gt0,5_drop_top5_full_gt0,7_beats_random_null,8_no_truncation,9_oos_drop_top5_gt0 |
| ITM2 | BOTH | 153 | 76.39 | 39.94 | 28.52 | 28.7 | 6/6 | True | True | YES | - |
| ITM2 | C | 83 | 118.35 | 49.08 | 37.88 | 37.0 | 6/6 | True | True | YES | - |
| ITM2 | P | 70 | 18.12 | 1.89 | -68.2 | 94.5 | 3/6 | True | False | no | 2_pos_q_ge4of6,8_no_truncation,9_oos_drop_top5_gt0 |

## Disclosure
- Per-trade EXPECTANCY reported, not WR alone (OP-14).
- IS=2025 AND OOS=2026; gate 9 (OOS-ALONE drop-top5) is the decisive de-concentration gate (L173).
- Random-entry null (L172) + no-truncation (L171) via fraud_gates.verify_candidate.
- Single fixed structure per cell; both tiers + both sides reported, no survivor cherry-pick (2.10).
- Real OPRA fills; SPY-direction != option edge (C3/L58).
