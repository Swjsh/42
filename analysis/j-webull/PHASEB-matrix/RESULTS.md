# Phase B — J-EDGE DEEP MATRIX: results (2026-07-01)

> ## ⚠ BS-SYNTHETIC OPTION PRICING — RANKING-ONLY EVIDENCE PER C1. No smile, no spread, no fills. Never a promotion gate.

> Pre-registered design: [DESIGN.md](DESIGN.md) — committed BEFORE the grind. Grinder: `matrix_grinder.py`. Full train grid: `train-grid.csv.gz`. JSON twin: `results.json`.

## Universe

539 episodes replayed (train 468 / test 71). Drops: {'no_ctx': 25, 'no_vix': 0, 'no_entry_bar': 0, 'no_path_bars': 3}. Unpriceable (BS prem < $0.05) by strike: {'his': 102, 'atm': 0, 'itm1': 0, 'itm2': 0, 'otm1': 0}.

E6 structure features at grind time: **added [E6 verdict=NO_SEPARATION]: level_sweep_favor > 0; touch_count >= train-median 1; event_recency > 0**.

## E2 anchor reproduction (gate: must match before results count)

| Anchor | n (got/exp) | total (got/exp) | match |
|---|---|---|---|
| a_his_strike | 437 / 437 | +8183.66 / +8183.66 | PASS |
| b_atm_strike | 539 / 539 | +109111.92 / +109111.92 | PASS |

## The funnel (honest)

| Stage | count |
|---|---|
| Cells ground (exit x strike x filter x size) | 57600 |
| Train-positive (mean > 0) | 55595 |
| Eligible (n_train>=60, drop-top3>0, n_test>=30 members) | 4577 |
| Top-K taken to test (ONE evaluation) | 25 |
| Test-positive (total > 0) | 25 |
| **BH-FDR survivors (q<=0.1 + drop-top3 + both halves)** | **6** |

## VERDICT: **SURVIVORS_FOUND**

## Top-K test table

| # | cell (exit / strike / filter / size) | n_tr | train $/tr | train t | n_te | test $/tr | test total | drop-top3 | p | q | halves | null-dom | SURV |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `stop-50·tp30x67·trailChand·tEOD` otm1 dir=C fixed_1 | 240 | +161.1 | 5.98 | 43 | +64.9 | +2790 | +1374 | 0.018 | 0.073 | +1771/+1019 | no | **YES** |
| 2 | `stop-50·tp30x67·trailChand·tEOD` atm dir=C fixed_1 | 240 | +186.1 | 5.95 | 43 | +89.4 | +3843 | +2254 | 0.016 | 0.073 | +2779/+1064 | no | **YES** |
| 3 | `stop-50·tp30x67·trailChand·t120` otm1 dir=C fixed_1 | 240 | +157.5 | 5.92 | 43 | +64.9 | +2790 | +1374 | 0.018 | 0.073 | +1771/+1019 | no | **YES** |
| 4 | `stop-50·tp30x67·trailChand·t120` atm dir=C fixed_1 | 240 | +182.0 | 5.90 | 43 | +89.4 | +3843 | +2254 | 0.016 | 0.073 | +2779/+1064 | no | **YES** |
| 5 | `stop-20·tp30x67·trailChand·t120` atm dir=C fixed_1 | 240 | +167.9 | 5.83 | 43 | +86.8 | +3733 | +2145 | 0.011 | 0.073 | +2262/+1471 | no | **YES** |
| 6 | `stop-50·tp30x67·trailChand·t60` otm1 dir=C fixed_1 | 240 | +152.1 | 5.82 | 43 | +65.3 | +2810 | +1395 | 0.017 | 0.073 | +1791/+1019 | no | **YES** |
| 7 | `stop-20·tp30x67·trailNone·t60` otm1 all fixed_1 | 468 | +142.1 | 6.81 | 71 | +38.2 | +2716 | +1087 | 0.046 | 0.111 | +818/+1898 | no | no |
| 8 | `stop-20·tp30x67·trailChand·tEOD` otm1 all fixed_1 | 468 | +126.2 | 6.75 | 71 | +33.6 | +2388 | +972 | 0.049 | 0.111 | +557/+1831 | no | no |
| 9 | `stop-50·tp30x67·trailChand·tEOD` itm1 dir=C fixed_1 | 240 | +204.8 | 5.83 | 43 | +90.3 | +3884 | +2112 | 0.048 | 0.111 | +3376/+508 | no | no |
| 10 | `stop-50·tp30x67·trailChand·t120` itm1 dir=C fixed_1 | 240 | +201.2 | 5.78 | 43 | +90.3 | +3884 | +2112 | 0.048 | 0.111 | +3376/+508 | no | no |
| 11 | `stop-20·tp30x67·trailChand·t120` itm1 dir=C fixed_1 | 240 | +188.0 | 5.77 | 43 | +87.2 | +3748 | +1976 | 0.034 | 0.111 | +2209/+1539 | no | no |
| 12 | `stop-50·tp30x67·trailChand·t120` itm2 dir=C fixed_1 | 240 | +235.5 | 5.71 | 43 | +106.9 | +4598 | +2262 | 0.060 | 0.115 | +4797/-199 | no | no |
| 13 | `stop-20·tp75x67·trailNone·tEOD` otm1 aligned fixed_1 | 322 | +275.7 | 5.67 | 50 | +108.4 | +5419 | +332 | 0.056 | 0.115 | -129/+5548 | no | no |
| 14 | `stop-20·tp75x67·trailNone·t60` otm1 all fixed_1 | 468 | +189.6 | 6.90 | 71 | +42.2 | +2993 | +816 | 0.078 | 0.119 | -237/+3230 | no | no |
| 15 | `stop-20·tp30x67·trailChand·tEOD` atm all fixed_1 | 468 | +142.2 | 6.65 | 71 | +38.1 | +2704 | +1115 | 0.085 | 0.119 | +189/+2514 | no | no |
| 16 | `stop-20·tp30x67·trailChand·t120` atm all fixed_1 | 468 | +141.7 | 6.64 | 71 | +38.1 | +2704 | +1115 | 0.085 | 0.119 | +189/+2514 | no | no |
| 17 | `stop-20·tp150x80·trailNone·tEOD` otm1 aligned fixed_1 | 322 | +314.8 | 5.83 | 50 | +85.8 | +4288 | -43 | 0.091 | 0.119 | -153/+4441 | YES | no |
| 18 | `stop-50·tp30x67·trailChand·t60` atm aligned first_fill | 322 | +244.7 | 5.76 | 50 | +127.4 | +6368 | +2325 | 0.088 | 0.119 | +4605/+1763 | no | no |
| 19 | `stop-50·tp30x67·trailChand·tEOD` atm aligned first_fill | 322 | +245.8 | 5.74 | 50 | +121.8 | +6092 | +2133 | 0.095 | 0.119 | +4413/+1679 | no | no |
| 20 | `stop-50·tp30x67·trailChand·t120` atm aligned first_fill | 322 | +240.9 | 5.68 | 50 | +121.8 | +6092 | +2133 | 0.095 | 0.119 | +4413/+1679 | no | no |
| 21 | `stop-20·tp75x67·trailNone·t60` atm all fixed_1 | 468 | +208.2 | 6.61 | 71 | +47.4 | +3368 | +719 | 0.119 | 0.141 | -929/+4297 | no | no |
| 22 | `stop-20·tp30x67·trailChand·tEOD` itm1 all fixed_1 | 468 | +157.9 | 6.57 | 71 | +36.1 | +2564 | +635 | 0.157 | 0.179 | -577/+3141 | no | no |
| 23 | `stop-20·tp30x67·trailNone·t60` itm1 all fixed_1 | 468 | +180.0 | 6.66 | 71 | +39.3 | +2793 | +365 | 0.167 | 0.182 | -150/+2943 | no | no |
| 24 | `stop-20·tp75x67·trailNone·t60` itm1 all fixed_1 | 468 | +236.8 | 6.63 | 71 | +33.1 | +2352 | -934 | 0.260 | 0.271 | -2356/+4708 | no | no |
| 25 | `stop-20·tp75x67·trailNone·t60` itm2 all fixed_1 | 468 | +258.8 | 6.48 | 71 | +14.2 | +1007 | -2927 | 0.407 | 0.407 | -3031/+4038 | no | no |

## Survivors -> Phase-C port specs

### C-spec 1: `stop-50·tp30x67·trailChand·tEOD` / strike=otm1 / filter=dir=C / size=fixed_1

- Train: n=240, +161.1 $/tr, t=5.98. Test: n=43, +64.9 $/tr, total +2790, WR 67.4%, p=0.0176, q=0.0734, boot P(sum<=0)=0.0136, drop-top3 +1374, halves +1771/+1019, null_total -630.
- **Detector (Phase C, 2025-26 OPRA):** J-entry-context screen = `dir=C`; strike rule = otm1; exit = stop-50|tp30x67|trailChand|tEOD; size = fixed_1. Validate on real fills per C1 before anything ships.

### C-spec 2: `stop-50·tp30x67·trailChand·tEOD` / strike=atm / filter=dir=C / size=fixed_1

- Train: n=240, +186.1 $/tr, t=5.95. Test: n=43, +89.4 $/tr, total +3843, WR 69.8%, p=0.0155, q=0.0734, boot P(sum<=0)=0.0138, drop-top3 +2254, halves +2779/+1064, null_total -630.
- **Detector (Phase C, 2025-26 OPRA):** J-entry-context screen = `dir=C`; strike rule = atm; exit = stop-50|tp30x67|trailChand|tEOD; size = fixed_1. Validate on real fills per C1 before anything ships.

### C-spec 3: `stop-50·tp30x67·trailChand·t120` / strike=otm1 / filter=dir=C / size=fixed_1

- Train: n=240, +157.5 $/tr, t=5.92. Test: n=43, +64.9 $/tr, total +2790, WR 67.4%, p=0.0176, q=0.0734, boot P(sum<=0)=0.0137, drop-top3 +1374, halves +1771/+1019, null_total -630.
- **Detector (Phase C, 2025-26 OPRA):** J-entry-context screen = `dir=C`; strike rule = otm1; exit = stop-50|tp30x67|trailChand|t120; size = fixed_1. Validate on real fills per C1 before anything ships.

### C-spec 4: `stop-50·tp30x67·trailChand·t120` / strike=atm / filter=dir=C / size=fixed_1

- Train: n=240, +182.0 $/tr, t=5.90. Test: n=43, +89.4 $/tr, total +3843, WR 69.8%, p=0.0155, q=0.0734, boot P(sum<=0)=0.0141, drop-top3 +2254, halves +2779/+1064, null_total -630.
- **Detector (Phase C, 2025-26 OPRA):** J-entry-context screen = `dir=C`; strike rule = atm; exit = stop-50|tp30x67|trailChand|t120; size = fixed_1. Validate on real fills per C1 before anything ships.

### C-spec 5: `stop-20·tp30x67·trailChand·t120` / strike=atm / filter=dir=C / size=fixed_1

- Train: n=240, +167.9 $/tr, t=5.83. Test: n=43, +86.8 $/tr, total +3733, WR 60.5%, p=0.0110, q=0.0734, boot P(sum<=0)=0.0068, drop-top3 +2145, halves +2262/+1471, null_total -1052.
- **Detector (Phase C, 2025-26 OPRA):** J-entry-context screen = `dir=C`; strike rule = atm; exit = stop-20|tp30x67|trailChand|t120; size = fixed_1. Validate on real fills per C1 before anything ships.

### C-spec 6: `stop-50·tp30x67·trailChand·t60` / strike=otm1 / filter=dir=C / size=fixed_1

- Train: n=240, +152.1 $/tr, t=5.82. Test: n=43, +65.3 $/tr, total +2810, WR 67.4%, p=0.0171, q=0.0734, boot P(sum<=0)=0.0133, drop-top3 +1395, halves +1791/+1019, null_total -264.
- **Detector (Phase C, 2025-26 OPRA):** J-entry-context screen = `dir=C`; strike rule = otm1; exit = stop-50|tp30x67|trailChand|t60; size = fixed_1. Validate on real fills per C1 before anything ships.


## Caveats

- All E2 caveats inherit (BS-synthetic, VIX-open IV, 5m bar-close granularity, entry priced up to 5 min before his tick, non-0DTE force-flattened same day, r=4%).
- Test year capacity: only broad filters can reach n_test>=30 (71 test episodes total) — registered in DESIGN.md before grinding.
- fixed_3 size rows are 3x fixed_1 by construction (identical signal); excluded from ranking, present in the grid.
- his-strike cells ride on mispriced BS entry premia (median BS/actual = 0.222, E2 calibration) — noisiest axis, drops adversely selective.
- Null diagnostic per cell: opposite-direction ATM through the same exit cfg; null-dominated survivors are convexity-harvest artifacts, not J-direction edge.

Runtime: 14.5 s, single process.

## Interpretation (post-hoc, non-verdict-bearing — added after the frozen protocol ran)

1. **The 6 survivors are ONE family, not six edges:** J's CALL entries + TP1 +30% sell 2/3 +
   chandelier profit-lock (arm +5%, trail 15% off HWM) at ATM/OTM1, with the stop level
   (−20/−50) and time-stop (60m/120m/EOD) nearly irrelevant — chandelier/TP1 exit first.
   Collapsed, that is ~3 distinct cells; the Phase-C battery should treat them as one
   hypothesis with knob variants, not six independent claims.
2. **The null column is what makes this credible:** every survivor's opposite-direction null
   is NEGATIVE (−$264…−$1,052) on the same moments/exits — the test-year edge is J's bullish
   directional read, not BS convexity. Contrast rank-17 (`tp150x80`, aligned), which is
   null-dominated (+$4,606 null) and correctly died.
3. **Train-positive 55,595/57,600 (96.5%) is the in-era frictionless-BS artifact** E2
   quantified (~+$76/tr convexity baseline) — the reason the funnel discipline (train-only
   ranking, ONE test pass, FDR, null) was mandatory, and the reason none of these dollar
   figures forecast live P&L.
4. **Convergence with already-shipped doctrine:** the surviving ladder is essentially v15.3's
   management (TP1 +30, chandelier 15% HWM) applied to BULLISH entries at sane strikes —
   independently re-derived from J's own 2021-23 book. It rhymes with the 2026-06-26 real-fills
   finding that bull was net-positive (+$5,586, chef-bull-scope-ab). The `aligned` ATM
   first-fill cells (ranks 18-20, test +$122-127/tr) just missed at q=0.119 — worth carrying
   into Phase C as a secondary screen, NOT as a survivor.
5. **What Phase B does NOT license:** any params change, any arming, any expectation that
   +$65-89/tr survives real 0DTE spreads. Phase C = re-express as detectors on 2025-26 SPY,
   run the OPRA real-fills battery (C1), FDR again there.
