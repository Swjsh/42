# FROZEN pre-registration — SSR v2 runner-leg exit (trail vs fixed cap)

**rule_id:** `ssr-v2-runner-exit-2026-09-03`
**status:** `FROZEN_PREREG` (no code exists yet; see `build_step` below — this file is DOCUMENT-ONLY per its own filing constraint, nothing on disk was edited to produce it)
**frozen_at_et:** 2026-09-03 04:43 ET (Thursday EDT, `et_clock.py` verified `market_hours=False` at freeze time)
**filed_by:** Sonnet, `automation/overnight/queue.md` items `SSR-REAL-BLOCKER-IS-EXIT-QUALITY-NOT-SIZING` (DIAGNOSED 04:40 ET 2026-09-03) and `SSR-FUNDABILITY-MEASURES-NOTIONAL-NOT-MARGIN` (CLOSED, reads UNPROVEN, 04:40 ET 2026-09-03)
**parent_finding:** `analysis/deep-research/SSR-EXIT-QUALITY-DECOMPOSITION-2026-09-03.md`

---

## 0. Hypothesis

Replacing the runner leg's **fixed profit cap** — "nearest opposing level beyond TP1, else a fixed 3R fallback, either way capped at 5R from entry" (`setup/scripts/ssr_shadow.py::_pick_runner`, lines 468–490; `RUNNER_FALLBACK_R_MULT = 3.0` line 259, `RUNNER_CAP_R_MULT = 5.0` line 260) — with a **trailing stop** on the final 1-of-3 contracts recovers most of the parent finding's **-$9,838.79 / 83% of gross downside** (4 trades: #4, #7, #15, #17 in the n=17 table) **without giving back the +$8,366.14 the current exit shape already earns on the other 10 trips** (stops net **+$2,662.77** vs null; time exits net **+$2,895.94** vs null — both legs are net-additive per the parent finding and are explicitly OUT OF SCOPE here, see §4).

This hypothesis is filed with an important disclosure the parent finding could not have known at diagnosis time (04:40 ET): the ssr-v2 respec (sizing-only, commit 77442e70, 2026-08-23) never touched exit code, so the SAME `_pick_runner`/`decide_bar_events` logic has been live in the ssr-v2 shadow lane for 11 days and has **already accrued n=16 current-spec round trips** as of this freeze (`automation/state/futures/ssr-shadow-progress.json`, `updated_et: 2026-09-03T04:30:00`): `total_pnl_usd = -$4,527.89`, `null_total_pnl_usd = -$3,340.85`, `beats_null = false`, `positive_expectancy = false`, `armable = false` (16/20 needed). **The queue item's predicted failure is already reproducing in real time on the current spec, not just in the retired n=17/18 ssr-v1 ledger the parent finding decomposed.** That existing v2 ledger is disclosed here as additional context, not as this prereg's test population — see §1.

## 1. Populations — two, kept strictly separate, neither retroactively merged

### 1a. IN-SAMPLE (already seen — hypothesis-generating only, never a verdict population)

The n=17 legacy (ssr-v1, retired spec) round trips the parent finding decomposed, plus the 18th trip it reports separately (n=18 total, `total_pnl_usd $32,140.01` vs `null $37,476.09`, gap **-$5,336.08**). **Disclosed explicitly as IN-SAMPLE**: this is the exact population the runner-cap hypothesis in §0 was read off of. Any number computed against it (e.g. "the trail would have recovered $X of the $9,838.79" as a backtest replay) is **hypothesis-generating only** — it may motivate the cell grid in §2 but **may not itself be cited as evidence the hypothesis is TRUE**, per this repo's standing no-peeking convention (same rule `vwap-family-killcheck-prereg-2026-08-18.json` and `exit-counterfactual-backfill-data-2026-09-03.md` both freeze). A run against 1a reports as `IN_SAMPLE_REPLAY`, never as `SHIP_CANDIDATE` or any arming-adjacent label.

### 1b. FORWARD (the only population that can ship anything)

A **fresh clock starting at this freeze**, counting only round trips whose `entry_time_et` (from `ssr_shadow.py::open_position`, the `_entry_event` row) is **strictly after 2026-09-03 04:43 ET**. This is deliberately NOT the same counter as the existing ssr-v2 `arming_bar` (`ARMING_MIN_ROUND_TRIPS = 20`, `ssr_shadow.py` line 263) — the 16 round trips already in that counter as of this freeze predate the variant recorder specified in §6 and were scored under a runner rule that never computed a trail/wide-cap counterfactual, so they cannot retroactively answer this question. They remain fully valid evidence for the **existing v2 arming_bar** (fixed-cap shape); they are simply not eligible to close out THIS prereg's clock.

**Frozen bar to unlock any verdict: >= 20 NEW round trips (post-freeze `entry_time_et`) AND >= 40 sessions (unique `date_et` calendar days between the freeze date and the last counted trip's `closed_at_et`, inclusive) — both conditions required, whichever clears later gates.** Sessions, not trading days elapsed, because SSR signals fire intermittently (per the parent finding's own per-trip table, several sessions produce zero qualifying signals) — a pure round-trip count with no session floor could in principle clear on an anomalously signal-dense handful of days, the same concentration risk `BACKTESTING-PLAYBOOK.md` §4.9 already warns against for thin-population families.

## 2. Frozen cells — two variant families, five cells, entry/stop/TP1 unchanged in every cell

Applies **only to the runner leg** (the final `RUN_QTY = 1` of 3 contracts, `ssr_shadow.py` lines 256–257) after TP1 (`TP1_QTY = 2` at `TP1_R_MULT = 1.5`, unchanged) has filled and the stop has moved to breakeven (unchanged). Entry, stop-to-breakeven, and TP1 sizing/pricing are byte-identical to the live shape in every cell — see §4.

| family | cell | rule | frozen knob |
|---|---|---|---|
| **A — chandelier trail** | A2 | trail stop = running high-water-mark (favor direction) minus `k * ATR14` | k=2 |
| | A3 | same | k=3 |
| | A4 | same | k=4 |
| **B — wide cap** | B8 | keep `_pick_runner`'s existing nearest-opposing-level-else-3R-fallback selection **unchanged**; only widen the cap | 8R (`RUNNER_CAP_R_MULT` analog = 8.0) |
| | B10 | same | 10R (`RUNNER_CAP_R_MULT` analog = 10.0) |

ATR source: `futures.swing_sim.wilder_atr` (already imported at `ssr_shadow.py` line 220, `ATR_PERIOD = 14` at line 252) — the SAME series the live detector already computes per config per poll (`_run_once_unlocked`, `atr = wilder_atr(bars, period=ATR_PERIOD)`), reused, never re-derived. Family A activates its trail only once the position is past TP1 (mirrors the live shape's own breakeven-stop timing, `decide_bar_events` post-TP1 branch, lines ~615–630) — pre-TP1 behavior (fixed stop, `REASON_STOPPED_PRE_TP1`) is untouched in every cell.

No sixth cell, no sweep beyond this grid, no post-hoc cell addition once §1b's forward clock starts accruing — a cell added after seeing forward data voids this prereg (same `no_peeking_rule` this repo's other forward preregs use).

## 3. Frozen metrics (computed per cell, per population, never blended across cells)

1. **Managed-vs-unmanaged-hold delta per trip** — reuses `ssr_shadow.py::compute_null_pnl` **unchanged** (same-direction full-qty unmanaged hold to the trip's own `close_bar_close`) as the null; `variant_total_pnl - null_total_pnl` per trip, summed per cell.
2. **`beats_null` rate** — fraction of individual trips (not just the aggregate sign) where the variant's per-trip P&L exceeds that trip's own null P&L, reported alongside (not instead of) the aggregate `beats_null` boolean `ssr_shadow.py::_null_check_block` already computes (reused unchanged for the aggregate figure).
3. **MAE of the trail** (family A only) — per trip, the running high-water-mark in R-multiples at the moment the trail stop fires, minus the trail-exit price in R-multiples (i.e., how much of the trip's own peak favorable excursion the trail gives back before triggering). Reported as a distribution (median + worst case), not a single mean — a mean-only figure is exactly the bare-verdict pattern `MONITORING-INSTRUMENTS-LACK-CONCENTRATION-GUARDS` (queue item, CLOSED 2026-09-03) flags across this repo.
4. **Giveback on winners** — for trips that closed favorably under BOTH the live fixed-cap shape and the variant, `(variant peak-favorable-excursion in $ − variant realized $)`, sourced from the same OPRA/futures bar path the ledger already walks (`walk_open_position`, `ssr_shadow.py` line 644) — never a separately-fetched bar set.
5. **Concentration term — drop-top-2 trips**: `backtest/lib/concentration.py::drop_top_n(records, n_drop=2)`, reused unchanged, applied to the per-trip variant-vs-null delta (not raw P&L) so a single anomalous trip cannot carry the verdict, matching this repo's `live_readiness.py` / `core_strategy_recency.py` concentration-gate precedent.
6. **CI-lower(2.5%) on the mean delta** — day-block bootstrap over the per-trip delta, resampling by `date_et` (not by trade — SSR's own trades cluster on signal-dense sessions, the same pseudo-replication risk `g5_day_block_bootstrap`'s own docstring names for the 5-arm engine). Reuses `setup/scripts/exit_policy_beats_null_2026_08_23.py::g5_day_block_bootstrap` (B=its existing default, seed=its existing default) unchanged, pointed at the variant-vs-null delta series instead of that module's own `recs`.

## 4. Verdict vocabulary

- **`SHIP_CANDIDATE`** — on the §1b FORWARD population only, at or after the §1b bar clears: a cell's `beats_null` is true on the aggregate AND its CI-lower(2.5%) (metric 6) is `> 0` AND its drop-top-2 delta (metric 5) is still `>= 0`. A `SHIP_CANDIDATE` cell is eligible for a SEPARATE ratification step (weekend, per OP-16/OP-22) — this prereg's clearing does NOT itself arm anything.
- **`NULL_HOLDS`** — the forward bar clears and no cell satisfies `SHIP_CANDIDATE`. Terminal for this prereg; a new prereg is required for any further runner-exit iteration (fresh cell grid, not a re-sweep of these five).
- **`UNDERPOWERED`** — the forward bar (§1b) has not yet cleared (either the round-trip count or the session count, or both). The only legitimate status while the clock is running; **no beats_null/CI/concentration number computed under this status may be cited as a verdict** (same `no_peeking_rule` violation this repo's other forward preregs guard against).
- **`IN_SAMPLE_REPLAY`** — any number computed against §1a. Hypothesis-generating only, per §1a; never upgraded to `SHIP_CANDIDATE` or `NULL_HOLDS` regardless of how it reads.
- **`VOID`** — the population window, cell grid, or forward bar is altered after forward data has started accruing. Requires a fresh prereg, not an edit to this one.

**Ship rule, stated once, unambiguously: `SHIP_CANDIDATE` requires `beats_null` TRUE on the FORWARD population (§1b) AND CI-lower(2.5%) `> 0` AND drop-top-2 `>= 0`. All three, on the forward population, or the answer is `NULL_HOLDS` / `UNDERPOWERED`.**

## 5. What does NOT change

- **Entries** — the SSR detector, its zone/sweep ATR multipliers, and the signal-selection watermark logic (`ssr_shadow.py::_select_new_signals`) are untouched. This prereg is exit-only.
- **Sizing** — `QTY = 3` per `ssr_shadow.py` (TP1_QTY=2, RUN_QTY=1) is unchanged in every cell. This is deliberate: per the queue item's own text, **"contract size has zero bearing on this failure"** (see §7 for the full statement) — the ssr-v2 respec already answered the sizing question (notional cut ~10x, `point_value_ratio_vs_full_size: 10.0` in `ssr-shadow-progress.json`'s `fundability` block) and it did not move `beats_null`, because sizing and exit-shape are orthogonal levers on this book.
- **TP1** — `TP1_R_MULT = 1.5` for `TP1_QTY = 2` of 3 contracts, and the stop's move to breakeven after TP1 fills, are unchanged in every cell (per §2). The parent finding found both legs net-additive; touching them here would be optimizing a leg the decomposition already cleared, the exact anti-pattern that finding's own "Guard against re-litigating stops/time-exits without cause" section warns against.
- **The 16:55 ET time-flatten** (`FLAT_HOUR_ET, FLAT_MINUTE_ET = 16, 55`) — unchanged. Net-additive per the parent finding (+$2,895.94, 0/17 trips show the hypothesized right-tail-cutting pattern).
- **Fundability** — `SSR-FUNDABILITY-MEASURES-NOTIONAL-NOT-MARGIN` closed 04:40 ET 2026-09-03 reading **UNPROVEN**: `setup/scripts/ssr_margin_check.py` exists and is GET-only, but the sandbox 502'd the margin-requirements endpoint 3/3 attempts and the account aggregate shows a stale $17,107 margin snapshot while flat, so per-symbol MNQ/MGC margin is `DATA_MISSING` and the gauge cannot read GREEN by construction. **Arming SSR into any live/paper-funded state requires BOTH this prereg reaching `SHIP_CANDIDATE` AND `ssr-fundability.json`'s gauge reading GREEN (overnight_ok) — neither alone is sufficient.** This prereg does not touch, re-run, or take a position on the margin question; it is named here only so a future reader does not mistake a `SHIP_CANDIDATE` exit-shape verdict for a green light to fund the lane.

## 6. `build_step` — the exit-variant recorder, which does NOT exist yet

**No code has been written for this prereg.** Verified this session: no match anywhere in the repo for the file/function named below.

```json
{
  "build_step": {
    "file": "setup/scripts/ssr_shadow_runner_variant_2026_09_03.py",
    "symbol": "compute_variant_round_trips",
    "must_contain": [
      "extends setup/scripts/ssr_shadow.py -- imports and reuses open_position, decide_bar_events's pre-TP1 branch, walk_open_position's bar-feeding loop, compute_round_trips, compute_null_pnl, and _null_check_block UNCHANGED; does NOT reimplement entry, stop, or TP1 logic a second time",
      "adds a NEW pure function, e.g. _pick_runner_variant(snapshot, entry, tp1, direction, r_points, atr_at_entry, variant) -> tuple[float, str], parallel to (never replacing) ssr_shadow.py::_pick_runner -- variant in {'trail_k2','trail_k3','trail_k4','cap_8r','cap_10r'} per the frozen cell grid in prereg section 2",
      "adds a NEW post-TP1 bar-walker for the trail family (cap family reuses decide_bar_events's existing post-TP1 branch unchanged, only the runner price differs) that tracks a running high-water-mark in the favor direction per open bar and exits the RUN_QTY=1 leg when price crosses high_water -+ k*ATR14 -- ATR sourced from futures.swing_sim.wilder_atr (ATR_PERIOD=14), the SAME series ssr_shadow.py's own _run_once_unlocked already computes per poll, passed in, never re-derived",
      "reads the SAME ledger ssr_shadow.py already writes (automation/state/futures/ssr-shadow-would-be.jsonl) for entry/stop/tp1/signal_ref/config per round trip -- does NOT re-run the SSR detector or refetch signals, only replays the EXIT leg against the position's own already-fetched bar path",
      "writes a SEPARATE output file (e.g. automation/state/futures/ssr-shadow-runner-variant.jsonl) -- NEVER writes to or mutates ssr-shadow-would-be.jsonl, ssr-shadow-state.json, or ssr-shadow-progress.json; the live v2 arming_bar (ARMING_MIN_ROUND_TRIPS=20, fixed-cap shape) must be completely unaffected by this recorder's existence or its numbers",
      "tags every output row with population in {'in_sample','forward'} per prereg section 1 (forward = entry_time_et strictly after 2026-09-03T04:43:00-04:00) and cell in {'trail_k2','trail_k3','trail_k4','cap_8r','cap_10r'} -- never blends cells or populations in a single aggregate row",
      "computes the six frozen metrics of prereg section 3 per (population, cell) -- reuses backtest/lib/concentration.py::drop_top_n(records, n_drop=2) and setup/scripts/exit_policy_beats_null_2026_08_23.py::g5_day_block_bootstrap unchanged for metrics 5 and 6; does not reimplement either",
      "REFUSES to emit SHIP_CANDIDATE/NULL_HOLDS for the forward population until BOTH >=20 forward round trips AND >=40 unique forward sessions are present -- returns UNDERPOWERED otherwise, gate enforced in code per prereg section 4, not left to the reader",
      "$0 cost -- reads bars already fetched by the live ssr_shadow.py poll (fetch_bars_light, cached), no new data source, no new order path, no exit-shape change to any live/paper position"
    ]
  }
}
```

## 7. The sizing red herring, stated explicitly

Per the queue item `SSR-REAL-BLOCKER-IS-EXIT-QUALITY-NOT-SIZING` (filed 2026-08-23, re-affirmed in its own 04:40 ET 2026-09-03 diagnosis entry): **"Contract size has zero bearing on that [failure] -- v2 restarts the clock at n=0 on IDENTICAL exit logic, so absent an exit change the most likely outcome is reproducing the same beats_null failure 20 round trips later."** This freeze independently confirms the prediction landed early: the ssr-v2 respec (micro contracts, ~10x notional reduction) is, as of this freeze, running the identical `_pick_runner`/`decide_bar_events` exit code and has produced `beats_null = false` at n=16 (§0) — the same qualitative failure the n=17/18 ssr-v1 ledger showed at full size. **No cell in §2 changes `QTY`, `TP1_QTY`, `RUN_QTY`, or any per-contract sizing constant.** A future reader who reaches for a sizing lever to fix this failure is re-litigating a question this repo has now tested twice (full-size and micro) with the same answer both times.

## 8. Falsification note

The honest way this prereg dies without a `SHIP_CANDIDATE`: SSR's signal rate stays as thin as the parent finding's own table shows (multiple sessions with zero qualifying trips), and the forward clock takes materially longer than 40 sessions to reach 20 new round trips — in which case `UNDERPOWERED` is the correct terminal status for a long stretch, not a reason to shrink the bar or blend in the pre-freeze v2 trips. If that happens, it is itself informative (SSR may not generate enough signal volume to validate ANY exit variant on a useful clock) and is worth its own queue item rather than a silent loosening of §1b.
