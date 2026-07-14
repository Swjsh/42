# PROFIT-P3 MORNING-GATE — result

Generated: 2026-07-14T07:23:17.739518. Registration: `analysis/recommendations/prereg-morning-gate-2026-07-11.json`. Runner: `backtest/tools/morning_gate_study.py`.

**Population:** Shared p3p5_baseline: ribbon_ride BULLISH_RECLAIM/BEARISH_REJECTION, both directions, OTM-2 strike, SS-B exit shape (fixed both arms), QTY=10. Window achieved: 2025-01-06..2026-06-17 (registration's stated net window 2025-01-02..2026-06-25 -- achieved window is the cached signal set's own span, ~1wk shorter at the tail, disclosed per the registration's own 'no silent substitution' clause; the hypothesis-source window 2026-06-26..2026-07-09 does not overlap the achieved window either way).

**k5 scope check:** PASS (directions seen: ['bear', 'bull'])

## Anchor context (J's 3 OP-16 winners — disclosure, mandatory report before aggregate)

- 4/29 SPY 710P x6 -> +$342 — entry 10:25:51 ET (journal/2026-04-29.md line 29 (Entry: 10:25:51 EDT))
- 5/01 SPY 721P x20 -> +$470 (leg#1, PREMATURE/anticipation entry per journal) — entry 13:09:14 ET (journal/2026-05-01.md line 16 (Filled 13:09:14 EDT))
- 5/01 SPY 721P x20 -> +$470 (leg#2, THE REAL TRIGGER per journal) — entry 13:36:11 ET (journal/2026-05-01.md line 21 (Filled 13:36:11 EDT))
- 5/04 SPY 721P x10 -> +$730 — entry 10:27:50 ET (journal/2026-05-04.md line 39 (Entry: 10:27:50 EDT))

| candidate | cutoff | n_kept | n_removed | blocks which winners |
|---|---|--:|--:|---|
| V1_GATE_BEFORE_11 | 11:00:00 | 198 | 52 | 4/29 SPY 710P x6 -> +$342; 5/04 SPY 721P x10 -> +$730 |
| V2_GATE_BEFORE_1030 | 10:30:00 | 218 | 32 | 4/29 SPY 710P x6 -> +$342; 5/04 SPY 721P x10 -> +$730 |
| V3_GATE_FIRST_HOUR | 10:35:00 | 212 | 38 | 4/29 SPY 710P x6 -> +$342; 5/04 SPY 721P x10 -> +$730 |

## Battery results

| candidate | exp kept | exp gate-off | s1 | s2 OOS | s3 null | s4 opposite | s5 concentration | s6 BH-FDR | verdict |
|---|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| V1_GATE_BEFORE_11 | $0.98 | $17.86 | False | False | False | True | False | False | **KILL (k1_stage1_fail, k2_stage2_fail, k4_bh_fdr_fail)** |
| V2_GATE_BEFORE_1030 | $12.98 | $17.86 | False | False | False | True | False | False | **KILL (k1_stage1_fail, k2_stage2_fail, k4_bh_fdr_fail)** |
| V3_GATE_FIRST_HOUR | $-0.91 | $17.86 | False | False | False | True | False | False | **KILL (k1_stage1_fail, k2_stage2_fail, k4_bh_fdr_fail)** |

## Disclosures

- Strike fixed at OTM-2, exit shape fixed at SS-B for BOTH gate-ON and gate-OFF arms (only entry inclusion differs) -- neither knob is named by the registration; this is a filled gap disclosed in p3p5_baseline.py's own module docstring, not a re-pick.
- Stage 4 (opposite/late-session mirror null) 'comparable-or-larger' is operationalized as mirror_delta >= 90% of candidate_delta -- the registration names the concept without a numeric bar; this threshold is disclosed here, not silently chosen.
- p_null (feeding stage 6 BH-FDR) is the add-one empirical p-value of the REMOVED cohort's own realized expectancy against the stage-3 random-entry-null's per-seed means (10 seeds, module default) -- same convention PROFIT-P2 used, distinct from ribbon_rejection_wick_battery.bootstrap_p's trade-level bootstrap (disclosed, not conflated).
- anchor_context_check is DISCLOSURE-ONLY per the registration (not a pass/fail gate for P3, unlike P5's k6) -- reported prominently regardless of aggregate verdict.

