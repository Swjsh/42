# CONVICTION SCORE — historical verdict: **NULL. DO NOT ARM.** (2026-08-12)

Built tonight, backtested tonight, and the evidence says it does not work as designed.
Artifacts: `backtest-2026-08-12.{jsonl,md}` · `-summary.json` · `-robustness.json` ·
tools `backtest/tools/conviction_{entry_index,levels_asof,backtest,backtest_robustness}.py`.

## 1. The backtest WAS possible — my "not backtestable" verdict was wrong twice over

Levels regenerate from bars. Better still, `backtest/lib/reconstruct_levels_asof.py` **already
existed** — same rli helpers, explicit `as_of_et`, no I/O, already RED-proofed causal, and
`et_now()` never enters the path. So the clock wrinkle I flagged was avoided entirely rather
than patched. **Second instance in one night of "the producer could be re-run, and in fact
someone already wrote the tool."**

Reconstruction fidelity was MEASURED, not assumed, against 28 real point-in-time
`key-levels.json` snapshots: **recall 0.852, precision 0.806**; per-entry vs the engine's own
logged `levels_active`, **79.5% agreement with 15 misses and 0 inventions** — strictly
conservative, so it can only UNDERSTATE C1, never inflate it.

## 2. The answer to the only question that mattered: higher conviction does NOT make more money

Scored at the honest unit — the **signal**, not the mirrored per-arm fill:

| score | fills | signals | signal WR | mean return-on-premium |
|--:|--:|--:|--:|--:|
| 0 | 99 | 54 | 0.241 | +0.010 |
| 4 | 35 | 11 | 0.364 | +0.110 |
| **5** | 20 | **5** | **0.000** | **−0.163** |
| **6** | 4 | **1** | **0.000** | −0.085 |

**Spearman −0.025. Flat.** (The per-fill −0.17 is inflated 2.33x by arm fan-out — do not quote
it. Six arms mirroring one signal is one observation, not six.)

## 3. The ratchet fails the mandated control — the "savings" IS the base rate

Forward-simulated correctly (only TAKEN entries increment k): keeps 21 of 205 fills, suppresses
**−$22**. Matched 20,000-draw random suppression from the same (arm, day) cells:
**median +$159, p05 −$487, p = 0.325.**

Deleting 21 random trades would have done *better* than deleting the 21 the score chose.
Kept-cohort expectancy **−$57.62/trade vs −$6.01 baseline** — and it is worse than baseline at
**every** floor from 2 to 6. This is exactly the trap the design memo pre-registered against,
and it caught it.

**F3 passes** (88.3% block rate, inside the 20–95% band) — so the score is not strangling.
It is simply not selecting.

## 4. Why this is NOT a hard kill

The entire high-conviction evidence base is **6 signals, 0 winners** — binomial p = 0.124 at
baseline WR. **Suggestive of harm, not significant.** Survived four artifact hunts
(setup-class, day-concentration, arm, C1-undercount).

**Role-side coherence — the refinement I deferred as a prereg candidate — is ALSO not supported:**
the sign is opposite the hypothesis (4 signals). Deferring it was right; adding it would have
been fitting noise.

## 5. Coverage, stated honestly per the standing rule

205 of 314 scorable. **All 109 drops share ONE cause**: `trigger_level_exact` did not exist
before 2026-07-10 (0 rows carry it before 07-09; 794/794 on 07-10). safe-1 loses all 27. The
agent refused to re-derive those levels from a reconstructed set rather than manufacture
coverage. **Nothing scores 0 from a missing input** — every row carries an `upper_bound`, and
158 of 184 blocks are robust to every unmeasurable component.

## 6. Two bugs found in code I shipped hours earlier

1. **`conviction.py` C2 dead branch** — tested `source.startswith("shelf")` but the producer
   writes `daily_context_shelf`, so the highest-weighted level class in the compiler (SHELF,
   weight 5, multi-WEEK zones) could **never** score the memory component. C14 class, in
   same-night code. **FIXED** (substring match).
2. **`extra_exec` is the second execution path** the churn teardown listed as unresolved —
   **36 placements** whose parent row carries `triggers: []` / `trigger_level_exact: null`,
   i.e. describing a setup that did not fire. Reading those rows naively is precisely the
   fake-zero trap. **This closes churn-teardown open item #1 (the orphan safe-2 09:58 fill).**

## 7. Gate correction carried into the shadow plan

F1's *"≥25 would-blocked fills"* must read **"≥25 blocked SIGNALS."** With 6-arm fan-out, 25
fills can be as few as 3 independent observations — the same inflation that made the per-fill
Spearman look 2.33x stronger than it is.

## Decision

- **DO NOT ARM the ratchet.** It fails its own pre-registered control at p = 0.325.
- **Keep the shadow running** — it is log-only, free, and 6 signals is too thin to close the
  question. But expectations are now calibrated: the prior is null, not promising.
- **Do NOT add role-side coherence.** Measured, unsupported.
- **Before any future weight freeze**: resolve C2's `memory_score >= 40` (production uses 60)
  and the fact that the underlying level-memory wire itself graded NEGATIVE_INSUFFICIENT_N
  (n=3, −$489.50) and stayed on only because n was below the floor.

**The honest read: I built a positive-evidence axis in one evening and the data says it does
not predict returns. That is the system working — the design memo pre-registered the exact
control that killed it, before the score existed.**
