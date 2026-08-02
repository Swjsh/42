# Level-target-exit study — EXECUTED, verdict KILL

**Prereg:** `analysis/recommendations/level-target-exit-prereg-2026-07-31.json` (frozen 2026-07-31, git sha `a965c8499efacf38fed741c9d7c96abce24eb721`)
**Full results:** `analysis/recommendations/level-target-exit-2026-08-02.json` (all 144 cells, per-position rows)
**Run:** overnight 2026-08-02, runner-leg investigation sub-problem B

## Path A admissibility: ADMISSIBLE (the prereg's own blocker is lifted)

The prereg was recorded BLOCKED because `key-levels-history` holds only 6 dates. Proven this session that historical levels are deterministically reconstructable from cached SPY bars using the SAME producer code the live path uses (`daily_context.py` + `refresh_levels_intraday.py`), not a re-implementation:

- `backtest/lib/reconstruct_levels_asof.py` + `backtest/tests/test_reconstruct_levels_asof.py` — 6/6 green.
- Causality proven via vary-and-assert (RED-proofed against a deliberately-unsliced control).
- Real-data ground truth: reconstructing as of the 2026-07-31 12:16:02 ET anchor-trade entry tick reproduces `INTRADAY_RTH_HIGH=746.30` exactly, and the shelf candidate pool contains the exact live-verified 742.45-744.05 band (9 touches, matching the documented "8 touches/28 sessions").
- Scope disclosed: reconstructs `daily_context_shelf` + intraday (RTH hi/lo, swing hi/lo, PMH/PML) only — NOT `level_memory` or premarket-curated levels. Conservative subset (can omit an eligible level, never fabricate one).

This unlocked the full real-fills population (129 positions, all 6 arms) instead of 6 dates — every one of the 144 cells reached `n_with_target >= 30` (0 underpowered), confirming Path A genuinely restores statistical power.

## Verdict: KILL — decisive, not a parity-noise artifact

Per the kill_criterion's `no_partial_credit` clause, ALL gates G1–G8 must pass. None of the 144 cells clear the full stack. The kill is over-determined by THREE independent mechanisms, not just one noisy gate:

| Gate | Pass rate | What it means |
|---|---|---|
| **G4 runner-cohort no-regression (zero tolerance)** | **0/144** | Every cell degrades the 6-position runner-trail cohort found in this population (best cohort delta: **-$492.30** vs incumbent). This is the doctrine's non-negotiable rail — "a cell that improves the book by degrading the runner cohort is rejected outright," no partial credit. |
| **G7 level-fired-rate (>=50% required)** | **0/144** | The level target is reached often enough to matter on **at most 27.1%** of positions in the best cell. Every cell is mostly measuring the incumbent's own fallthrough behavior, exactly the trap the prereg's own `_REPORTING_GUARD` warned about. |
| **G6 BH-FDR (q=0.10, 144 cells)** | 0/144 | No cell's advantage survives multiple-testing correction. |
| G1 aggregate beats incumbent | 28/144 | Most cells don't even clear the first bar. |
| G3 drop-best-day/trade robustness | 8/144 | Most apparent "wins" are one-day/one-trade artifacts. |
| G5 OOS + walk-forward >=0.70 | 8/144 | Most cells don't hold up out of sample. |
| G8 harness-vs-live parity | 0/144 | See below — genuinely noisy at this harness fidelity, but not load-bearing for the verdict since G4/G7/G6 already kill everything independently. |

**Bottom line: even a perfect-fidelity harness would not change this verdict.** G4 and G7 are structural — they fail because of what levels this detector spec reaches and how it treats the runner cohort, not because of measurement noise.

## Harness-vs-live parity — a real, disclosed, non-fatal limitation

First run (5-minute cached option bars, population-wide): harness +$2,377.86 vs actual real fills -$1,259.99, a sign-flipped $3,637.85 gap. Root-caused (not a bug guess): a 5-minute bar's point-sampled `open` missed an intra-bar stop a real engine tick caught — verified exactly on `SPY260709C00750000`/risky-3, where the real position stopped out on a dip to $0.40 inside a 5-min bar whose own open was $0.52, producing a $475 phantom gain in the harness alone.

**Fixed**: refetched the full population at true 1-minute option-bar resolution (the same real-OPRA REST path `exit_shape_parity_study.fetch_option_bars` already uses elsewhere). Gap shrank to $1,920.40 (harness +$660.41 vs actual -$1,259.99) — better, still large. Diagnosed as the SAME two mechanisms `exit_grid_n1`'s single-trade study already disclosed (fill-price model: limit-exact vs real market-into-the-bid; tick-cadence mismatch: fleet historically ticked every 3 min, core every 1 min, the harness ticks every available 1-min bar) — just amplified at population scale where cadence effects don't cancel out the way they happened to on one anchor trade. **Recommended follow-up** (not attempted tonight, real scope): a tick-cadence-matched replay that walks each position on its OWN arm's actual historical tick timestamps rather than a fixed 1-minute grid. Given G4/G7 already kill every cell independently of G8, this would not be expected to change the verdict, only tighten the parity number.

## Graveyard entry

Per the prereg's `kill_criterion.on_kill`: **"level-referenced take-profit (frozen 2026-07-31)" is recorded DEAD.** No band value may be moved and re-run; the swept values are frozen in the prereg file. A later attempt must be a new pre-registration citing this one and stating what changed and why (candidate axis: the detector's own construction — RULE_A/B/C over shelf+intraday levels at 1.5-5.0 reach rarely gets touched; a materially different level family or a much wider default reach might change G7, but that is a new hypothesis, not a re-run of this one).

## One disclosed interpretive judgment call

`step_4_levels_are_ZONES_not_prices.band_source`'s prose ("BAND = zone_width/2 where present") would, read literally, make the explicit 4-value `band` sweep inoperative for every level in this population (all carry their own `zone_width`). Resolved by following the structurally-binding `cells.axes.band` sweep directly (BAND = the swept value) rather than the prose note, since collapsing all 4 band cells to an identical threshold would contradict `total_cells=144` and the BH-FDR correction it's keyed to. Flagged for adjudication, not silently picked — see `BAND_INTERPRETATION_NOTE` in the results JSON.

## Code

- `backtest/lib/reconstruct_levels_asof.py` + `backtest/tests/test_reconstruct_levels_asof.py` (Path A proof)
- `backtest/tools/level_target_exit_study.py` (library: population builder, eligibility/target selection, the walk)
- `backtest/tools/run_level_target_study.py` (driver: gates G1-G8, BH-FDR, deliverable JSON)
- `backtest/tests/test_level_target_exit_study.py` (guards)
