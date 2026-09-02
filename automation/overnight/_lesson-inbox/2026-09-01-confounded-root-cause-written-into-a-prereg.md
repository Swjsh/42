# The null study's "root cause" was a confounded correlation — and it got written into a frozen prereg before anyone swapped the variable

**Date:** 2026-09-01 (Opus session, executing `markdown/planning/OPUS-WORK-ORDER-2026-09.md`)
**Theme:** C7 / root-cause discipline — a correlation strong enough to name in a prereg is still not a cause

## Symptom

The whole-engine null study (`setup/scripts/whole_engine_null.py`, built the same evening)
reported **verdict WITHHELD_HARNESS_UNRELIABLE**: its V9 validate-the-validator gate replayed
the engine's own 121 real entries through the exit walker and got **79.3% sign agreement**
against a 85% bar.

A root cause was identified the same night and written into three places — the prereg's
`addendum_2026_09_01_validator_fidelity.first_reading` ("Root cause candidate: 94/121 P1 rows
lack the real chart-level trigger_level"), `queue.md`'s WALKER-FIDELITY-TRIGGER-LEVEL item, and
the work order's B1 note ("**Top research item now: walker fidelity**"). All three said the same
thing: the enrichment never carried the chart level through, so structure stops replay on a
proxy.

The supporting evidence was genuinely strong. Cross-tabbing V9's own detail rows:

| rows | sign agreement |
|---|---|
| had a real recorded `trigger_level` | 26/27 = **96.3%** |
| fell back to the proxy | 70/94 = **74.5%** |

A 22-point gap, n=121. It looks like a cause.

## Root cause of the WRONG root cause

**Nobody swapped the variable.** The two groups differ in more than the level: every one of the
27 real-level rows was a **call**, from a **core arm** (safe-2/bold-2). The comparison was
between two populations, not between two treatments.

The differential settles it in one run — the same 25 rows, the same cached bars, the same
production `exit_manager` core, walked twice with only the level changed:

```
walked with REAL recorded level : 24/25 = 96.0%
walked with PROXY reconstruction: 24/25 = 96.0%
delta attributable to the level : +0.0%
proxy level error vs real: median $0.27, max $2.33
```

The proxy was *accurate*. It was never the cause. The 22-point gap was entirely confounding.

The real cause was a different hardcode in the very same function. `walk_one` passed
`structure_stop_enabled=True` for every row, but `exit_manager.py:268` resolves stop mode as
`(shape_mode == "structure" and structure_stop_enabled and trigger_level is not None)` — and
**26.9% of the engine's P1 population (42/156) actually resolved to `premium` mode live**. Those
rows were being replayed with the wrong stop entirely. Decomposed one variable at a time over
135 rows:

```
A base (RIBBON shape, structure_stop_enabled=True)   108/135 = 80.0%
B  A + recorded stop_mode ONLY                       117/135 = 86.7%   (+6.7pp)
C  A + recorded shape keys ONLY                      108/135 = 80.0%   (+0.0pp)
D  both                                              117/135 = 86.7%   (+6.7pp)
```

Per exit_reason the mechanism is unmistakable: the `premium_stop` bucket goes
**34/42 = 81.0% → 42/42 = 100.0%**.

Note C: the *first* fix the investigator proposed after the falsification — overlay the whole
recorded exit shape — also measured **+0.0pp**. It was proposed on a three-variable test whose
attribution had not been decomposed either. The same mistake, made a second time within the
same hour, caught only because the decomposition was run before the build shipped.

## The fix

1. Thread the row's recorded `stop_mode` into the V9 walk (V9 only — the null legs are frozen
   prereg design and were left byte-identical, with the mismatch disclosed instead).
2. The enrichment defect was real and worth fixing on its own merits — it just was not the
   cause of the V9 number. `trades_enriched.py` sourced `trigger_level` from the **signal**
   stage (`trigger_level_exact`, null for every sloped-trendline trigger) and hardcoded `None`
   for all fleet arms, when the level `exit_manager` actually armed is recorded one stage later
   as `exec.trigger_level` / `placement.trigger_level`. Fixed: structure-mode rows carrying a
   level went 27/186 → **186/186**; puts 0/72 → 51/72; safe-3 (the gate's prod-shadow arm)
   0/20 → 20/20.

## The lesson

**A correlation between a known data defect and a failure is the cheapest possible explanation,
which is exactly why it deserves the differential before it is written down.** Costs are
asymmetric: running the swap took one cached-bar script and a few minutes; the wrong cause was
already propagating into a frozen prereg, the backlog, and the standing execution order, where
the next session would have inherited it as settled fact.

Two guards worth having:

- **Before naming a root cause, name what else differs between the two groups.** Here it was one
  line — "all 27 are calls from core arms" — and it was sitting in the same cross-tab.
- **Never attribute a delta from a test that moved more than one input.** Decompose first. Both
  wrong answers in this episode came from multi-variable tests; both died to the decomposition.

Related: this is the same failure shape as `/fable-too-good` in reverse. That drill scales
suspicion with how *good* a result looks; this one scales suspicion with how *tidy* an
explanation looks. A defect that explains the failure perfectly, found in the first hour, on a
metric nobody had decomposed, is a hypothesis — not a finding.

## Guard shipped

`backtest/tests/test_trades_enriched_trigger_level_2026_09_01.py` pins the enrichment invariant
that `exit_manager.py:268` makes true: every row with `stop_mode == "structure"` carries a
non-null `trigger_level`. RED-proofed (7/8 fail on the unfixed producer with the exact
missing-level signature).
