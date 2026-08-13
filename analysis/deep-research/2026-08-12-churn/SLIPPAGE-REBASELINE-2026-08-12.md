# Slippage re-baseline — 0.02 vs 0.01 across the verdict-bearing study set (2026-08-12)

> **Prereg frozen BEFORE any run:** `analysis/recommendations/prereg-slippage-rebaseline-2026-08-12.json`
> (commit `b2ab6943`), amended before any treatment result (`97d46490`).
> **Machine scorecard:** `analysis/recommendations/slippage-rebaseline-2026-08-12.json`.
> **Nothing was armed, un-killed, or re-config'd. Module defaults NOT changed.**

## Verdict

**No published KILL is overturned.** The three killed cells whose control run reproduces their
published numbers *exactly* all hold at `slippage=0.01`.

But the re-baseline is **not the important finding**. Two things came out of it that matter more:

1. **The harness is non-monotonic in slippage.** Lowering friction makes some cells *worse* —
   impossible for a well-formed fill model. Root-caused to stop fills bypassing `exit_slippage`.
2. **Most measured deltas are exit-path reclassification, not friction.** A 1¢ entry change flips
   which exit fires on a 5-minute bar, swamping the friction effect by 1–2 orders of magnitude.

Together these mean **"241 studies ran twice as pessimistic" is not true as stated**, and a clean
re-baseline is blocked until the bug is fixed.

## The premise needed correcting first

| | claim | measured |
|---|---|--:|
| call sites | 255 | **195** (AST over the live tree) |
| on the default | ~241 | **166** |
| explicit slippage kwarg | 14 | **7** (2 pass the DEFAULT constants, 5 are unit tests passing 0.0) |
| **studies with a published verdict** | ~241 | **78** |

The 255/241 figures come from a raw grep that counted `.claude/worktrees` copies, imports,
docstrings and comments — and, decisively, **equated call sites with studies**. The verdict-bearing
population is **78 scripts**.

## Method

Both arms run the same script, same population, same code path; only the injected slippage differs.
The module constants are bound into each function's `__defaults__` at def time, so patching the
constant post-import is a no-op — the runner wraps the function object and injects the kwarg before
the target imports it. For the 2 scripts that import and pass the constants *explicitly*, the
constants themselves are rebound pre-import. **No repo file was edited.** All writes under
`analysis/`, `automation/`, `strategy/`, `journal/` were redirected to a scratch mirror; afterwards
all 47 target artifacts were verified to retain their pre-run mtimes.

## Coverage — honestly reported

| class | n | meaning |
|---|--:|---|
| MEASURED | 49 | non-empty population, patch bound, delta measured |
| VACUOUS — empty population | 17 | ran clean, but n=0 (input rot) |
| NO_PNL_EFFECT | 5 | ran, but emits no P&L key to compare |
| NOT_RUNNABLE | 4 | errored — reasons below |
| PATCH_DID_NOT_BIND | 3 | diagnosed, not reported as "no effect" (2 since fixed) |

Reproduction against the *published* artifact: **REPRODUCES 10 · DIFFERS 47 · VACUOUS 5 · ERROR 4 ·
NO_ARTIFACT 12**. Most `DIFFERS` are benign drift — the data caches grew a day or two
(n=100→101, 641→642 days), not rot.

### Why things could not be run

* **Input rot (dominant).** `automation/state/watcher-observations.jsonl` is a **rolling file** —
  `heal-engine.ps1` rotates it into `archive/` past 1MB, so it now holds **one day**. Studies keyed
  on it match zero rows, exit 0, and write a real-looking verdict at n=0. ORB published n=10 and
  re-runs n=0, *still* `verdict: FAIL`. 7,681 rows over 376 dates were recovered from the archives;
  that reconstruction reproduced `orb_real_fills` **exactly**, validating the method — but it is a
  *superset* (v14e re-runs n=132 vs published 100), so it cannot restore most published snapshots.
* **OPRA cache-edge guard (2).** `_web_vwap_cont_late_entry_theta_cliff`, `_wp5_strike_ab` assert
  `fill date <= cache edge 2026-05-29`; the SPY feed has extended past it. Their guard fired
  *correctly*. Not re-runnable without editing a hardcoded constant — out of scope.
* **Harness gap (1).** `lbfs_shadow_revalidation` writes via an unguarded `Path.open`. Failed
  **closed** (no repo write) and ran fine in the reconstructed-input arm.
* **Different exit engine (1).** `recency_check` replays through
  `lib/exit_manager_walk.walk_exit_manager`, not `simulate_trade_real` (imported for a legacy path
  only). That walker has its own fill model, so the patch legitimately does not reach it — not a bug.

## Before/after — the three Tier-A killed cells

These are the only cells whose control run reproduces the published numbers exactly, so they are the
only ones entitled to speak to a published verdict.

| cell | published | control @0.02 | treatment @0.01 | delta | sign flip | verdict @0.01 |
|---|--:|--:|--:|--:|:--:|---|
| `orb_real_fills` v1 | $2.70, WR 0.30 | **$2.70** ✓ | $17.30, WR **0.30** | +$14.60 | **no** | FAIL — unchanged |
| `orb_real_fills` v2 | $272.80, WR 0.90 | **$272.80** ✓ | $297.00, WR **0.90** | +$24.20 | **no** | FAIL — unchanged |
| `nlwb_tp1_sweep` best | −$1,596 | **−$1,596** ✓ | −$1,516 | +$80 | **no** | "no TP1 rescues NLWB" — unchanged |
| `nlwb_chart_stop_sweep` best | −$840 | **−$840** ✓ | −$760 | +$80 | **no** | "no chart stop rescues NLWB" — unchanged |

ORB's gate is `wr >= 0.50 in BOTH variants`. Friction moves dollars, not the *sign* of a trade, so
the win rate is untouched — it was killed on **win rate**, which this change cannot address. NLWB
gains +$80 against deficits of $1,596 and $840: **5–10% of the gap.**

## Why kills were never likely to move

Of the **20** kill-flavoured published verdicts:

| kill basis | cells | friction-sensitive? |
|---|--:|---|
| CONCENTRATION / QUARTERS | 11 | partially — ratios and marginal quarter signs can move |
| PNL / EXPECTANCY | 11 | yes, directly |
| RANDOM_NULL | 6 | **no — mathematically invariant** |
| WIN_RATE | 5 | barely — needs a trade to cross zero |
| TRUNCATION / FREQUENCY / LOOKAHEAD / EDGE_CAPTURE | 5 | no — structural |

**14 of 20 cite at least one gate friction cannot move; only 2 died on a purely friction-movable
basis** (`nlwb_full_real_fills`, `momentum-accel-highvol` — both WIN_RATE).

`RANDOM_NULL` is the decisive one: the null is simulated under the **same** slippage, so both arms
shift together and the *difference* the gate tests is unchanged. Those 6 can never be rescued by
re-baselining friction, by construction.

## FINDING 1 — the harness is non-monotonic in slippage (a real bug)

Pre-registered as "more valuable than the re-baseline itself", and it is.

Two exit paths fill at an exact price with **no `exit_slippage`**, while every market exit pays it:

* **TP1 premium fallback** — `tp1_fire_premium = entry_premium * (1 + tp1_premium_pct)`.
  Defensible: a limit order fills at its limit.
* **Runner stop, incl. the post-TP1 breakeven stop** — `runner_exit_premium = runner_stop_premium`.
  **Not** defensible: a stop executes at market and should pay the half-spread.

For a TP1-limit + BE-runner trade the whole payoff is therefore

```
P&L = tp1_premium_pct × entry_fill × tp1_qty × 100
```

— strictly proportional to an entry fill that **includes entry slippage**. More assumed pessimism
*inflates* those winners. With `TP1_PREMIUM_PCT=0.30`, `TP1_QTY_FRACTION=2/3`, `qty=3 → tp1_qty=2`,
halving slippage predicts exactly `0.30 × 0.01 × 2 × 100 = $0.60` **worse** per trade.
**Observed: −$0.60 on every `TP1_THEN_RUNNER_RIBBON` trade.** Mechanism confirmed, not inferred.

| module | slippage-free stop fill | verdict |
|---|---|---|
| `simulator_real.py` | lines ~703, ~832, ~859 + TP1 ~789 | **affected** |
| `simulator_real_trailing.py` | lines 294, 383, 408 + TP1 344 | **affected** |
| `simulator_credit.py` | every exit is `m ± exit_slippage` | clean |
| `simulator_debit.py` | every exit is `m ± exit_slippage` | clean |

**It bites exit-tuning studies hardest** — the ones whose entire purpose is choosing exit
parameters: `sweep_regime_chandelier` **24/24 cells worse**, `sweep_timecond_exit` 23/44,
`sweep_watcher_exits` 20/114, `sweep_lunch_trough_gate` 8/23.

**Consequence for the premise:** the 2¢ default was *not* uniformly pessimistic. It overstated entry
cost and market exits but **inflated %-target winners and gave every stop a free fill**. The *sign*
of the bias depends on each cell's exit mix. Same script, same trades, `v14e_chart_stop_research`:
the premium-stop arm moved **+$39.60** while the market-exit arm moved **+$548.80** — 14x, from exit
mix alone.

## FINDING 2 — the deltas are path divergence, not friction

The direct friction effect is bounded: `$0.02/share × 100 × qty` ≈ **$6/trade at qty=3**, and only on
market-priced exits. Deltas far exceeding that bound cannot be friction.

`_recency_stop_variant_ab`, ITM-2 / chart-stop-only / recent_window — **n=11 in both arms**:

| | 0.02 | 0.01 |
|---|--:|--:|
| exp_per_trade | −$39.60 | **+$41.04** |
| total | −$435.60 | **+$451.40** |
| exit mix | LEVEL_STOP **3**, RIBBON_FLIP_BACK 3, TP1_RUNNER_RIBBON **1**, TP1_RUNNER_TIME 4 | LEVEL_STOP **2**, RIBBON_FLIP_BACK 3, TP1_RUNNER_RIBBON **2**, TP1_RUNNER_TIME 4 |

A +$80.64/trade swing on an ~$6/trade bound. **One trade's exit path flipped** and carried the whole
cell. A 1¢ cheaper entry lowers the stop level, and on a **5-minute** option cache that can move the
breach across a bar boundary so a different exit fires first — a documented limitation
(`OPTION-BAR-RESOLUTION-BIAS-2026-08-02`, $1,821.75 aggregate swing).

**Prevalence: 70 of 129 exit-mix distributions (54.3%) changed between arms**, across 8 of the 9
scripts that report one.

**Therefore sign flips produced by this study are not evidence about any cell's true edge.**

## Sign flips — 339 cells, none nominated

339 P&L cells across 22 studies change sign. Almost all are **sweep-grid sub-cells and slices**
(`by_quarter`, `by_side`, `by_regime`, `exit_mini_sweeps[N]`, `all_cells[N]`) inside studies carrying
**80–1,126 P&L cells each**. With that many cells, something crossing zero under a uniform shift is
arithmetically guaranteed — it is exactly the multiple-comparisons surface these studies' own gates
exist to defend against (anti-pattern 2.10).

Headline-metric flips worth naming:

* `_b6_turn_of_month_drift` `primary_per_trade` −12.85 → **+0.88** — but the cell died on 5/8 gates
  including random-null (invariant) and concentration. Kill stands.
* `_edgehunt_momentum_accel` `baseline_prod_v15_strike-2_stop-8_per_trade` −7.2 → **+0.8**
* `gate_sweep_volume_morning` `scenarios[1].edge_capture` −263 → **+42**

**None is nominated for re-validation.** The prereg requires the control to reproduce the published
numbers (all of these are `DIFFERS` or worse), n ≥ 15, non-marginal clearance of the *original* kill
threshold, and drop-best survival. None qualifies — and FINDING 2 independently disqualifies flips
driven by path divergence.

**A sign flip is not a resurrection.**

## The aggregate is deliberately NOT quantified

A naive sum over all P&L keys gives **$1,377,291.71**. That number is meaningless — it double-counts
nested keys and sums across hundreds of mutually exclusive sweep-grid cells that were never a
portfolio. Publishing it would be a fabricated headline, so it is not published.

What can honestly be said:

* the direct effect is ~$0.02/contract/round-trip (~$6/trade at qty=3), **only on market-priced exits**;
* on proportional exits it is scaled down by the stop/target percentage, and on stop fills it is
  currently **zero** (FINDING 1);
* the three Tier-A killed cells moved **+$14.60, +$80, +$80** — 5–10% of their deficits.

## Validity controls

| control | result |
|---|---|
| Write sandbox | all 47 target artifacts retain pre-run mtimes; the 3 files that did change were concurrent scheduled tasks |
| Patch binds (C14) | confirmed; 3 initial non-binds **diagnosed**, not reported as "no effect" |
| RNG noise floor | **0** differing keys across identical-slippage replicates (339 keys on `_sel_vwap_sizing`; 0 on every gated script measured) |
| Arms symmetric | 78 scripts each, 74 OK / 4 ERROR in both |

## Recommended next (none done here)

1. **Fix the runner-stop slippage** in `simulator_real.py` + `simulator_real_trailing.py` under its
   own prereg, then add a monotonicity vary-and-assert guard to `test_graduated_guards.py`.
   **This blocks a clean re-baseline.**
2. **Re-baseline the module defaults to 0.01 only after that fix** — otherwise the re-baseline bakes
   the non-monotonicity in permanently.
3. **Make studies snapshot their input population** (or an input hash + row count) into their own
   artifact, and treat `n == 0` as `NO_RESULT`, never as a verdict.

Lessons filed: `strategy/candidates/_lesson-inbox/2026-08-12-slippage-is-not-monotonic-stop-fills-are-slippage-free.md`,
`…/2026-08-12-rolling-state-file-silently-empties-old-studies.md`.
