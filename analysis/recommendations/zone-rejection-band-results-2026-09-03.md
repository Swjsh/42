# Zone-rejection-band study -- ZONE-REJECTION-BAND-2026-07-17

Generated: 2026-09-03T00:32:09.816280. Source: `backtest/tools/zone_rejection_band_study.py`. Pre-reg: `analysis/recommendations/prereg-zone-rejection-band-2026-07-17.json`.

**Motivating incident:** 2026-07-17 10:15 ET, SPY 747.27 vs PDL 747.88 (61c shy), zero triggers both accounts (core-decisions.jsonl confirmed).

**Walker used:** exit_manager_walk (via structure_stop_study.replay_structure_aware -> exit_manager.plan_exit_actions -- the LIVE decision core, per-bar), NOT multileg_exit_walk.py. This study never imports multileg_exit_walk.

**Magnitude-fidelity caveat:** exit_manager_walk's own magnitude-fidelity anchor (whole_engine_null.py V9, n=121, 2026-09-02) is aggregate_ratio=0.6452, median_abs_error=$15.00 -- WITHIN the pre-registered magnitude criterion (|ratio-1|<=0.4, median<=$40; see analysis/harness-fidelity/WALKER-MAGNITUDE-2026-09-03.md). This is the OPPOSITE situation from multileg_exit_walk, which fails that same criterion even after its 2026-09-03 partial fix -- dollar magnitudes in THIS study's cells are read as walker-trustworthy, not merely sign-trustworthy, though the underlying WF-gate ladder itself only ever required sign/ranking correctness.

**Control cell:** the current, unmodified, already-shipped exact-pierce `filters.py#detect_level_rejection` (Z=0 / candidate disabled). Every cell above is a delta AGAINST this control, not an absolute P&L -- delta=0 by definition.

## SAFE

Tier **ATM** (so=0), equity=$1485.31, qty=3, time_stop=15:40:00. Control bear trades: 138. Candidate bear trades: 83. Umbrella zone-branch fires: 3665.

Episodes: unchanged=47, new=8, shifted=28, control_only_excess(diagnostic)=63, dropped={'no_local_bars': 0, 'floor_skip': 0}.

| Z cell | n | n_is/n_oos | IS delta/tr | OOS delta/tr | WF | verdict_ladder | anchor_ok | bh_survivor | ship_ready |
|---|--:|--:|--:|--:|--:|---|:--:|:--:|:--:|
| fixed_0.15 | 1 | 1/0 | $-141.0 | $None | None | FAIL_NO_IMPROVEMENT | True | False | False |
| fixed_0.3 | 3 | 1/2 | $-141.0 | $-70.7 | None | FAIL_NO_IMPROVEMENT | True | False | False |
| fixed_0.5 | 6 | 2/4 | $25.5 | $-46.23 | -1.8127 | FAIL_WF_BELOW_BAR | False | False | False |
| fixed_0.75 | 12 | 8/4 | $24.18 | $-46.23 | -1.9116 | FAIL_WF_BELOW_BAR | False | False | False |
| fixed_1.0 | 21 | 15/6 | $-22.55 | $-49.32 | None | FAIL_NO_IMPROVEMENT | False | False | False |
| atr_0.1x | 0 | 0/0 | $None | $None | None | NO_EPISODES | True | False | False |
| atr_0.2x | 2 | 1/1 | $-141.0 | $-186.0 | None | FAIL_NO_IMPROVEMENT | True | False | False |
| atr_0.3x | 2 | 1/1 | $-141.0 | $-186.0 | None | FAIL_NO_IMPROVEMENT | True | False | False |

**SAFE: NULL RESULT (KILL).** Closest cell: `fixed_0.3` (2/5 gates passed, verdict_ladder=FAIL_NO_IMPROVEMENT, n=3, IS=$-141.0, OOS=$-70.7) -- fails: ['oos_positive', 'wf_ge_070', 'bh_fdr_survivor'].

**Best-day concentration** (full new+shifted delta population, 32 trading days, total delta $-181.55): best day 2025-01-07 contributed $549.0 (-3.024 of total, 0.1868 of gross-positive-day delta).

## BOLD

Tier **OTM-3** (so=-3), equity=$1963.04, qty=5, time_stop=15:40:00. Control bear trades: 192. Candidate bear trades: 131. Umbrella zone-branch fires: 3608.

Episodes: unchanged=87, new=14, shifted=30, control_only_excess(diagnostic)=75, dropped={'no_local_bars': 0, 'floor_skip': 0}.

| Z cell | n | n_is/n_oos | IS delta/tr | OOS delta/tr | WF | verdict_ladder | anchor_ok | bh_survivor | ship_ready |
|---|--:|--:|--:|--:|--:|---|:--:|:--:|:--:|
| fixed_0.15 | 4 | 2/2 | $-255.0 | $115.0 | None | INSUFFICIENT_REGIME_SHIFT | True | False | False |
| fixed_0.3 | 5 | 3/2 | $-256.67 | $115.0 | None | INSUFFICIENT_REGIME_SHIFT | True | False | False |
| fixed_0.5 | 8 | 3/5 | $-256.67 | $60.24 | None | INSUFFICIENT_REGIME_SHIFT | True | False | False |
| fixed_0.75 | 15 | 10/5 | $-343.0 | $60.24 | None | INSUFFICIENT_REGIME_SHIFT | True | False | False |
| fixed_1.0 | 27 | 18/9 | $-185.2 | $-136.26 | None | FAIL_NO_IMPROVEMENT | False | False | False |
| atr_0.1x | 2 | 1/1 | $-290.0 | $470.0 | None | INSUFFICIENT_REGIME_SHIFT | True | False | False |
| atr_0.2x | 4 | 2/2 | $-255.0 | $115.0 | None | INSUFFICIENT_REGIME_SHIFT | True | False | False |
| atr_0.3x | 4 | 2/2 | $-255.0 | $115.0 | None | INSUFFICIENT_REGIME_SHIFT | True | False | False |

**BOLD: NULL RESULT (KILL).** Closest cell: `fixed_0.75` (3/5 gates passed, verdict_ladder=INSUFFICIENT_REGIME_SHIFT, n=15, IS=$-343.0, OOS=$60.24) -- fails: ['wf_ge_070', 'bh_fdr_survivor'].

**Best-day concentration** (full new+shifted delta population, 42 trading days, total delta $-9211.7): best day 2026-02-23 contributed $1805.0 (-0.1959 of total, 0.2424 of gross-positive-day delta).

## Overall verdict

any_ship_ready_overall=False (safe=False, bold=False)

## Disclosures

- MEASURED (real OPRA local cache replay), not REALIZED -- no broker fills exist for this candidate trigger, which does not exist in production.
- Umbrella single-pass mining (not 8 separate per-cell orchestrator runs) -- smaller Z cells are exact post-filters on recorded proximity_cents/atr_at_fire; a disclosed path-dependence caveat applies to SAME-DAY SEQUENCING after a wide-Z entry (see prereg mining_method_umbrella).
- Episode attribution is ordinal (date,direction) matching, not a full state-machine replay isolated per Z cell -- disclosed simplification, per the frozen prereg.
- control_only_excess (ordinal slots where control had MORE same-day bear entries than candidate) is a diagnostic OUTSIDE the frozen prereg's delta definition -- reported, not gated, per the frozen document's own scope (new/shifted/unchanged only).
- Safe's live block_level_rejection=true gate is threaded through orchestrator.run_backtest's own params_overrides -- the mined control/candidate populations already reflect its suppression of single-trigger LEVEL-tier entries; not re-derived separately.
- Null-sanity draw count is capped at 40 per cell (n_signals=min(cell_n,40)) and cached by that capped count across cells sharing it -- disclosed efficiency simplification, not a per-cell-exact null.
- min_entry_premium floor (0.30, both accounts) applied IN-SIM against the raw entry-bar OPEN premium; a signal below floor is dropped and counted, never imputed (C7).
- ONE process, no multiprocessing.Pool -- OPRA local bar cache is process-local; matches the 6-8-worker-ceiling / OPRA-cache-deadlock lesson by staying at 1 worker for this cache-bound workload (same convention every SS-B-lineage study this week used).

