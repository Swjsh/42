# PROFIT-P5 EXPECTED-MOVE-GATE — result

Generated: 2026-07-14T07:23:51.144339. Registration: `analysis/recommendations/prereg-expected-move-gate-2026-07-11.json`. Runner: `backtest/tools/expected_move_gate_study.py`.

**Population:** Shared p3p5_baseline (IDENTICAL to morning_gate_study.py's own population -- byte-for-byte, both import p3p5_baseline.build_baseline() -- the registration's own required cross-check): ribbon_ride BULLISH_RECLAIM/BEARISH_REJECTION, both directions, OTM-2 strike, SS-B exit shape, QTY=10. Window achieved: 2025-01-06..2026-06-17.

## Anchor context check (MANDATORY k6) — VIOLATION

| winner | side | premium | expected_move_$ | V1 skip | V2 skip | V3 skip |
|---|:--:|--:|--:|:--:|:--:|:--:|
| 4/29 SPY 710P x6 -> +$342 | P | $1.67 | 3.91 | False | True | True |
| 5/01 SPY 721P leg#1 (premature) @ $0.46 | P | $0.46 | 2.0825 | True | True | False |
| 5/01 SPY 721P leg#2 (the real trigger) @ $0.19 -> blended +$470 | P | $0.19 | 2.0825 | True | False | False |
| 5/04 SPY 721P x10 -> +$730 | P | $0.85 | 2.3205 | True | True | True |

*Losers (disclosure only): Losers (5/05 722P, 5/06 730C @ $1.29/10:15 ET, 5/07 734C, 5/07 737C) -- only 5/06's entry premium+time were recoverable from journal/2026-05-06.md within this task's scope (BULLISH_RECLAIM, entry ~$1.29, trigger 10:15 ET); 5/05's premium is explicitly logged 'unknown (J did not state)' (journal/2026-05-05.md line 73) and 5/07's two loser fills are not present in journal/2026-05-07.md (file only covers pre-market through 10:30 ET in this task's read). Per the registration, losers are DISCLOSURE ONLY, not pass/fail-determinative -- incomplete loser data does not affect any verdict below; only the 3 WINNERS gate k6.*

## k5 — existing VIX-gate-only baseline: delta_exp=$26.45 (n_kept=80)

## Battery results

| candidate | exp kept | exp gate-off | s1 | s2 OOS | s3 null | s4 opposite | s5 conc | s6 BH-FDR | k5 no-lift | k6 anchor | verdict |
|---|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| V1_SESSION_FLOOR_TRAILING_PCTILE | $33.39 | $17.86 | True | False | False | True | True | False | True | True | **KILL_K6_ANCHOR_VIOLATION_MISCALIBRATED** |
| V2_REMAINING_MOVE_VS_TP1_DISTANCE | $-12.18 | $17.86 | False | False | False | True | False | False | True | True | **KILL_K6_ANCHOR_VIOLATION_MISCALIBRATED** |
| V3_PREMIUM_BUDGET_RATIO | $10.52 | $17.86 | False | False | False | True | False | False | True | True | **KILL_K6_ANCHOR_VIOLATION_MISCALIBRATED** |

## Disclosures

- Strike fixed at OTM-2, exit shape fixed at SS-B (shared p3p5_baseline module) -- same disclosed filled-gap as PROFIT-P3.
- delta_proxy = 0.30 (OTM-2 row of the registration's own frozen table) for every V2 trade -- population strike never varies, so the table lookup is constant, not a per-trade Greek (as the registration itself allows but does not require).
- SPY_price_at_open (V1's denominator) = the day's literal 09:30 RTH session open; the ATM straddle itself is sampled at the first bar >=09:35 ET per the registration's own formula -- two distinct timestamps, disclosed, not conflated.
- Stage 4 opposite-null for V1 uses the registration's own explicit mirror (75th percentile day-level skip, not count-matched); V2/V3 use the registration's other explicit instruction (opposite metric extreme, count-matched to the real candidate's blocked-n).
- k5 VIX-gate-only baseline is a LEVEL-only proxy (playbook.md's rising/falling slope leg not modeled) -- comparison baseline only, not a trading-path change.
- Losers (5/05 722P, 5/06 730C @ $1.29/10:15 ET, 5/07 734C, 5/07 737C) -- only 5/06's entry premium+time were recoverable from journal/2026-05-06.md within this task's scope (BULLISH_RECLAIM, entry ~$1.29, trigger 10:15 ET); 5/05's premium is explicitly logged 'unknown (J did not state)' (journal/2026-05-05.md line 73) and 5/07's two loser fills are not present in journal/2026-05-07.md (file only covers pre-market through 10:30 ET in this task's read). Per the registration, losers are DISCLOSURE ONLY, not pass/fail-determinative -- incomplete loser data does not affect any verdict below; only the 3 WINNERS gate k6.

