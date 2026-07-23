# ENGULFING-AT-STRUCTURE-TRIGGER -- verdict: HONEST NULL

**Verdict:** 0/12 grid cells clear the ship bar. Do NOT wire. Full real-fills replay,
386 days, both anchors fire on 4 cells -- all 4 are net-negative. This is a genuinely new
detector (not a re-run of the failed swing-shelf attempt) that fires correctly on both
of J's live exhibits but carries no measurable edge under the standing 4-gate + BH test.

## What was built

1. **Root cause of the prior miss (already found + fixed before this fire, see
   `automation/overnight/queue.md` ENGULFING-AT-STRUCTURE-TRIGGER):**
   `backtest/lib/patterns/registry.py::engulfing_at_swing_shelf` (commit `31c5089e`)
   composed the existing `engulfing` predicate with the existing swing-pivot primitive
   (`flat_side`/`labeled_swings`). `backtest/tools/pattern_anchor_verify.py` proved it
   does NOT fire on either exhibit (both anchors declared `expected_fire=false`).
   Root cause: a 2-sided-fractal pivot needs bars on BOTH sides to confirm -- but in
   both exhibits the second touch of the shelf IS the reaction/engulfing bar itself,
   which has zero bars after it at evaluation time. Every rule built on that primitive
   inherits the same blind spot structurally.
2. **New primitive** (`backtest/tools/engulfing_at_structure_detector.py::find_shelf_touch`):
   a ONE-SIDED (backward-only) rolling local-extreme check. A shelf touch is confirmed
   using only bars `<= t`, so the reaction bar itself can be the second touch. C6-safe by
   construction (verified by 3 causality guard tests, RED-proofed by injecting a
   deliberate look-ahead bug and confirming the test caught it).
3. **Composite trigger:** engulfing (standard OHLC body-containment) AND body-%-floor
   gate AND a matching-direction shelf touch within a $ zone-band and minimum bar
   separation. Bearish engulfing only pairs with a HIGH shelf (put); bullish only with a
   LOW shelf (call).
4. **Frozen pre-reg:**
   [`analysis/recommendations/engulfing-at-structure-prereg-2026-07-23.json`](engulfing-at-structure-prereg-2026-07-23.json),
   written + a cheap non-P&L anchor falsification precheck run BEFORE the expensive
   real-fills replay (same discipline the prior fire's own writeup required). Grid: 3
   knobs x 12 cells (`zone_band_dollars` in {0.08, 0.15, 0.25}, `body_floor_pct` in
   {0.50, 0.65}, `min_bars_apart` in {1, 3}; direction is structural, not a 4th axis).
5. **Full real-fills replay:** 386-day frozen OPRA inventory
   (`analysis/edge-matrix/day-inventory-2026-07-23.json`), live RIBBON_RIDE exit shape via
   `exit_manager_walk` (the real production exit_manager core), ATM strike selection,
   entry-window/min-premium/risk-gate identical to every other edge-matrix family.

## Sanity anchors (fired from the freshest cache, includes today)

| Anchor | Bar (real OHLC) | Fires on |
|---|---|---|
| 2026-07-23 10:40 bearish | O740.38 H740.64 L738.67 C738.87 | 4/12 cells (needs `zone_band>=0.15` AND `min_bars_apart=1`; the only qualifying shelf touch is 10:35, exactly 1 bar back, spread $0.13) |
| 2026-07-21 11:05 bullish | O746.00 H747.07 L745.85 C746.98 | 10/12 cells (nearest touch is 11:00, spread $0.02, fires at every band and `nbar=1`; a second farther touch at 10:40 -- spread $0.08, 5 bars back -- also qualifies once `nbar>=2` excludes the near one) |

**Both anchors fire together on exactly 4/12 cells**: `band∈{0.15,0.25} x body∈{0.50,0.65} x nbar=1`.
Per the task's own standing rule, firing on the anchors is necessary but NOT sufficient --
it does not by itself ship anything.

## Full-history result (386 days, real OPRA fills)

**Every one of the 12 cells is net-negative on the tuning population, on held-out days,
and after dropping the single best trade.** None pass gate 1 (positive aggregate), so
gates 2-4 are moot for all 12. n is not the problem (297-731 real fills per cell, well
above the n=15 evidence floor).

| cell | n fills | expectancy | total P&L | day WR | held-out P&L | gates | both anchors |
|---|---:|---:|---:|---:|---:|---:|:---:|
| band0.15\|body0.65\|nbar1 (least-bad, anchor-passing) | 518 | -$1.85 | -$956.59 | 0.363 | -$5,666.00 | 0/4 | yes |
| band0.25\|body0.65\|nbar1 | 593 | -$4.95 | -$2,934.28 | 0.358 | -$7,044.20 | 0/4 | yes |
| band0.15\|body0.50\|nbar1 | 641 | -$8.08 | -$5,178.17 | 0.330 | -$3,858.86 | 0/4 | yes |
| band0.25\|body0.50\|nbar1 | 731 | -$8.70 | -$6,356.59 | 0.324 | -$6,938.52 | 0/4 | yes |
| (8 remaining cells, all `both_anchors_fire=false`) | 233-540 | -$9.88 to -$20.11 | -$2,301.76 to -$9,872.31 | 0.253-0.354 | -$1,650.67 to -$4,517.38 | 0/4 | no |

Full per-cell detail (regime split, skip breakdown, BH significance) in
[`engulfing-at-structure-2026-07-23.json`](engulfing-at-structure-2026-07-23.json); every
signal/fill/skip row in
[`engulfing-at-structure-episodes-2026-07-23.json`](engulfing-at-structure-episodes-2026-07-23.json).

**Pattern across the grid:** expectancy gets monotonically WORSE as `zone_band` widens
and `min_bars_apart` grows -- the loosest/widest cells (band0.25, nbar3) are the worst
performers, not the best. Wider bands and more separation admit noisier reactions, not
cleaner ones. The tightest anchor-passing cell (band0.15\|body0.65\|nbar1) is the
LEAST bad of the 12, still solidly negative.

**Regime split (least-bad cell):** 2025H1 flat-ish (+$26), 2025H2 the loss driver
(-$1,570), 2026 YTD positive (+$587) but on only 72 fills -- too thin to read as recovery,
not the kind of consistency the gates look for.

## Verdict + binding gate

**HONEST NULL.** No cell clears `gates_passed==4 AND bh_significant AND
both_anchors_fire AND n_real_fills>=15`. The binding gate for every cell is **g1
(positive aggregate)** -- the detector loses money in aggregate before day-majority,
drop-best-trade, or held-out checks are even reached. This is NOT the "anchor-trade
overfit trap" (loosening a gate to retroactively catch 2 exhibits) -- the grid was frozen
before the replay ran, and the result is reported as-is: real vocabulary, real fires on
both of J's live calls, no aggregate edge across 386 days under the live exit shape.

**Not wired. No live/paper change. No further loosening of this grid** -- if a follow-up
is warranted, the next honest lever (not attempted here, named for the record) is the
EXIT side: this study tuned entry only against the live RIBBON_RIDE shape, which was not
built for this trigger's typical hold profile. An entry that reliably marks real
reversals but loses money under a fixed exit shape is an exit-fit question, not proof the
entry itself is noise -- but that is a new pre-reg, not a re-run of this one.

## Files

- Detector (pure, causal): `backtest/tools/engulfing_at_structure_detector.py`
- Runner: `backtest/tools/edge_matrix_engulfing_at_structure.py`
- Guard tests (19, RED-proofed): `backtest/tests/test_engulfing_at_structure.py`
- Pre-reg: `analysis/recommendations/engulfing-at-structure-prereg-2026-07-23.json`
- Results: `analysis/recommendations/engulfing-at-structure-2026-07-23.json`
- Episodes: `analysis/recommendations/engulfing-at-structure-episodes-2026-07-23.json`
