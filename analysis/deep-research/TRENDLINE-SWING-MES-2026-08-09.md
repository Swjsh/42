# Trendline Swing MES — Results — 2026-08-09

> **MECHANICAL GATE VERDICT: PASS.** 5 of 72 pre-registered cells clear (oos_mean>0 AND
> BH-FDR survivor at alpha=0.05 AND beats buy-and-hold-same-horizon), reported exactly as
> the frozen prereg defined it — not redefined after seeing results.
>
> **PRACTICAL VERDICT: PASS_BUT_NOT_TRUSTED — treat as a KILL for any build decision.**
> Applying the SAME beyond-the-gate scrutiny this project's own prior batteries use (VIX
> regime concentration, IS/OOS sign stability, how many of "5 clearing cells" are actually
> independent, sensitivity to one disclosed robustness toggle) shows this PASS does not
> represent a validated, repeatable edge. Full reasoning below. **The 4H multi-day MES
> swing thesis has now been tested three independent ways (2026-07-02, 2026-07-09, this
> pass) and none has produced trustworthy evidence — do not build the futures swing lane
> on it.**
>
> Run: 2026-08-09, `backtest/futures/run_trendline_swing_battery.py`, `backtest/.venv`,
> ~16s runtime, $0. Prereg (frozen and committed BEFORE any runner code existed — commit
> `2f4eed3a`): `analysis/deep-research/TRENDLINE-SWING-MES-PREREG-2026-08-09.md`. Same
> source data as both prior batteries: `backtest/data/futures/MES_1m_continuous.csv`
> (Databento GLBX.MDP3, 508,586 1m bars, verified full ETH Globex, 2025-01-01→2026-06-12).

## Why this run happened

Two prior Phase-1 batteries killed the 4H/daily MES multiday swing thesis (0/12 cells
2026-07-02, `DOES_NOT_TRANSFER`; 0/96 cells 2026-07-09, KILL all 3 seeds — full account:
`analysis/recommendations/futures-swing-phase1-summary.md`). Neither tested a trendline
setup. `analysis/deep-research/TORI-TRENDLINE-RESEARCH-2026-08-09.md` documents a public,
genuinely mechanical 4H-swing trendline method whose native timeframe matches this thesis
exactly (unlike its poor fit for 5m 0DTE SPY). This was the one untested cell, run as a
third, independent pass.

## What I found, in order

### 1. A first run showed 7/72 clearing — and it was significantly inflated by a bug

The first complete run of the battery (bias filter ON) returned **7/72 cells clearing**,
with the two best-looking cells at OOS n=19 and n=13. Before trusting that number, I ran
the `/fable-too-good` protocol (mandatory for any surprising result, doubly so for a PASS
after two prior kills). Pulling the raw per-trade dates for the top cells immediately
surfaced a real implementation bug: **multiple geometrically-valid-but-overlapping
trendlines were firing the identical (direction, signal_bar_idx) event**, so the same
real-world market touch was being counted as 2, 3, or up to **9 separate "trades."**
Example: 2026-02-20 bar_idx=564 appeared 4 times in one cell's OOS trade list, each with
the byte-identical $35.00 P&L (same entry, same exit — literally the same trade).

Across all 12 official combos this was systemic: **820 raw signal rows collapsed to only
458 truly distinct (combo, direction, bar) events** — 202 of 458 keys had more than one
duplicate, one key had 9. This is pseudo-replication: the bootstrap-null p-value and the
BH-FDR correction both assume independent draws, and duplicate-of-the-same-bar rows are
not independent evidence — they are the same evidence counted multiple times, which
mechanically inflates apparent significance and artificially clears `MIN_OOS_N`.

**Fixed properly, not just disclosed**: `generate_signals` now collapses to one signal
per `(combo_id, direction, signal_bar_idx)`, keeping the highest-touch-count line's
version when duplicates occur (a principled tie-break — `find_trendlines` already returns
lines sorted by touch-count descending, so `keep="first"` prefers the best-validated line,
not an arbitrary one). Regression test proving the fix actually fires (and would fail
without it): `backtest/tests/test_trendline_swing_seed.py::TestNoDoubleCounting`. Also
found and fixed in the same pass: an inverted opposing-swing-kind lookup in the
Safety-Line construction (`"swing_low" if kind=="support"` should be `"swing_high"` — the
OPPOSING kind, not the same kind) — caught by
`TestSafetyLine::test_break_with_no_opposing_swing_returns_none` before any real-data run.

**After the fix: 458 signals (was 820), 5/72 cells clear (was 7/72).** The verdict stayed
mechanically PASS, but a materially different, smaller PASS — itself a useful data point
about how much of the original 7-cell result was measurement artifact (2 of 7 cells,
~29%, evaporated from the bug fix alone).

### 2. The 5 surviving cells, in full

| combo_id | dir | horizon | stop | IS n/mean | OOS n/mean/WR | null p | BH-FDR | beats B&H | B&H mean |
|---|---|---|---|---|---|---|---|---|---|
| `tl_w2_bounce_atr` | short | 3d | atr | 6 / $460.40 | 9 / $347.21 / 77.8% | 0.012 | survive | yes | $192.36 |
| `tl_w2_bounce_atr` | short | 5d | atr | 6 / $25.18 | 9 / $465.97 / 88.9% | 0.007 | survive | yes | $125.56 |
| `tl_w2_bounce_safety_line` | short | 3d | safety_line | 6 / $114.72 | 9 / $225.13 / 55.6% | 0.0075 | survive | yes | $192.36 |
| `tl_w3_bounce_safety_line` | short | 3d | safety_line | **0 / n/a** | 7 / $274.25 / 71.4% | 0.0085 | survive | yes | $58.57 |
| `tl_w3_break_retest_atr` | long | 5d | atr | 4 / **-$43.95** | 13 / $360.36 / 76.9% | 0.004 | survive | yes | $333.37 |

Every cell here beats its own buy-and-hold-same-horizon benchmark (the null check the
work order asked to re-run) — that is a genuine point of difference from the prior
battery's Seed B (E2 context), whose apparent OOS edge was fully explained by simply
holding through the window. This is not pure beta. But four other problems, found by
applying the exact depth of scrutiny this project's prior batteries model, undermine it:

### 3. Only 2 real, independent discoveries hide behind "5 clearing cells"

Grouping by `(window, entry_trigger, direction)` gives 3 nominal families — but that key
is too coarse. I pulled the actual OOS entry **dates** for the two `bounce short`
families (window=2 and window=3, both flagged as separately "clearing"):

- `tl_w2_bounce_atr short`: 9 trades / **8 distinct dates**, 2026-02-20 → 2026-04-06.
- `tl_w3_bounce_atr short` (same underlying population feeding the w3 safety_line cell):
  13 raw / **7 distinct dates**, 2026-02-20 → 2026-04-06.
- **6 of the w3 line's 7 distinct dates are also in the w2 line's 8-date set.** Window=2
  and window=3 are not independent confirmations here — they are two fractal-sensitivity
  settings mostly re-detecting the SAME roughly 8-9 real market touches in the SAME
  6.5-week stretch. Reflects the same finding the 2026-07-09 battery's own `structure_seed`
  disclosure made about its own window knob ("window=2 fires far more than window=3...
  neither knob shows a stable direction of effect").
- The `tl_w3_break_retest_atr long` cell is genuinely separate: 13 trades / **12 distinct
  dates**, 2026-04-10 → 2026-06-02 — a different direction, a different (and immediately
  adjacent, non-overlapping) 7.5-week stretch.

So the real evidentiary base behind "5 clearing cells" is **two clusters of real market
touches** — about 8-9 short-side events in a 6.5-week window, and about 12-13 long-side
events in the following 7.5-week window — each graded 2-3 ways by horizon/stop-shape.
BH-FDR correctly controls for the 72 CELLS tested; it cannot and does not control for this
within-family correlation, because the cells it corrected were never truly independent
observations to begin with.

### 4. Every clearing cell is concentrated in one VIX regime — and worse this time

| combo_id (dir/horizon) | OOS n | VIX<17.5 n | VIX>=17.5 n | % high-VIX |
|---|---|---|---|---|
| `tl_w2_bounce_atr` short 3d | 9 | 0 | 9 | 100% |
| `tl_w2_bounce_atr` short 5d | 9 | 0 | 9 | 100% |
| `tl_w2_bounce_safety_line` short 3d | 9 | 0 | 9 | 100% |
| `tl_w3_bounce_safety_line` short 3d | 7 | 0 | 7 | 100% |
| `tl_w3_break_retest_atr` long 5d | 13 | 3 | 10 | 76.9% |

This is the identical signature `futures-swing-phase1-summary.md` used to kill Seed B
(E2 context): "every seed's better-looking cells concentrate in the higher-VIX /
bigger-trend-day bucket — consistent with 'caught some of 2026 H1's drift,' not with a
repeatable pattern-based edge." **Steelmanning the other side first**, because it deserves
airtime: trendline bounce/break-retest patterns are arguably supposed to concentrate in
higher-vol, more-directional stretches — a dead, range-bound market gives a trendline
strategy nothing to catch, so VIX concentration alone isn't automatically damning the way
it was for E2's at-level+VWAP context (a signal with no directional-regime story behind
it). That is a fair point and the reason this isn't reported as a clean mechanical kill.
But it doesn't rescue the result given points 3, 5, and 6 below, which are VIX-regime-
independent problems.

### 5. One of the two real clusters shows the exact IS/OOS instability signature that killed Seed B

`tl_w3_break_retest_atr long 5d`: **IS mean = -$43.95 (n=4, negative) → OOS mean =
+$360.36 (n=13)**. A sign flip from negative in-sample to positive out-of-sample, on a
sub-`MIN_OOS_N` in-sample count (n=4 < 5) — structurally the same shape as the E2 seed's
"IS is negative... OOS flips positive... 9 of 12 eligible cells flip sign IS→OOS" finding
that killed it. The other real cluster (`bounce short`, window=2) does NOT show this
problem — its IS mean is positive and same-signed as OOS across all 3 of its cells — which
is a genuine point in its favor, but note `tl_w3_bounce_safety_line` has **zero in-sample
trades at all** (IS n=0), meaning there is no track record whatsoever to check that
specific cell's stability against.

### 6. The result does not survive its own disclosed robustness check

The daily-bias-filter toggle was pre-registered as informational-only specifically to
avoid a post-hoc "turn a knob until something clears" pattern. Turning it OFF changes the
answer completely: 2/72 cells would clear, and **zero of those 2 cells' underlying
`(window, entry_trigger, direction)` families overlap with the 3 families behind the
official 5** — different combos (`break_retest` at 1-day horizon for both windows,
entirely absent from the official clearing set) and a genuinely different, more balanced
regime mix (3 of 18 and 3 of 20 trades in the low-VIX bucket, vs. 0 in most official
cells). A single reasonable, pre-declared methodological choice fully changes which cells
"work." That is the textbook fits-noise signature this project's own debugging doctrine
warns about ("it got better/changed with each variant" — H3 of the too-good-to-be-true
protocol), not a stable pattern surviving a sanity check.

### 7. Concentration within each cluster

`drop_top3_oos_pnl` (battery.py's built-in concentration check, on the `atr`-stop cells):
`tl_w2_bounce_atr` 5d drops from $4,193.72 to $1,407.54 with the top 3 trades removed
(66% of the cell's entire OOS P&L from 3 of 9 trades); `tl_w3_break_retest_atr` 5d drops
from $4,684.65 to $2,013.06 (57% from 3 of 13 trades). Not a single-trade fluke, but
consistent with a small, lumpy sample rather than a broad, repeatable edge.

## Cross-check against both prior batteries

| | 2026-07-02 (5m-signal) | 2026-07-09 (daily/4h-signal, 3 seeds) | 2026-08-09 (this pass, trendline) |
|---|---|---|---|
| Mechanical gate | 0/12 cells | 0/96 cells | 5/72 cells (PASS) |
| VIX-regime concentration | n/a (never reached test) | ubiquitous across all 3 seeds' best cells | ubiquitous across all 5 clearing cells |
| IS/OOS sign stability | train-negative, never reached test | 9/12 E2 cells flip sign; structure's best cell fails BH-FDR outright | 1 of 2 real clusters flips sign (same shape as E2) |
| Beats buy-and-hold | n/a | fails in every top cell examined (E2's "edge" was pure beta) | **passes** in every clearing cell (genuine point of difference) |
| Robustness to a disclosed toggle | n/a | not tested | **fails** — zero population overlap bias-on vs bias-off |
| Practical verdict | DOES_NOT_TRANSFER | KILL, all 3 | **PASS_BUT_NOT_TRUSTED** (treat as KILL for build decisions) |

Three independent passes, three different methodologies, the same practical bottom line:
**nothing in this kill pile survives full-depth scrutiny.** This pass is meaningfully
different in texture from the prior two (it clears the mechanical gate and beats
buy-and-hold, which the priors never did) but fails on population-independence,
IS/OOS-stability, and robustness-toggle grounds severely enough that treating it as a
validated edge would repeat exactly the mistake this project's own eval-first doctrine
(OP-16: "sub_window_stable AND anchor_no_regression") exists to prevent.

## Disclosures

- **Grid** (pre-registered, not expanded post-hoc): `window` {2,3} x `entry_trigger`
  {bounce, break, break_retest} x `stop_shape` {atr, safety_line} = 12 combos x 2
  directions x 3 horizons = 72 official cells, bias filter frozen ON. Bias-filter-OFF (12
  combos, 72 cells) ran as the pre-declared robustness check only, per prereg section
  "Scope decisions."
- **Safety-Line exclusion never actually triggered on real data** (0 of 556 break/
  break_retest events lacked an opposing swing point in span) — disclosed as a real,
  verified property of this run (checked directly, not assumed): with 315 valid lines
  found across both windows and 84-98 swing points per kind over 721 bars, spans wide
  enough to require an opposing extremum almost always contained one. This means the
  `atr` and `safety_line` stop-shape variants share an identical entry population for
  break/break_retest combos in this run, differing only in exit mechanics.
  `mean_stop_dist_pts_oos` for the two safety_line clearing cells (30.2pt, 36.0pt) is a
  sane multi-day risk distance on MES ~6000, not a degenerate near-zero stop.
  `find_opposing_safety_line` returning `None` when genuinely absent is unit-tested.
- **315 valid trendlines found** across both windows over the 721-bar file (84-98 swing
  points per kind) — a mechanical, exhaustive-pairs search finds every geometrically
  valid line, not just the 1-3 a discretionary trader would actively watch. This is
  consistent with how this codebase's OWN live SPY detector (`backtest/lib/trendlines.py`)
  and the prior battery's structure seed both work (exhaustive candidate generation, then
  filter/dedupe) — not a departure, but worth flagging as a difference from how a human
  chart-reader would scope "the" trendline.
  `find_trendlines`/`_dedupe_lines`: `backtest/futures/trendline_geometry.py`.
- **No look-ahead**: swing points are computed once over the full bar array (same
  precedent as `structure_seed.py`'s `walk_structure` usage) but only consumed from
  `bar_index + window` onward; the daily bias filter reads only the prior CLOSED session.
  Regression-tested: `TestNoLookahead` (mutates the tail, proves the head is unchanged).
- **Costs/split**: `cost_per_side_usd=2.50` ($5.00/round-turn), 1 MES contract, IS/OOS
  split 2026-01-01 — identical to both prior batteries. `atr` stop-shape uses
  `stop_mult=1.5`/`target_mult=3.0` (battery.py defaults, unchanged, matching the prior
  seeds' exit shape exactly). `safety_line` stop-shape uses `stop_mult=1.0`/`target_mult=
  2.0` (matches Tori's stated "2R or better" floor).
- **Native Databento window only** (through 2026-06-12) — no yfinance gap-fill extension,
  matching the prior battery's own disclosed 4h-scope limit (VWAP/4h resampling both need
  intraday RTH bars the yfinance daily gap-fill can't provide).
- **`backtest/futures/battery.py` and `swing_sim.py` were NOT edited** — the `atr`
  stop-shape cells call `battery.run_cell` verbatim; the `safety_line` stop-shape cells
  use a parallel function (`run_cell_variable_stop`) because the stop distance is
  per-signal, not a single shared per-bar Series the way ATR is — reusing `run_cell`
  verbatim for that half of the grid would have risked silently wrong per-trade stops
  (see `backtest/futures/seeds/trendline_swing_seed.py` module docstring for the full
  reasoning). `backtest/lib/trendline_detector.py` (sibling-owned) does not exist and was
  not touched; geometry lives locally in `backtest/futures/trendline_geometry.py`,
  disclosed duplication with `backtest/lib/trendlines.py` (live SPY detector) and
  `crypto/lib/trendlines.py` (swing-point primitive, reused directly) flagged for later
  consolidation, per the work order.

## Recommendation — what this leaves

**Do not build the futures swing lane on this.** Three independent methodologies across
two months of research effort have now tested this thesis and none has produced evidence
that survives full scrutiny. This is not a marginal "almost" — the mechanical PASS here is
real but is built on roughly 20-22 real-world trade opportunities across the whole 5.5-month
OOS window (not the 458 signals or even the 5×9-13-trade cell counts suggest), concentrated
in two adjacent volatility clusters, unstable to a single reasonable methodological choice,
and one of its two real clusters shows the same IS/OOS sign-flip signature that sank the
immediately preceding seed in this same battery family.

**What this leaves, per the work order's own suggested fallback**: the `mes-linear-sim`
thesis — "the option tax is the killer, not the read" — is a genuinely different question
from the one just killed a third time. It does not ask whether MES has an independent
multi-day swing edge; it asks whether OUR EXISTING, evidenced SPY 0DTE intraday directional
read survives better on a linear instrument (MES) where the theta/spread tax (25-33% of
premium per 0DTE round trip) doesn't exist and friction is roughly 1 tick. Per
`markdown/planning/FUTURES-FIRST-PLAN-2026-08-09.md`, infrastructure for this already
exists (`Gamma_FuturesMirror`, `automation/state/futures/`, an edge3-sim fill/position
spine) — the mirror-shadow approach re-expresses signals we already have some directional
evidence for, rather than searching for a brand-new multi-day entry family from scratch.
That plan's own framing is the right one to carry forward: "the mes-linear-sim note IS the
hypothesis. It gets tested, not assumed" — same discipline this document just applied.

**Nothing here is armed.** No broker wiring exists for this seed family; paper/shadow
infrastructure was out of scope for this run regardless of verdict, per the work order.
