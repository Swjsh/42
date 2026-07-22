# PULLBACK-HOLD-BULL-TRIGGER -- Stage Summary, ITERATION 2 (2026-07-22)

**Verdict: NO_CELL_SHIPS (honest null, this time on the DOLLAR gates, not the fidelity gate).**
0/36 pre-registered cells clear the ship bar. Unlike v1 -- where every cell was disqualified
before dollar economics were even consulted -- v2's design fix WORKED: both of J's named
anchors now fire, on real cached bars, through the real production exit-walk pipeline. The
kill this time is evidence-based: the best-looking cells are driven by extreme single-day
concentration and do not hold up on the held-out tail.

Pre-reg (frozen before any grid run): `analysis/recommendations/pullback-hold-bull-prereg-v2-2026-07-22.json`
Scorecard (full detail, all 36 cells): `analysis/recommendations/pullback-hold-bull-v2-2026-07-22.json`
Detector: `backtest/tools/pullback_hold_bull_v2.py`
Grid runner: `backtest/tools/pullback_hold_bull_v2_replay.py` (reuses v1's data-loading/
real-fills/stats/ship-gate helpers via import -- only the grid + detector-frequency pass are new)
Guard tests: `backtest/tests/test_pullback_hold_bull_v2.py` -- **18/18 PASS** (34/34 with v1's
untouched 16)

v1 (superseded, kept as committed evidence, NOT edited): `pullback-hold-bull-prereg-2026-07-22.json`,
`pullback-hold-bull-2026-07-22.json`, `pullback-hold-bull-stage-summary-2026-07-22.md`,
`backtest/tools/pullback_hold_bull_detector.py`, `backtest/tools/pullback_hold_bull_replay.py`.

## What changed vs v1, and whether the fix worked

| v1 diagnosed failure | v2 fix | Result on real data |
|---|---|---|
| Up-structure qualifiers (MARKET_STRUCTURE, PRICE_VWAP) both read FALSE at the 07-22 10:40 pullback-low bar, recovering True 15-45 min late | IMPULSE-LEG qualifier: within K EXTENDED (premarket-inclusive) bars, an upswing leg >= M dollars whose retracement to the candidate bar's own low is <= R, with the low still above the leg's origin -- evaluated causally AT the candidate bar | **FIXED.** Both anchors now fire on the shipping-candidate `K24_M1.00_R0.786` mode: anchor_1 pullback-bar 10:40 (retrace 0.7466, matches the pre-registered hand-verification almost exactly), entry 10:45 (inside [10:44,10:53]); anchor_2 pullback-bar 11:00, entry 11:05 (inside [11:03,11:17]) |
| "Low within band of ANY LevelMemory level" fired 9-13x/day, diluting to noise | SELECTIVITY axis: PRIOR_INTERACTION (>=1 same-day touch before the pullback) or LEG_ORIGIN (level coincides with the leg's own origin) | **PARTIALLY WORKED, asymmetrically.** LEG_ORIGIN cuts frequency hard (0.0-1.3 entries/day) exactly as hoped -- but at the cost of missing anchor_1 entirely (the leg's own origin, 746.01, sits ~0.53 away from the LevelMemory-matched level, ~746.54 -- wider than any tested band, exactly the near-miss disclosed in the pre-reg before the grid ran). PRIOR_INTERACTION only cuts frequency MODESTLY (7.7-9.8/day vs v1's 9-13/day) -- most LevelMemory levels touched by mid-morning already have an earlier same-day touch, so the filter bites less than intended. |

## Impulse-leg hand-verification held up on the real grid

The pre-reg's design-time hand-verification (against real cached bars, before freezing the
grid) predicted retrace=0.7466 at the 07-22 10:40 bar under K24_M1.00_R0.786 -- the actual
grid run reproduces that number EXACTLY (`retrace_pct: 0.7466216...`) and confirms the R-grid
asymmetry: `K24_M1.00_R0.618` at the same band/N misses anchor_1 (0.7466 > 0.618), while
`K24_M1.00_R0.786` hits it. `K12_*` never hits anchor_1 at any band/selectivity combination --
a 1-hour lookback is structurally too short to reach behind 2026-07-22's true pre-market
launch point (verified: the K=12 window's own origin ends up ABOVE the pullback low, an
outright "undercut" disqualification, not a close miss).

## Sanity anchors -- both fire, on 8 of 36 cells

All 8 anchor-passing cells are `K24_M1.00_R{0.786 with any of band15/25/40 x N1/N2, or 0.618
with band15 x N1/N2}` under `PRIOR_INTERACTION` selectivity. Zero `LEG_ORIGIN` cells and zero
`K12_*` cells pass both anchors -- exactly the two limitations disclosed in the pre-reg before
the grid ran (LEG_ORIGIN's origin/level gap at anchor_1; K12's undercut at anchor_1).

## Dollar economics -- the top cell looks dramatically better than v1, and that is the problem

| Cell | n | Total P&L | Expectancy/tr | WR | Day win rate | Held-out P&L | p-value |
|---|---|---|---|---|---|---|---|
| K24_R0.786_PRIOR_INTERACTION_band40c_N1 | 320 | $4,788.27 | **$14.96** | 36.9% | 15/36 (41.7%) | **-$817.90** | 0.247 |
| K24_R0.786_PRIOR_INTERACTION_band40c_N2 | 325 | $4,187.38 | $12.88 | -- | 15/36 (41.7%) | -$459.64 | -- |
| K24_R0.786_PRIOR_INTERACTION_band25c_N1 | 377 | $1,840.94 | $4.88 | -- | 16/34 (47.1%) | **+$203.16** (only anchor-passing cell to clear condition_4) | 0.651 |

$14.96/trade is ~9x v1's best cell ($1.60/trade) -- exactly the kind of "extraordinary result"
that demands the artifact hunt before celebrating (per the fable-too-good protocol), and the
hunt finds one immediately:

**Single-day concentration disqualifies both top cells on inspection, independent of the
formal gates.** `band40c_N1`'s single best day (2026-06-11, +$5,490.75 on the raw by-day
figures used for condition_3, or the OPRA/held-out-scoped +$4,478.56 seen at `band25c_N1`)
exceeds the ENTIRE 36-day total by itself. Removing just the best day from `band25c_N1`
flips the whole cell from +$1,840.94 to **-$2,637.62**. The day immediately after
(2026-06-12) is a matching-magnitude crash (-$3,334.95 raw / -$3,533.01 at band25c_N1) --
a spike-then-reversal pair consistent with 2026-06-11 being an unusually large single-day
trend that this detector happened to ride well, not a repeatable edge (C24: anchor-style
one-off setups are not representative of the general population of the same pattern class).

## Why every cell is correctly disqualified

- **Condition 1 (positive aggregate):** PASSES for the best cells -- not the binding constraint.
- **Condition 2 (day majority):** FAILS for every anchor-passing cell. Best case 47.1% of days
  win (band25c_N1); most sit at 41-44%. The aggregate P&L is a few very good days carrying many
  losing days, not a majority-of-days edge.
- **Condition 3 (survives dropping best TRADE):** PASSES for the top cells (the concentration
  is at the DAY level, spread across several trades on 2026-06-11, not one single trade) --
  this is exactly why day-level concentration had to be checked by hand; the formal per-trade
  condition_3 gate does not catch it.
- **Condition 4 (held-out, last 10 OPRA days 2026-07-01..07-17, never touched during tuning):**
  FAILS for every cell except `band25c_N1` (+$203.16, barely positive on n it doesn't disclose
  here as large). The highest-expectancy cell (`band40c_N1`, $14.96/tr) is NET NEGATIVE on the
  held-out tail (-$817.90) -- the edge that shows up in the bulk of the sample does not
  generalize forward into the most recent, unseen data.
- **Condition 5 (BH-FDR q=0.10):** FAILS for all 36 cells (best p=0.247, nowhere near
  significant even before the multiplicity correction).

`cell_disqualified_if` (both anchors) is satisfied by 8 cells, but the mandatory dollar gates
are AND'ed with the anchor gate -- a cell must clear all 5. None does.

## Verdict for the queue item

**PULLBACK-HOLD-BULL-TRIGGER: KILL, on real evidence this time.** v2 proves the mechanism J
asked for is buildable -- the impulse-leg qualifier IS computable causally at the exact bar J
named, on real data, through the real production exit-walk, and both named exhibits fire
inside their pre-registered windows. That rules out "the detector can't see the pattern" as
the explanation. What v2 also proves is that the pattern, once correctly and causally
detected, is not a repeatable dollar edge over 44 real trading days: the best-looking result
is carried by one exceptional day and reverses on the next one, and does not hold on the
untouched held-out tail. Per the mission's own framing ("this is the ONE permitted redesign;
if v2 fails, the idea gets killed"), this closes PULLBACK-HOLD-BULL-TRIGGER.

## Test evidence

```
backtest/tests/test_pullback_hold_bull_v2.py -- 18 passed
backtest/tests/test_pullback_hold_bull.py    -- 16 passed (v1, untouched, still green)
```

v2 coverage: impulse-leg math (M/R/undercut gates each isolated), no-look-ahead (truncation
tests at both the impulse-leg-feature level and the full-detector level), selectivity
qualifiers unit-tested in isolation, full-walk mechanics (no duplicate/overlapping signals,
consumption-after-reclaim), and -- the RED-proof the mission specifically asked for -- both
of J's named exhibits reproduced against the REAL cached `spy_5m_2026-05-19_2026-07-22.csv`
bars (not synthetic), confirming `K24_M1.00_R0.786` fires inside anchor_1's window while
`K24_M1.00_R0.618` does not, on the actual data.
