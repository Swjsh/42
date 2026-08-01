# WS3 — LEVEL-FLICKER FIX: Friday 2026-07-31 replay through the hysteresis logic

Verdict: **FIXED**. Tool: `backtest/tools/level_flicker_replay_2026_08_01.py` (drives the PRODUCTION `refresh_levels_intraday._hysteresis_carry`, N=5). Method + replay-domain caveats in the tool docstring; machine-readable sidecar: `LEVEL-FLICKER-FIX-2026-08-01.json`.

## Root cause (named, with evidence)

Every 5-min `Gamma_LevelRefresh` fire re-derives the multi-week shelf zones from scratch (`daily_context._shelf_zones`) with **today's live-FORMING daily bar included as both a candidate seed and a touch-counter** (`_find_shelf_candidates` seeds band edges from every bar's c/h/l and scores every bar as a touch — the forming bar's c/h/l move every fire). Two near-tied overlapping candidates cover the 742-744 region: `742.45-744.05` (8 touches) and `741.56-743.16` (10 touches **only while today's forming bar lands inside it**). `_merge_shelf_candidates` is greedy winner-take-all by touch count with overlap exclusion, so as spot wobbled around ~742.5-743 the winner snapped back and forth, re-tiling the region and RENAMING the written level: mid 743.25 <-> mid 742.36. `refresh_levels_intraday.refresh()` then wholesale strips + re-derives the shelf/memory/INTRADAY families each run with zero cross-run identity, so every upstream wobble went straight into `key-levels.json` and the engine's per-tick `levels_active`.

Evidence:
- `core-decisions.jsonl` 2026-07-31: safe AND bold show the IDENTICAL 331/386 + 14-transition series for 743.25 (same file read => the FILE was changing, not the read); every transition lands on a tick right after a :MM:37 refresh fire.
- `key-levels-history/2026-07-31`: 0835/0930/1550 snapshots carry `SHELF_742.45_744.05` (mid 743.25); the 1200 snapshot carries `SHELF_741.56_743.16` (mid 742.36) — the SAME logical shelf, re-tiled.
- Deterministic reproduction (scratch, real `daily_context._shelf_zones` on the real daily bars + the forming 07-31 bar rebuilt from the 5m SIP tape at each fire): the two-state bistability reproduces exactly, 76-77/89 fires matching the observed state (mismatches are partial-bar reconstruction at flip boundaries; transient bands seeded at today's own forming prints — e.g. 741.69-743.29 — appear too, direct proof of the forming-bar seeding).
- Alternate mechanisms ruled out: proximity-band recompute (|743.25 - spot| <= 5.6 all day, never near the +/-12 edge); race between refresher fires (all flips at 5-min fire boundaries, none sub-5-min); rounding (bands differ by $0.89, not 1c).

## Fix + N=5 provenance

`_hysteresis_carry` in `setup/scripts/refresh_levels_intraday.py`: a previously written ACTIVE level that fails to re-qualify (no fresh level within $0.10 and no fresh level sharing its prefix-stripped label) is carried forward verbatim with a `hyst_miss_streak` counter until it has been missing 5 CONSECUTIVE refreshes or its session expiry passes. Observed Friday absence-run distribution for 743.25: {1 refresh: x5, 2: x1, 4: x1} — max flicker gap 4, so N=5 bridges every observed gap while a genuinely-gone level still retires <= ~25 min after it last qualified. Conservative by construction: only verbatim prior-file levels are ever re-emitted (never a price that never qualified); a detector that legitimately MOVES its level (same label, new price) still retires the old price instantly via label identity. Guards incl. RED-proof: `backtest/tests/test_level_hysteresis_2026_08_01.py` (neutering the carry fails 7 tests, reproducing the observed 14-flip series).

- Ticks: 386 (safe ledger; bold verified identical). Refresh windows: 78 (5-min fires at :MM:37, MM%5==3). Non-uniform windows: 19.
- **743.25 (the 28-session shelf): 331/386 ticks, 14 flips  →  386/386 ticks, 0 flips.**
- Superset + no-wrongly-sticky assertions ran in-line for EVERY level (script raises on violation; a level that left the feed for good still retires within 5 windows ≈ 25 min).

| Level | old present /386 | old flips | new present /386 | new flips | extra ticks | extra windows after last qual | note |
|--:|--:|--:|--:|--:|--:|--:|---|
| 729.79 | 81 | 9 | 81 | 9 | 0 | 0 | near +/-12 band edge some ticks |
| 735.10 | 351 | 1 | 351 | 1 | 0 | 0 | near +/-12 band edge some ticks |
| 736.78 | 20 | 4 | 45 | 2 | 25 | 4 | near +/-12 band edge some ticks |
| 737.33 | 5 | 2 | 25 | 2 | 20 | 4 |  |
| 737.57 | 10 | 2 | 10 | 2 | 0 | 0 |  |
| 737.58 | 10 | 2 | 10 | 2 | 0 | 0 |  |
| 737.68 | 312 | 1 | 312 | 1 | 0 | 0 |  |
| 737.85 | 376 | 2 | 386 | 0 | 10 | 0 |  |
| 737.97 | 5 | 2 | 25 | 2 | 20 | 4 |  |
| 738.36 | 45 | 4 | 85 | 4 | 40 | 4 |  |
| 738.98 | 5 | 2 | 25 | 2 | 20 | 4 |  |
| 739.15 | 65 | 6 | 115 | 4 | 50 | 4 |  |
| 739.34 | 5 | 2 | 25 | 2 | 20 | 4 |  |
| 739.73 | 361 | 8 | 386 | 0 | 25 | 0 |  |
| 739.91 | 10 | 2 | 10 | 2 | 0 | 0 |  |
| 739.93 | 115 | 4 | 135 | 4 | 20 | 4 |  |
| 740.17 | 15 | 6 | 60 | 4 | 45 | 4 |  |
| 740.29 | 5 | 2 | 25 | 2 | 20 | 4 |  |
| 740.76 | 179 | 7 | 234 | 1 | 55 | 4 |  |
| 741.12 | 20 | 2 | 40 | 2 | 20 | 4 |  |
| 741.55 | 30 | 2 | 30 | 2 | 0 | 0 |  |
| 741.60 | 306 | 12 | 306 | 12 | 0 | 0 |  |
| 741.62 | 5 | 2 | 5 | 2 | 0 | 0 |  |
| 741.63 | 45 | 10 | 45 | 10 | 0 | 0 |  |
| 741.98 | 5 | 2 | 25 | 2 | 20 | 4 |  |
| 742.34 | 20 | 2 | 40 | 2 | 20 | 4 |  |
| 742.36 | 40 | 12 | 100 | 6 | 60 | 0 |  |
| 742.46 | 40 | 2 | 40 | 2 | 0 | 0 |  |
| 742.49 | 10 | 2 | 10 | 2 | 0 | 0 |  |
| 742.51 | 312 | 7 | 332 | 5 | 20 | 0 |  |
| 742.79 | 386 | 0 | 386 | 0 | 0 | 0 |  |
| 742.90 | 4 | 1 | 24 | 1 | 20 | 4 |  |
| 742.95 | 15 | 2 | 35 | 2 | 20 | 4 |  |
| 743.10 | 25 | 2 | 45 | 2 | 20 | 4 |  |
| 743.25 | 331 | 14 | 386 | 0 | 55 | 0 |  |
| 743.56 | 10 | 2 | 30 | 2 | 20 | 4 |  |
| 743.66 | 10 | 2 | 30 | 2 | 20 | 4 |  |
| 743.99 | 65 | 2 | 85 | 2 | 20 | 4 |  |
| 744.13 | 4 | 1 | 24 | 1 | 20 | 4 |  |
| 744.31 | 337 | 5 | 367 | 3 | 30 | 0 |  |
| 744.43 | 15 | 2 | 35 | 2 | 20 | 4 |  |
| 744.91 | 4 | 1 | 4 | 1 | 0 | 0 |  |
| 744.98 | 382 | 1 | 382 | 1 | 0 | 0 |  |
| 745.19 | 50 | 2 | 70 | 2 | 20 | 4 |  |
| 745.20 | 40 | 2 | 40 | 2 | 0 | 0 |  |
| 745.31 | 35 | 2 | 55 | 2 | 20 | 4 |  |
| 745.67 | 25 | 2 | 45 | 2 | 20 | 4 |  |
| 745.72 | 4 | 1 | 24 | 1 | 20 | 4 |  |
| 745.79 | 25 | 2 | 27 | 1 | 2 | 1 |  |
| 746.04 | 15 | 2 | 15 | 2 | 0 | 0 |  |
| 746.09 | 87 | 3 | 87 | 3 | 0 | 0 |  |
| 746.30 | 225 | 2 | 245 | 2 | 20 | 4 |  |
| 746.40 | 5 | 2 | 5 | 2 | 0 | 0 |  |
| 746.43 | 30 | 2 | 50 | 2 | 20 | 4 |  |
| 746.44 | 5 | 2 | 5 | 2 | 0 | 0 |  |
| 746.50 | 50 | 2 | 50 | 2 | 0 | 0 |  |
| 746.54 | 15 | 2 | 15 | 2 | 0 | 0 |  |
| 746.55 | 321 | 4 | 321 | 4 | 0 | 0 |  |
| 746.87 | 2 | 1 | 2 | 1 | 0 | 0 |  |
| 747.54 | 5 | 2 | 15 | 2 | 10 | 2 |  |
| 747.55 | 5 | 2 | 22 | 1 | 17 | 4 |  |
| 747.92 | 17 | 1 | 17 | 1 | 0 | 0 |  |
| 748.09 | 381 | 2 | 386 | 0 | 5 | 0 |  |
| 748.50 | 317 | 7 | 357 | 3 | 40 | 0 |  |
| 750.98 | 376 | 2 | 376 | 2 | 0 | 0 | near +/-12 band edge some ticks |
| 752.77 | 341 | 4 | 341 | 4 | 0 | 0 | near +/-12 band edge some ticks |
| 754.71 | 255 | 3 | 255 | 3 | 0 | 0 | near +/-12 band edge some ticks |
| 756.38 | 205 | 5 | 205 | 5 | 0 | 0 | near +/-12 band edge some ticks |
