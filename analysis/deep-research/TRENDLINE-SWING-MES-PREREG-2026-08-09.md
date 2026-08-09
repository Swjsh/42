# Trendline Swing MES — Pre-Registration — 2026-08-09

> Frozen BEFORE any runner/geometry code is written. Committed as its own commit; the
> results doc/scorecard commit must be a git descendant of this one
> (`git merge-base --is-ancestor <this-commit> <results-commit>`). This is the ONE
> untested cell in the futures-swing kill pile — see "Why this cell" below.

## Why this cell (context, not re-litigation)

Two independent Phase-1 batteries already KILLED the 4H/daily multiday MES swing thesis:
- 2026-07-02 (RTH-5m-signal/ETH-5m-fill): `DOES_NOT_TRANSFER`, 0/12 cells.
- 2026-07-09 (daily + 4h-of-RTH, `swing_sim.py`): KILL all 3 seeds (`rrw_short`,
  `e2_context`, `structure_bos_choch`), 0/96 cells. Full account:
  `analysis/recommendations/futures-swing-phase1-summary.md`.

None of the 96 tested cells was a trendline setup. `analysis/deep-research/
TORI-TRENDLINE-RESEARCH-2026-08-09.md` documents a public, genuinely mechanical 4H-swing
trendline method (Victoria Duke / "Tori Trades") whose rule set is native to the EXACT
timeframe this thesis needs (4H entry, daily/weekly bias, multi-week line maturity) — the
opposite situation from that same doc's finding that her numbers do NOT transfer to 5m
0DTE SPY (Phase 4 §3b). That asymmetry — wrong fit for 0DTE, natural fit for MES swing —
is the entire justification for spending a third battery pass on this instrument. This
document pre-registers that pass. Per the work order: **use the externally-specified
rule as the default parameterization** (a genuine overfitting defense, since we did not
fit these numbers to this data) and **the SAME PASS gate the prior two batteries used**
— no friendlier bar for the one seed we hope works.

## Data

- Source: `backtest/data/futures/MES_1m_continuous.csv` (Databento GLBX.MDP3 back-adjusted
  continuous, verified full ETH Globex, 508,586 1m bars, 2025-01-01→2026-06-12 — same cache
  the prior two batteries used, re-verified this session: 367 daily bars, 721 4h-of-RTH bars).
- Bars: `futures.data.resample_4h_rth` (2 bars/session, [09:30,13:30) + [13:30,16:00) —
  the PRIMARY signal+trade timeframe, matching Tori's stated native execution timeframe
  exactly, so — unlike the 0DTE adaptation problem — NO rescaling of her touch-spacing/
  duration numbers is required here) and `futures.data.resample_daily` (bias-filter only).
- IS/OOS split: **2026-01-01** (identical cutoff to both prior batteries). IS: 496 4h bars
  / 253 daily bars. OOS: 225 4h bars / 114 daily bars.
- Instrument: MES, $5/pt (`futures.instruments.MES`).
- Costs: `cost_per_side_usd=2.50` ⇒ **$5.00/round-turn**, 1 contract — identical to both
  prior batteries.
- No yfinance gap-fill extension this pass (native Databento window only, through
  2026-06-12) — matches the prior battery's `structure_bos_choch` seed's own scope
  (4h data can't be extended by a daily-only yfinance proxy), disclosed there and here.

## Validity grammar and its source

Source: `analysis/deep-research/TORI-TRENDLINE-RESEARCH-2026-08-09.md`, Phase 2
"Trendline validity rules" (triangulated from 3 independently-written derivative
summaries of one underlying free playbook — see that doc's sourcing caveat). Rules below
are used **as pre-registered defaults**, not fitted; anywhere a literal number has no
mechanical equivalent in a backtest, the operationalization is disclosed explicitly (not
silently invented) per the same doc's own Phase 4 §3b warning against unrescaled literal
copies.

| Rule (as stated) | Status here | Value |
|---|---|---|
| Anchor: wicks only, never mixed with bodies | Literal (also J's own hard rule) | bar high (resistance) / bar low (support) |
| Min touches: 3 | Literal, frozen (not gridded) | 3 |
| Min spacing between touches: 6+ candles | Literal, frozen — **native units**, no rescaling (bars ARE 4h) | >= 6 bars |
| Line duration: 3+ weeks | Literal, frozen — native units | >= 30 bars (3wk x 5d x 2 bars/day) |
| Slope: < 45 degrees at 3-month zoom | **Operationalized, disclosed** — "45 degrees at a chart zoom" has no absolute geometric meaning without a defined price/time pixel scale (the source doc's own Phase 4 §3b flags this as inherently visual/discretionary). Operationalization: tan(45 deg)=1, so cap the line's rise-per-bar at 1x the market's own typical rise-per-bar, using mean Wilder ATR(14) over the line's span as the per-bar volatility unit. | `abs(slope_pts_per_bar) < mean(ATR14 over line span)` |
| Timeframe: 4H chart, daily/weekly top-down bias | Literal for the 4H part (native). Bias operationalized: no weekly resample exists in this repo; bias = daily close vs daily EMA(20) direction (long only if close > EMA20 AND EMA20 rose over the prior 5 daily bars; short symmetric). **Frozen ON for the primary/official battery.** A bias-OFF run is a disclosed robustness check only (see "Scope decisions" below) — NOT part of the official BH-FDR family, to avoid inflating the multiple-testing family with a redundant axis decided after the fact. | daily EMA(20) trend agreement |
| One attempt per line | **Deviated, disclosed** — NOT applied. Per this project's own standing lesson (kill unvalidated re-entry locks without evidence — cited explicitly in the Tori research doc Phase 4a, and in project memory "Kill re-entry lock + gate provenance": unvalidated Claude-invented locks get deleted, every gate needs provenance+evidence or dies), a re-entry cap is a hypothesis to test, not a rule to import on authority. Not applying it is the doctrinally-consistent default; testing it is future work if this seed ever clears. | not applied |
| Touch tolerance (numeric) | Not stated by the source (not one of her published numbers) — **frozen, not gridded**, chosen for consistency with the ALREADY-LIVE, already-validated SPY bear-side trendline detector's own tolerance (`detect_trendline_rejection_bearish`, `backtest/lib/filters.py:601`, `proximity_pct=0.0010`) rather than inventing a fresh number. | 0.10% of price |
| Swing-point fractal window | Not stated by the source (an implementation nuisance parameter every trendline detector needs) — **gridded**, matching the prior `structure_bos_choch` seed's own window grid for internal consistency. | {2, 3} bars each side |

## Entry trigger variants (grid axis, 3 values — matches the work order's explicit ask)

1. **`bounce`** — a bar's wick touches the line within tolerance (low near support /
   high near resistance) AND that same bar's close is back beyond the line by more than
   tolerance (confirms rejection in one bar, wick-only criterion — no body/wick mixing).
   Entry at the NEXT bar's open, in the bounce direction (off support = long, off
   resistance = short). Matches Tori's stated Bounce setup ("enter at the touch itself,
   once the line is validated").
2. **`break`** — a bar CLOSES beyond the line by more than tolerance (through support =
   short, through resistance = long). Entry at the next bar's open (this codebase's
   universal next-bar-open convention — avoids the same-bar-close look-ahead a market-
   order-on-the-close would require). Matches her stated Break setup.
3. **`break_retest`** — after a qualifying `break` bar at index j, scan bars j+1..j+10:
   the first bar where price returns within tolerance of the (role-flipped) line AND
   closes continuing in the break direction fires the signal (entry at that bar's next
   open). Skipped (no signal) if no retest occurs within 10 bars. This is the "break and
   retest" variant named explicitly in the work order.

## Stop shape (grid axis, 2 values — matches the work order's explicit ask)

Both variants are implemented via `backtest.futures.swing_sim.simulate_swing`
**completely unmodified**, exploiting its documented contract that `atr_at_entry` is a
caller-supplied point-distance, not necessarily a real Wilder ATR value (module
docstring: "`atr_at_entry` is a CALLER-supplied value"). This is not a workaround — it is
using the function exactly as designed, so both stop shapes flow through the SAME
gap-aware fill logic (`swing_sim.py`'s documented open-checked-first, stop-before-target
convention) with zero risk of a second, subtly-different fill engine.

- **`atr`** — `atr_at_entry` = real Wilder ATR(14) on the 4h bars (`swing_sim.wilder_atr`,
  unmodified). `stop_mult=1.5`, `target_mult=3.0` — the exact `battery.py`
  `DEFAULT_STOP_MULT`/`DEFAULT_TARGET_MULT` the prior 3 seeds used, unchanged, so this
  variant isolates "does trendline entry TIMING beat RRW/E2/structure entry timing,"
  holding exit mechanics constant against the prior kills.
- **`safety_line`** — `atr_at_entry` = the point-distance from entry price to the Safety
  Line's projected price at entry. `stop_mult=1.0` (stop = exactly at the safety line);
  `target_mult=2.0` (matches Tori's explicit "2R or better" MINIMUM for the Break setup —
  used as a fixed target for BOTH setups, a disclosed simplification of her actual rule,
  which is "trail as new swings form" for Bounce and "first S/R offering 2R+" for Break;
  neither is mechanically specifiable without a full trailing-stop or S/R-scanning system
  that doesn't exist in this repo — collapsing both to a fixed 2R is the honest
  simplification, not a silent one).
  - Safety Line construction for `bounce`: the Action Line itself (matches her rule
    exactly — "the line itself; a close-through invalidates" — no channel search needed).
  - Safety Line construction for `break`/`break_retest`: a parallel channel line — same
    slope as the Action Line, anchored through the most extreme OPPOSING-kind swing point
    within the Action Line's own touch span (support's opposing kind = swing highs, and
    vice versa). This operationalizes "the opposing/parallel trendline" from the source
    doc's own Phase 4 §3a framing. **If no opposing swing point exists in that span, the
    signal is EXCLUDED from `safety_line` cells only** (disclosed + counted in the results
    doc) — the `atr` stop-shape cells still include it, since that path never needed a
    safety line.

## Target rule

Covered above (target_mult=3.0×ATR for the `atr` stop shape; target_mult=2.0×safety-line-
distance, i.e. a fixed 2R, for the `safety_line` stop shape). No trailing-target variant
is tested this pass (out of scope — `swing_sim.simulate_swing`'s fixed-target contract
doesn't support trailing; a trailing exit would need new simulator code, which the work
order's "run it through the EXISTING machinery" instruction argues against building
before this cheaper, machinery-native test has even cleared IS).

## Horizon

1-5 trading days, expressed in native 4h-bar units (2 bars/RTH session): `(2 bars, "1d")`,
`(6 bars, "3d")`, `(10 bars, "5d")` — identical horizon-bar mapping to the prior battery's
`structure_bos_choch` seed (`H4_HORIZONS`).

## Grid summary

`window` {2,3} x `entry_trigger` {bounce, break, break_retest} x `stop_shape` {atr,
safety_line} = **12 combos**. x 2 directions x 3 horizons = **72 official cells**
(daily-bias filter ON, frozen). Small by design — every axis either reproduces a number
Tori states explicitly, or is a minimal, disclosed implementation nuisance parameter
(fractal window, touch tolerance) already precedented elsewhere in this codebase. This is
about 1.5x `rrw_short`'s cell count (48) and 2x `structure_bos_choch`'s (36) — bigger
because this seed genuinely varies one more independent axis (stop shape) the priors
never tested, not because of a blind parameter sweep.

## Scope decisions (pre-committed, not chosen after seeing results)

- `MIN_OOS_N = 5` — identical pre-committed threshold to both prior batteries
  (`battery.MIN_OOS_N`). Cells below this are reported in the full JSON, never a PASS.
- BH-FDR (alpha=0.05) computed across **all 72 official cells together**, one family per
  seed — same discipline as the prior batteries.
- VIX regime split (>=/< 17.5) reported per cell — same as prior batteries
  (`battery._regime_split`, reused unmodified).
- Daily-bias-filter-OFF is run and reported as a **disclosed robustness check only**,
  clearly labeled, outside the official 72-cell BH-FDR family. Decided here, before any
  code exists, specifically to prevent a post-hoc "turn the bias filter off until
  something clears" pattern.
- No exit-shape gridding beyond the two stop_shape variants above (fixed
  stop_mult/target_mult per shape, not swept) — consistent with the prior battery's own
  disclosed decision not to re-sweep exit shape ("the exit knob doesn't rescue a losing
  signal" — futures-swing-phase1-summary.md).

## PASS gate — UNCHANGED, verbatim from the prior two batteries

A CELL clears iff:

```
oos_mean > 0  AND  bh_fdr_survivor (alpha=0.05)  AND  oos_mean > buy_and_hold_mean
```

(buy-and-hold-same-horizon computed via `swing_sim.simulate_buy_and_hold`, unmodified, on
the identical OOS entry bars/direction/horizon — this IS the "beats buy-and-hold" null
check the work order asks to re-run.) A SEED's verdict is **PASS** iff >=1 of the 72
official cells clears; otherwise **KILL**. No friendlier bar than the prior two batteries
— this is the explicit point of the exercise.

## Implementation plan (not yet written as of this commit)

- `backtest/futures/trendline_geometry.py` — LOCAL geometry (per file-ownership boundary:
  `backtest/lib/trendline_detector.py` does not exist and is reserved for a sibling agent;
  this module lives under `backtest/futures/` instead, duplicating rather than touching
  that path). Causal swing-point confirmation (reuses the already-tested
  `crypto.lib.trendlines.find_swing_points` primitive, same no-look-ahead convention as
  `structure_seed.py`: a swing at bar j is only usable starting at bar j+window), event-
  driven candidate-line generation + validity filter, safety-line construction.
- `backtest/futures/seeds/trendline_swing_seed.py` — signal generation (grid x entry
  triggers x bias filter) + a battery-cell orchestrator that reuses `swing_sim.
  simulate_swing`/`simulate_buy_and_hold`/`wilder_atr` and `battery.bh_fdr`/
  `bootstrap_null_pvalue`/`build_null_pool` (all PUBLIC, unmodified functions) directly.
  `atr`-stop-shape cells reuse `battery.run_cell` verbatim (zero new statistical code).
  `safety_line`-stop-shape cells use a parallel cell function (mirrors `run_cell`'s
  structure exactly, documented as such) because the stop distance is PER-SIGNAL (a
  property of which specific line fired), not a single shared per-bar series like ATR —
  `battery.run_cell`'s per-bar-indexed lookup can't represent that, so reusing it verbatim
  isn't possible for this half of the grid without risking silently wrong per-trade stops.
  **`backtest/futures/battery.py` and `swing_sim.py` are NOT edited** — everything above
  is additive, in new files only.
- `backtest/futures/run_trendline_swing_battery.py` — orchestrator (load data, run both
  grids, write the scorecard JSON + append a `data-versions.jsonl` provenance row).
- `backtest/tests/test_trendline_swing_seed.py` — causal/no-look-ahead regression test
  (same pattern as `TestStructureSeedNoLookahead`), validity-rule unit tests on synthetic
  bars, entry-trigger unit tests, a real-data smoke test.
- Outputs: `analysis/deep-research/TRENDLINE-SWING-MES-2026-08-09.md` (full disclosure,
  same standard as `futures-swing-phase1-summary.md`) + `analysis/recommendations/
  futures-swing-trendline.json` (scorecard).

## Commit-order proof

This document is committed by itself, before any of the files listed under
"Implementation plan" exist. Verify with:

```
git log --oneline -- analysis/deep-research/TRENDLINE-SWING-MES-PREREG-2026-08-09.md
git merge-base --is-ancestor <this-prereg-commit> <results-commit> && echo "prereg predates results"
```
