# block_elite_bull SS-B revalidation -- RUN 2026-09-03

**RESEARCH / SIM-ONLY. Nothing here ships.**

## MAJOR FINDING
A COMPLETE confirmatory run already exists: analysis/recommendations/block-elite-bull-ssb-revalidation.json, generated_at=2026-07-10T16:10:35 (same day as the freeze). It was never OPRA-blocked -- OPRA access was available that session. The prereg's `status` field was simply never flipped from FROZEN_PENDING_RUN afterward (a bookkeeping gap, not an actually-pending run). VERDICT (from that run, authoritative): KEEP.

## AUTHORITATIVE VERDICT (from the 2026-07-10 confirmatory run)
- **verdict: KEEP**
- conditions: {"condition_1_ssb_total_positive": false, "condition_2_ssb_drop_top1_positive": false, "condition_3_old_exit_parity": true, "condition_4_n_events_floor_12": true, "all_pass": false, "verdict": "KEEP"}
- elite cohort n=28: OLD exit total pnl = $-560.00, SS-B exit total pnl = $-3873.60 (SS-B drop-top-1 remainder = $-6810.00)
- Both exit shapes lose money on the elite cohort -- SS-B does not rescue it; block_elite_bull correctly stays armed.

## Cross-validation: tonight's OPRA-free mining vs the 2026-07-10 run
- all countable fields match: **True**
- {"n_raw_ticks_part_b": {"tonight": 100, "2026_07_10_run": 100}, "n_kept_part_b": {"tonight": 21, "2026_07_10_run": 21}, "n_kept_comparison": {"tonight": 4, "2026_07_10_run": 4}, "part_a_n": {"tonight": 7, "2026_07_10_run": 7}, "part_a_pnl": {"tonight": -241.26, "2026_07_10_run": -241.26}, "all_match": true}

preflight: `{"prereg_version": 1, "prereg_version_ok": true, "prereg_sha256_16_recomputed": "9182d6f9e43b62ab", "prereg_sha256_16_stored": "9182d6f9e43b62ab", "prereg_hash_ok": true}`

## Tonight's own characterization (cross-check only, not authoritative when a prior confirmatory result exists)
- part_a (reused prior artifact, NOT re-run): n=7, old-exit net pnl recorded=$-241.26
- part_b extension (07-01..07-10): 100 raw ticks -> 21 events (5min dedupe) -> 0 stale-echo excluded -> **21 final events** (sensitivity: 2min=21, 15min=17; 0 open-adjacent flagged, not excluded)
- trigger_level recovered (non-fallback) for 10/21 kept events
- elite cohort n_final (part_a + part_b): **28**
- SUPER comparison cohort (disclosure only): 22 raw ticks -> **4 final events**

## Dollar impact on the real record
From the already-completed 2026-07-10 confirmatory run: on the FULL elite cohort (n=28), the OLD exit shape totals $-560.00 and SS-B totals $-3873.60 -- unblocking under EITHER exit shape would have LOST money on this population; SS-B is worse than OLD here, not better. The gate is correctly KEEPING this cohort blocked; no further OPRA work changes that conclusion.
