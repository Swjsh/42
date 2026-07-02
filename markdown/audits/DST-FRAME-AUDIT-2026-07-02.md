# DST Frame Audit — fixed -04:00 wall-time artifact (2026-07-02)

> Found during WIRE-BOLLINGER (disclosed in
> `analysis/recommendations/bollinger-squeeze-fresh-reverify.json` →
> `frame_convention_disclosure`). This doc is the canonical audit: root cause,
> verified consumer classification, blast radius, the fix, and the
> re-validation plan. Guards: `backtest/tests/test_et_frame_guards.py`.

## TL;DR

The SPY master CSVs store timestamps with a **fixed `-04:00` offset
year-round**. The UTC instant of every row is CORRECT; the offset **label** is
wrong for EST months (Nov–Mar). Every consumer that parses naively and strips
tz ("wall-v1" convention) therefore read winter sessions as 10:30–16:55 wall —
the RTH slice `[09:30, 16:00)` **clipped the last true trading hour** and every
winter bar label sat **+1h vs true ET**. **129 of 365 trading days (35%)** in
the `2025-01-01..2026-06-18` master are EST days.

The fix is at the **parse boundary** (`backtest/lib/et_frame.py`), NOT a CSV
rewrite, behind an explicit `frame=` parameter with **defaults staying legacy
("wall-v1") until re-validation diffs are filed** (no silent swap). The writer
root cause is also fixed for future appends.

## Root cause (verified)

`backtest/tools/extend_data_v2.py` SPY fetch (pre-fix):

```python
ts_et = ts_utc - dt.timedelta(hours=4)                     # constant offset — wrong in EST
"timestamp_et": ts_et.strftime("%Y-%m-%d %H:%M:%S-04:00")  # hardcoded label
```

The VIX branch of the same file always did it correctly
(`tz_convert("America/New_York")` + `%z`), so **the VIX master is NOT
affected** (winter rows carry `-0500`). The OPRA option cache
(`backtest/data/options/*.csv`) shares the SPY convention (fixed `-04:00`).

Verified reproduction (master CSV, 2025-01-07):

| parse | RTH bars | first | last |
|---|---|---|---|
| wall-v1 (naive strip) | 66 | 10:30 | 15:55 (= true 14:55) |
| et-v2 (UTC→ET) | 78 | 09:30 | 15:55 |

## What the wall-time frame did to winter backtests

1. **Last true trading hour invisible** (true 14:55–15:55 never simulated);
   the 15:50 time-stop fired at true 14:50.
2. **Thin premarket prints mislabeled as the RTH open.** The Alpaca fetch
   window is fixed in UTC, so winter IEX *premarket* trades (true 08:30–09:25
   EST) parse as wall 09:30–10:25 "RTH" bars. Verified 2025-01-27: a lone
   200-share bar at "09:30" (median RTH volume that day: ~8K), then a gap to
   10:30. Of the 129 EST days, 36 have no premarket rows (clean 66-bar clip
   starting 10:30); the rest open on sparse premarket bars — poisoning
   opening-range, first-hour and volume-baseline logic on those days.
3. **Entry gate distorted**: 09:35–15:45 wall = true 08:35–14:45 — winter
   entries could fire on premarket prints and stopped at true 14:45.
4. **Time-of-day labels +1h** on all winter bars (morning/afternoon splits,
   TOD analyses shifted).
5. **OPRA joins stayed consistent** — SPY and option cache share the fixed
   offset, so real-fills prices were correct for the bars evaluated (mislabeled
   + clipped, not misaligned). Verified by guard
   `test_opra_join_frame_consistent`.
6. **VIX joins**: the orchestrator aligns SPY↔VIX on `utc=True` (correct — no
   leakage). Any consumer joining SPY↔VIX on *naive* timestamps pairs winter
   SPY bars with VIX from **one hour in the future** (look-ahead, C6) — flagged
   per-file below.

**Stage-1 measured deltas** (identical 2025-01-01..2026-06-18 window, signals
et-v2 vs wall-v1): bollinger_squeeze **316→351**, three_ducks 1133→1180,
supply_demand_zone 248→243, ema_adx 136→137 — every non-zero monthly delta
falls in Nov–Mar, zero in EDT months (mechanism confirmed). The 360 figure in
the original WIRE-BOLLINGER disclosure was measured on the extended window
through 2026-07-01.

## Consumer classification (verified on the load-bearing paths)

**WALL-TIME (winter-clipped):**
- `autoresearch/family_detectors.build_rth` + `null_baseline` + `family_grind`
  → all family grinds, mass grinds, `grind_new_families` (bollinger 316 wall
  vs 360 et-v2 signals)
- `lib/orchestrator.py:782-794` (production backtest engine RTH slice) → **all
  orchestrator A/B scorecards share the winter clipping**; its VIX align
  (`:233`, utc=True) is correct
- `lib/simulator_real.py` / `simulator_real_trailing.py` OPRA strip
  (consistent with the wall SPY frame — by design, now explicit via `frame=`)
- `replay_heartbeat_core.py`, `replay_fleet_arms.py`,
  `validate_six_account_grid.py` (deliberate "parse EXACTLY like the
  orchestrator" parity)
- assorted `tools/`, `autoresearch/*_validate.py` one-offs (point-in-time
  artifacts — reclassify only if re-cited)

**UTC-CORRECT (unaffected):** `shotgun_scalper_grinder`, `chart_data_verify`,
`futures/*` (own data pipeline), `sweep_missed_*`, `sniper_matrix`,
`atr_regime_chandelier`, pressure-test conftest, orchestrator VIX align.

**DATE-ONLY-SAFE:** every `str[:10]` / utc-date extraction (dates agree in
both conventions).

**MIXED (flag for case-by-case check before re-citing):** files parsing SPY
naive but VIX utc (or vice versa) in one run — e.g. `watcher_live.py`
(SPY naive :264 / VIX utc :271), `eval_fleet_standalone_regime.py`
(naive↔naive: SPY wall + VIX true-ET = winter VIX 1h-ahead risk),
`gate_sweep_combinations.py`. None of these back a currently-armed param.

**LIVE paths are NOT CSV consumers** — the live engine reads fresh
beacon/Alpaca bars whose offsets are correct *today* (EDT). Before November:
verify the beacon's timestamp serialization writes real offsets (queued as a
re-validation follow-up).

## The fix (Phase A — shipped this commit)

1. **`backtest/lib/et_frame.py`** — canonical `parse_timestamp_et(series,
   frame)` with `FRAME_WALL_V1` (legacy, byte-reproducible) and `FRAME_ET_V2`
   (DST-correct). `DEFAULT_FRAME = wall-v1` until Phase B.
2. **`build_rth(spy, frame=...)`** and **`simulate_trade_real(...,
   frame=...)`** (+ trailing variant) thread the frame explicitly so the
   SPY↔OPRA join can never mix conventions; `family_grind.run_family/sim_cell/
   _run_null/_dir_null` thread it end-to-end.
3. **Writer fixed**: `extend_data_v2.utc_iso_to_et_string` emits real per-row
   offsets (`-0500`/`-0400`); `append_today` dedupe made mixed-offset-safe
   (utc=True scratch column, original strings preserved).
4. **8 guards** in `tests/test_et_frame_guards.py` pin: legacy winter clip
   (66@10:30), et-v2 restore (78@09:30), summer frame equality, build_rth
   threading, OPRA join frame-consistency, writer DST correctness, VIX master
   asymmetry, and default-stays-wall-v1-until-migration.

**NOT chosen:** rewriting master CSVs to true-ET naive — it would break every
currently-correct `utc=True` consumer and require regenerating 18 months of
data; the stored UTC instants are already correct.

## Re-validation plan (NO decision on et-v2 numbers before its diff is filed)

Runner: `backtest/autoresearch/frame_migration_revalidate.py` →
`analysis/frame-migration/frame-revalidation-stage{N}-{date}.json`.

- **Stage 1 (cheap, detector-level)** — 4 family detectors both frames, signal
  deltas clustered by month (expect Nov–Feb concentration; bollinger 316→360).
- **Stage 2 (heavy, real OPRA fills — after-hours only, single process,
  backtest venv = reaper-exempt)** — re-sim the family-grind ELITE cells both
  frames; diff n/exp/OOS/candidate-bar per cell. **WIRE-BOLLINGER must cite
  this before wiring any cell using et-v2 numbers.**
- **Stage 3 (orchestrator scope — separate task)** — the orchestrator RTH slice
  fix + re-run of anchor + A/B baselines (params ratifications sit on the wall
  frame; they measured a *consistent truncated* winter session, so they remain
  internally valid AS MEASURED — but must be re-validated before any NEW
  ratification cites winter data).
- **Before November:** verify beacon/live serialization offsets; flip
  `DEFAULT_FRAME` to et-v2 (Phase B) once Stage 1+2 diffs are filed — the
  `test_default_frame_is_wall_v1_until_migration` guard must be flipped in the
  same commit citing the diff reports.

## Affected-artifact ledger

`analysis/frame-migration/WALL-FRAME-SCORECARDS.json` — every validated
scorecard family sitting on the wall frame, with re-run priority. Rule:
**a wall-frame scorecard stays citable for wall-frame comparisons** (that is
why wall-v1 remains byte-reproducible) **but may not certify an et-v2 wiring
decision.**
