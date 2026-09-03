# PULLBACK-HOLD-BULL-TRIGGER -- forward shadow pre-registration (Lane B, 2026-09-03)

**Filed:** 2026-09-03 (Sonnet worker fire, queue item `PULLBACK-HOLD-BULL-TRIGGER`).
**Status: FROZEN BEFORE THE FIRST FORWARD LEDGER ROW WAS WRITTEN.** This document exists so the
forward shadow ledger (`analysis/recommendations/pullback-hold-shadow-ledger.jsonl`, written by
`setup/scripts/pullback_hold_shadow.py`) has a decision rule fixed BEFORE any of its own rows
existed -- no post-hoc tuning (C25), no peeking at the ledger to pick the bar.

## Relation to the prior, already-CLOSED Lane-B work

`PULLBACK-HOLD-BULL-TRIGGER` already ran one full Lane-B validation on 2026-07-22: a 36-cell
historical GRID replay of `filters.py::detect_pullback_hold_bullish` through
`exit_manager_walk`/`option_pricing_real`
(`analysis/recommendations/pullback-hold-bull-prereg-2026-07-22.json` ->
`pullback-hold-bull-stage-summary-2026-07-22.md`), which closed
**`status:CLOSED-LANE-B-NO-CELL-SHIPS`** -- an honest null (0/36 cells cleared both of J's named
exhibits as sanity anchors, 0/36 cleared BH-FDR q=0.10). That result stands; this document does
not reopen it or claim it was wrong.

This pre-registration covers a **structurally different, independent** Lane B for the
**new, standalone** detector in `backtest/lib/pullback_hold_detector.py` (zero shared code with
the frozen `filters.py` implementation -- see that module's docstring). Two differences from the
closed grid:

1. **Methodology:** a forward-going SHADOW LEDGER (day-over-day EOD scans as real sessions
   elapse) rather than a one-shot historical backtest grid. The closed grid's failure mode was
   that its up-structure CONFIRMATION layer (session-VWAP-crossing / 60-bar market-structure
   trend) was itself too laggy to see J's own earliest read -- this design removes that specific
   confirmation layer entirely and substitutes a 15-minute-HTF-not-BEAR qualifier plus
   levels-as-zones per-level `zone_width` (both untested by the closed grid).
2. **No grid search.** One frozen parameterization (below), not 36 cells -- this build does not
   repeat the multi-cell search that produced the prior null; it tests ONE specific hypothesis
   shape end to end.

## Frozen detector parameterization (do not hand-tune off any single exhibit -- C25)

| Constant | Value | Source |
|---|---|---|
| `zone_band_dollars` (default, per-level `zone_width` from key-levels.json overrides when present) | $0.30 | matches the existing `CONFLUENCE_TOLERANCE_DOLLARS` / `filters.py::PULLBACK_HOLD_ZONE_BAND_DOLLARS` precedent |
| `min_hold_bars` (K) | 3 bars | task spec, frozen; stricter than the closed grid's cells (which tested N=1,2,3) -- K=3 alone, not searched |
| `lookback_bars` | 12 bars (1 hour of 5-min bars) | matches `filters.py::PULLBACK_HOLD_LOOKBACK_BARS` precedent |
| HTF qualifier | 15-min ribbon stack (read-only from `orchestrator.py::_compute_htf_15m_stack` logic, or the ledger's own logged `htf_15m` field) must NOT be `BEAR`. `None`/`UNKNOWN` passes. | task spec |
| Hold rule | every bar's LOW (not just close) must sit inside `[level-band, level+band]` for the full hold window -- stricter than the closed detector's close-only floor check | task spec ("lows inside the band") |
| Reclaim rule | current bar CLOSE > zone ceiling (`level+band`) AND > highest close seen during the hold window | mirrors the closed detector's reclaim confirmation, applied to the new hold definition |

Implementation: `backtest/lib/pullback_hold_detector.py::detect_pullback_hold` /
`scan_session`. SHADOW-ONLY, zero imports from/into the live or backtest engine path (verified:
not referenced by `heartbeat_core.py`, `filters.py`, `orchestrator.py`'s live dispatch,
`strategies.py`, `build_shared_signal.py`, `risk_gate`, `exit_manager`, `fleet_executor`,
`fleet_live`).

## Forward outcome proxy (frozen, computed BEFORE any forward row)

Same walk-forward sign-only methodology as
`analysis/recommendations/bear-f8-vix-floor-sign-costing-2026-09-03.md`'s Population E
(entered-trade) read, mirrored to the BULL/calls side:

- **Baseline walk parameters**, estimated ONCE from the FULL-HISTORY set of core-arm
  (`safe-2`/`bold-2`) engine BULL (`right=="C"`) round trips, joined to their entry SPY spot via
  the nearest `core-decisions.jsonl` `ENTER_BULL` row (same account, within 120s before
  `entry_ts_et` -- unmatched trades disclosed-excluded, same tolerance rule as the bear-f8 doc):
  `n=44` matched of 62 core-arm engine bull trips (18 unmatched: no core-decisions match within
  tolerance or missing `hold_min`/`spy`).
    - `median_hold_min = 23.9`
    - `median_MFE = 0.60` (SPY points; calls profit as SPY rises, walked on
      `backtest/data/spy_5m_2026-05-19_2026-09-02.csv`, the only granularity available -- same
      5-minute-resolution disclosure as the bear-f8 doc)
    - `median_MAE = 0.58` (SPY points)
- **Per-fire outcome rule**, applied to each shadow-ledger fire using the ABOVE fixed medians
  (never the fire's own realized stats):
  - Window = `[trigger_ts, trigger_ts + 23.9min]`.
  - FAVOURABLE_price = `trigger_close + 0.60`.
  - ADVERSE_price = `trigger_close - 0.58`.
  - Walked bar-by-bar in time order. A bar whose high >= FAVOURABLE_price AND low > ADVERSE_price
    -> **FAVOURABLE**, stop. A bar whose low <= ADVERSE_price AND high < FAVOURABLE_price ->
    **ADVERSE**, stop. A bar touching BOTH -> **ADVERSE by pre-registered tie-break**
    (conservative against the hypothesis, cannot manufacture a positive read). Neither touched by
    session end (or by the ledger's own available forward bars, whichever is shorter) ->
    **UNSCORED_INSUFFICIENT_BARS**, excluded from the rate denominator and disclosed as such.

## Engine bull baseline (the bar this must clear)

Same walk applied to the ENTERED population -- every core-arm (`safe-2`/`bold-2`) engine BULL
trip, full history, using its OWN entry SPY spot and the SAME fixed medians above:
**n=44, FAVOURABLE=20, ADVERSE=17, FLAT=7 -> baseline favourable rate = 0.4545 (45.45%).**
Reproducible via the exact join/walk described above against
`analysis/trades-enriched.jsonl` + `automation/state/core-decisions.jsonl` +
`backtest/data/spy_5m_2026-05-19_2026-09-02.csv`.

## Decision rule (frozen)

- **Forward window opens 2026-09-03** (this filing's date) -- any session dated before
  2026-09-03 that the scanner also happens to score (it scans the FULL `core-decisions.jsonl`
  history it can reach, same as `day_throttle_shadow.py`'s `in_sample_reference` block) is
  reported separately as **in-sample reference only** and can NEVER clear the verdict, exactly
  the same no-peeking split `day_throttle_shadow.py` uses for its own `FORWARD_FIRST_DATE`. Only
  rows dated `>= 2026-09-03` count toward the forward floors and the forward statistic below.
- **Forward bar:** the ledger must accumulate **>= 30 scored trading sessions** (sessions where
  the detector had a full RTH scan available, whether or not it fired) **AND >= 25 scored fires**
  (FAVOURABLE+ADVERSE+FLAT, excluding UNSCORED_INSUFFICIENT_BARS) before any verdict is read.
  Below either threshold the ledger is MEASURING, not adjudicating -- `verdict_ready: false`.
- **Statistic:** session-clustered bootstrap on the FAVOURABLE rate (resample TRADING DAYS with
  replacement, not individual fires -- multiple same-day fires are correlated market moments, not
  independent draws), `numpy.random.default_rng(seed=1337)`, `n=2000` resamples, report the
  2.5th-percentile (CI-lower).
- **Ship-consideration bar (NOT an auto-ship gate):** CI-lower(2.5%) of the forward favourable
  rate > 0.4545 (the engine's own bull baseline, above). Clearing this bar makes the detector a
  **candidate** for the SAME structural pipeline the 07-22 grid used before any live wiring
  (real-fills replay through `exit_manager_walk`, full 4-condition gate + concentration + BH-FDR)
  -- it does NOT itself authorize wiring `triggers`/`bull_score`/`passed`.
- **No-peeking:** this rule, the two medians, and the baseline number above are frozen at file
  time (2026-09-03) and MUST NOT be edited to chase a result once forward rows exist. A cell that
  fails re-verification (e.g. `median_hold_min` recomputed differently after this filing) voids
  the window and requires a fresh, freshly-dated pre-registration -- not an edit to this one.

## Expansion discipline

**Nothing before 2026-10-30.** No live wiring, no parameter change to `filters.py`'s existing
shadow-logged `detect_pullback_hold_bullish`, no relaxation of the K/band/HTF constants above,
regardless of how the forward ledger reads before the 30-session/25-fire floor is reached. Any
change after 10-30 goes through its own frozen A/B, never a hand-loosening of this pre-reg.

## Scope / rail-4

Research-tool + JSON/JSONL/MD outputs only. No `params*.json`, `heartbeat_core.py`, `filters.py`,
`orchestrator.py`'s live dispatch, `risk_gate`, `exit_manager`, `fleet_executor`, `fleet_live`,
`strategies.py`, `build_shared_signal.py`, `CLAUDE.md` touched. No broker import, no OPRA fetch.
