# ENGULFING-AT-STRUCTURE-TRIGGER (Lane-A: `engulfing_at_local_cluster`) -- verdict: HONEST NULL

**Verdict:** 0/16 grid cells clear the ship bar. Do NOT wire. Full real-fills replay,
386 days, both anchors fire on 6 cells including the exact shipped/anchor-verified
registry config -- all cells net-negative or too-thin, and the shipped cell itself is
solidly negative (-$20.11/tr, n=87, held-out -$2,314.82). **This closes the item's
last open thread** (Lane-A's own named next step) -- combined with Lane-B's
independent HONEST NULL two days ago (`engulfing-at-structure-2026-07-23.md`), BOTH
tracks that grew out of J's two live exhibits (2026-07-21 bullish, 2026-07-23 bearish)
now agree: an engulfing candle reacting at a fast local high/low structure fires
correctly on both of J's calls, but carries no measurable real-fills edge under the
live exit shape.

## What was run

This is the confirmatory real-fills replay `automation/overnight/queue.md`'s
ENGULFING-AT-STRUCTURE-TRIGGER item named as its own still-open next step (2026-07-23
~23:12 fire): *"a frozen pre-reg (<=16 cells) + real-fills replay through
exit_manager_walk over the 386-day history, standing gates + BH, confirming the
winning cell still fires on both anchor bars."* The "winning cell" is the ALREADY-
SHIPPED, anchor-verified, C27-prescreen-cleared registry rule
`backtest/lib/patterns/registry.py::engulfing_at_local_cluster` (commit `8aed997a`) --
this fire did not design a new detector, it ran the existing one through the standard
edge-matrix real-fills harness for the first time.

1. **Zero-fork grid adapter** (`backtest/tools/engulfing_at_local_cluster_detector.py`):
   imports the exact two generic predicate factories the registry rule composes
   (`backtest.lib.patterns.predicates.engulfing`, `...local_extreme_cluster`) and
   grid-sweeps their existing parameters. Proven byte-identical to the live registry
   predicate at the shipped cell over the FULL 30k-bar sequence (not just the 2
   anchors) by `test_engulfing_at_local_cluster.py::test_shipped_cell_matches_registry_predicate`.
2. **Frozen pre-reg** (`engulfing-at-local-cluster-prereg-2026-07-25.json`, written
   before this replay ran): 3 knobs x 16 cells (`min_touches` in {3,4},
   `min_body_dollars` in {0.0, 0.40, 0.60, 0.80}, `tolerance` in {0.15, 0.20}); the
   shipped config (touch3, body0.40, tol0.20) is cell `touch3|body0.40|tol0.20`.
3. **Full real-fills replay**: same 386-day frozen OPRA inventory
   (`analysis/edge-matrix/day-inventory-2026-07-23.json`), live RIBBON_RIDE exit shape
   via `exit_manager_walk` (the real production exit_manager core), ATM strike
   selection, entry-window/min-premium/risk-gate identical to every other edge-matrix
   family -- same harness convention as Lane-B (`edge_matrix_engulfing_at_structure.py`).

## Sanity anchors (fired from the freshest cache, includes today)

| Anchor | Fires on |
|---|---|
| 2026-07-23 10:40 bearish | 8/16 cells (needs `min_touches<=3` to admit at every body/tol combo tested, or `min_touches=4` at looser body floors) |
| 2026-07-21 11:05 bullish | 6/16 cells |

**Both anchors fire together on exactly 6/16 cells**, including the shipped
`touch3|body0.40|tol0.20`. Firing on the anchors is necessary but NOT sufficient -- it
does not by itself ship anything (same standing rule as Lane-B).

## Full-history result (386 days, real OPRA fills)

**Every one of the 16 cells fails gate 1 (positive aggregate) or is too thin to
evaluate.** The shipped/anchor-verified cell itself:

| cell | n fills | expectancy | total P&L | day WR | held-out P&L | gates | both anchors |
|---|---:|---:|---:|---:|---:|---:|:---:|
| **touch3\|body0.40\|tol0.20 (SHIPPED)** | 87 | -$20.11 | -$1,749.14 | 0.355 | -$2,314.82 | 0/4 | yes |
| touch3\|body0.00\|tol0.15 | 733 | -$15.92 | -$11,671.88 | 0.322 | -$3,213.48 | 0/4 | yes |
| touch3\|body0.00\|tol0.20 | 812 | -$12.56 | -$10,201.07 | 0.354 | -$4,939.06 | 0/4 | yes |
| touch4\|body0.00\|tol0.15 | 486 | -$20.48 | -$9,951.04 | 0.279 | -$1,381.56 | 0/4 | no |
| touch4\|body0.00\|tol0.20 | 591 | -$21.52 | -$12,717.17 | 0.289 | -$3,810.14 | 0/4 | no |
| (11 remaining cells) | 1-58 | -$113.47 to +$176.61 | -$934 to +$217 | thin/inconclusive | mixed | 0-2/4 | mixed |

No cell reaches 3+ gates; none is both statistically significant (BH q=0.10) AND both-
anchor-firing AND n>=15 AND gate-clean. Full per-cell detail (regime split, skip
breakdown, BH significance) in
[`engulfing-at-local-cluster-2026-07-25.json`](engulfing-at-local-cluster-2026-07-25.json);
every signal/fill/skip row in
[`engulfing-at-local-cluster-episodes-2026-07-25.json`](engulfing-at-local-cluster-episodes-2026-07-25.json).

**Same pattern as Lane-B:** loosening the body-dollar floor toward 0 does NOT rescue
the edge -- it makes the aggregate MUCH worse (-$1,749 at the shipped floor vs
-$10,201/-$11,672 with no floor at all), because it multiplies fill count on noisier
engulfing bars. The floor is doing real selectivity work; it just isn't enough to flip
the sign.

## Verdict + binding gate

**HONEST NULL**, matching Lane-B's independent finding on a different (but
mechanistically similar) detector two days prior. The binding gate for the shipped
cell and every cell with meaningful n is **g1 (positive aggregate)**. This is NOT the
"anchor-trade overfit trap" -- the grid was frozen before the replay ran, the shipped
cell was fixed by the PRIOR fire's own anchor-verification + C27 prescreen work (not
cherry-picked after seeing P&L), and the result is reported as-is.

**Not wired. No live/paper change.** `engulfing_at_local_cluster` remains registry.py
discovery-only, unchanged by this finding (it is a real, tested, anchor-verified
grammar addition regardless of its economics -- same standing as every other
discovery-only rule in this registry).

**ENGULFING-AT-STRUCTURE-TRIGGER is now CLOSED** (`automation/overnight/queue.md`):
both independent tracks that grew out of J's two live exhibits (swing-shelf -> dead on
anchors; one-sided-shelf Lane-B -> HONEST NULL; local-cluster Lane-A -> HONEST NULL)
have run their course. If a follow-up is warranted, the next honest lever (not
attempted in either lane) is the EXIT side -- this study, like Lane-B, tuned entry only
against the live RIBBON_RIDE shape, which was not built for this trigger's typical hold
profile. That is a new pre-reg, not a re-run of this one.

## Files

- Detector (zero-fork grid adapter): `backtest/tools/engulfing_at_local_cluster_detector.py`
- Runner: `backtest/tools/edge_matrix_engulfing_at_local_cluster.py`
- Guard tests (6, incl. byte-identical-vs-registry + C6 causality): `backtest/tests/test_engulfing_at_local_cluster.py`
- Pre-reg: `analysis/recommendations/engulfing-at-local-cluster-prereg-2026-07-25.json`
- Results: `analysis/recommendations/engulfing-at-local-cluster-2026-07-25.json`
- Episodes: `analysis/recommendations/engulfing-at-local-cluster-episodes-2026-07-25.json`
