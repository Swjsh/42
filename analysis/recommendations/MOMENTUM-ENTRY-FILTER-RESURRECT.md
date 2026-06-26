# momentum_morning ENTRY-FILTER RESURRECTION — VERDICT: **OVERFIT_OR_FAILS**

**Date:** 2026-06-21 (Sunday SAFE research, $0, not live path). **Family:** `momentum_morning`
(detector `detect_intraday_momentum`, byte-for-byte). **Cell:** 1DTE + dollar-anchored stop
($59.28, ITM-2). **Window:** 2025-01-02..2026-06-16 (IS = 2025, OOS = 2026).
**Harness:** `backtest/autoresearch/_momentum_entry_filter_resurrect.py` (reuses
`_dte_stop_construction.run_cell` + `_dte_expansion_sim.clears_bar` byte-for-byte).
**JSON:** `analysis/recommendations/momentum-entry-filter-resurrect.json`.

## The question
The dollar-stop fixed the RISK on momentum_morning (maxDD -$4,432 → -$2,252, Sortino
-0.905 → +6.21, worst-day capped at the $59.28 threshold) and lifted OOS exp/tr to
**+$61.31 (n=59)**, clearing 10 of 11 gates. It FAILED ONLY the L173 de-concentration gate:
`oos_drop_top5 = -$1.25` (and the sibling full-sample `drop_top5_full = -$4.21`). The test:
**can a CAUSAL, IS-frozen entry filter lift signal breadth enough to flip `oos_drop_top5`
positive on held-out OOS, without overfitting?** Strict rules: causal-only features, threshold
chosen on IS-2025 only then frozen and applied to OOS-2026, re-check all 11 gates +
no-regression (L174), small a-priori sweep (5 filters, one test each).

## Result — every filter (IS-chosen threshold, applied to OOS-2026)

| Filter (causal) | IS-frozen rule | OOS n | OOS exp | **oos_drop_top5** (gate 9, L173) | drop_top5_full (gate 5) | no-regr | clears bar |
|---|---|---:|---:|---:|---:|:---:|:---:|
| **baseline (unfiltered)** | — | 59 | +$61.31 | **−$1.25** | −$4.21 | — | ✗ |
| **F1 momentum strength** | keep \|move\|≥0.0040 | 55 | +$70.08 | **+$3.39** ✓ | −$2.62 ✗ | yes | **✗** |
| **F4 tight stop-dist** | keep stop_dist_rel≤0.0169 | 57 | +$65.54 | **+$0.98** ✓ | −$8.72 ✗ | yes | **✗** |
| **F3a low VIX** | keep VIX≤26.70 | 54 | +$55.09 | **−$11.56** ✗ | −$13.62 ✗ | no | ✗ |
| **F3b VIX not rising** | keep slope≤0.16 | 45 | +$47.96 | **−$31.14** ✗ | −$14.07 ✗ | no | ✗ |
| **F2 side select** | (infeasible on IS) | — | — | — | — | — | ✗ |

**Zero filters clear the bar.** Two (F1, F4) flip the decisive OOS-alone gate 9 positive but
NEITHER flips the full-sample gate 5 (`drop_top5_full`) positive — so neither passes
`clears_bar`. F3a/F3b make concentration WORSE and remove winners (no-regression fails). F2
is infeasible (the C/P split is ~53/47 and both sides are IS-negative on de-concentration, so
keeping either side keeps < the 55% n-floor and still doesn't de-concentrate).

## Why this is OVERFIT, not a near-miss (the decisive evidence)

An oracle sweep of the F1 threshold across BOTH halves (real numbers, `move_abs`):

| \|move\| thr | keep N | IS drop_top5_full | OOS drop_top5_full (gate 5) | **OOS-alone drop_top5 (gate 9)** |
|---:|---:|---:|---:|---:|
| 0.0035 | 183 | −23.62 | −4.21 | −1.25 |
| **0.0040** | **169** | **−25.09** | **−2.62** | **+3.39** |
| 0.0045 | 149 | −26.73 | −9.45 | −20.51 |
| 0.0050 | 136 | −30.75 | −13.93 | −25.97 |
| 0.0055 | 116 | −28.90 | −16.72 | −41.81 |
| 0.0080 | 55 | −49.39 | −17.13 | −59.28 |

1. **The OOS gate-9 flip is a single isolated point.** `oos_drop_top5` is positive at
   EXACTLY one threshold (0.0040 → +3.39) and negative on BOTH sides (0.0035 → −1.25,
   0.0045 → **−20.51**). A lone positive spike bracketed by negatives is a knife-edge, the
   textbook signature of noise — not a plateau / monotone trend you could trust out-of-sample.
2. **The IS objective never improves — it monotonically WORSENS.** IS `drop_top5_full` goes
   −23.62 → −25.09 → −26.73 → … → −49.39 as the filter tightens. The filter does NOT
   de-concentrate in-sample at any threshold. So the IS data gives **zero predictive support**
   for the OOS flip: the IS-honest selection landed on 0.0040 only because it was the
   least-bad / most-feasible IS choice, not because IS told us it de-concentrates. The OOS
   +$3.39 is held-out luck on a 4-day removal (the 4 removed OOS days were net −$237).
3. **Gate 5 (full-sample drop_top5) stays negative everywhere.** Even the lucky 0.0040 point
   is −$2.62 full-sample. The structural bar requires BOTH de-concentration gates positive;
   the filter cannot satisfy gate 5 at any threshold.

This is exactly the trap the prompt and **L178** warned about: a stop/sizing lever moves the
LOSS distribution; L173 (`oos_drop_top5 < 0`) is a property of the WIN/signal-breadth
distribution. The morning-move magnitude is a momentum **strength** knob — it shapes which
trending days you take, but it does NOT manufacture win-day breadth, and the IS data confirms
it doesn't de-concentrate in-sample. The $1.25 gap on 59 OOS trades is noise-level and a single
threshold trivially "crosses" it out-of-sample by chance, which is precisely why a held-out,
IS-supported, plateau-stable flip — not a one-point spike — was required to count.

## VERDICT
**OVERFIT_OR_FAILS.** No causal, IS-frozen filter generalizes IS→OOS: the only thresholds that
flip `oos_drop_top5` positive (F1@0.0040, F4) are unsupported by the IS de-concentration
objective (flat-negative / worsening), are knife-edge single points in the OOS sweep, and still
fail the full-sample gate 5. **momentum_morning stays DEAD.** This CONFIRMS the doctrine
(L178 / C4 concentration / C28 exit-knob limits): **signal-breadth (L173) cannot be cheaply
filtered** — an oos_drop_top5<0 edge needs a fundamentally different/broader ENTRY signal, not a
strength/regime trim of the existing one. (No independence check vs #1 is needed — nothing
resurrected.)

## What DID hold up (worth keeping, separately from the dead family)
- **The dollar-anchored stop is the right RISK construction** (re-confirmed: maxDD −$2,035,
  Sortino +7.29, worst-day −$159 even on the filtered cell) — but it is necessary-not-sufficient,
  per L178. Independently adopt-worthy wherever maxDD scales with premium; not a resurrection.
- **F1's no-regression held** (removed OOS days were net −$237): the filter doesn't throw away
  winners. It simply can't add breadth. A clean negative, cleanly disclosed.

## NEXT DIRECTION (named, either-way)
1. **Stop chasing concentration-failed dead families with trims.** Graduate L178 to a hard
   pre-screen: before any resurrection attempt on an `oos_drop_top5 < 0` family, require that a
   candidate ENTRY change move the **IS** `drop_top5_full` materially positive FIRST (an
   IS-supported mechanism) — abandon if IS de-concentration can't be achieved in-sample. This
   harness's IS-objective column is the screen; bake it into the dead-library backlog as a gate.
   (Folds into `markdown/research/STRATEGY-DIRECTION-BACKLOG.md`.)
2. **Spend the breadth budget on NEW signals, not trims of old ones.** The live edge (#1
   vwap_continuation) cleared L173 because its signal was ALREADY broad-based. The productive
   direction is *additive* breadth — independent setups that pay on different days — not
   subtractive selection on a narrow base. Continue the edge-hunt families that are L173-positive
   on raw signal (the EDGE-HUNT pipeline), not the dead-library rescue track.
3. **Retire the momentum_morning / orb_continuation / power_hour 1DTE-dollar-stop resurrection
   thread.** 0/3 + this filter attempt = the dead-library-via-risk-lever hypothesis is closed.
   The dollar-stop is the keeper; the dead families are not.
