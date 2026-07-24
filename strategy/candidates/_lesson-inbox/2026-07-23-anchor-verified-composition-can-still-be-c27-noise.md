# Lesson candidate: a pattern-grammar composition that fires on its own named anchor exhibits can still be C27 NOISE-KILL

> Queued by conductor (AFTERHOURS) 2026-07-23 ~23:35 ET, from the ENGULFING-AT-STRUCTURE-TRIGGER
> follow-up build (commit `8aed997a`). Inverse pairing to the swing-shelf fire's earlier finding
> ("a clean prescreen number can still fail a targeted anchor check") — this is the OTHER
> direction of the same discipline gap.

## Symptom
Built `engulfing_at_local_cluster` (backtest/lib/patterns/registry.py) specifically to fire on 2
real live-tape exhibits J called (2026-07-21 bullish, 2026-07-23 bearish). Verified via
`pattern_anchor_verify.py` — both anchors fired exactly as intended on the first working design.
Declaring victory at that point (as the prior swing-shelf fire's own falsification discipline
almost invites — "the hard part is making it fire on the real bars") would have shipped a rule
that fires on 92-99% of ALL trading days (C27 prescreen verdict: NOISE-KILL) — i.e. a rule that
technically explains the 2 named exhibits but carries essentially zero cross-day selectivity as a
trading signal.

## Root cause
Anchor verification (`pattern_anchor_verify.py`) and C27 frequency prescreen
(`pattern_prescreen.py`) test two INDEPENDENT, NON-SUBSTITUTABLE properties of a rule:
- Anchor verification: "does this rule fire on the SPECIFIC bars it claims to explain" (precision
  on a curated n=2 sample).
- C27 prescreen: "is this rule SELECTIVE across the full history" (population-level base rate).
A rule can pass one and fail the other in either direction. The base predicates this rule
composed from (`engulfing()` has no minimum body size; `local_extreme_cluster()`'s bare
n_touches=2 threshold) were each individually loose enough that their conjunction still fired on
nearly every day — clustering near a recent extreme after ANY size reversal candle is common
market noise, not a rare structural event.

## Fix
Ran the C27 prescreen IMMEDIATELY after anchor verification passed, before treating the build as
done. Grid-searched two discriminators (`local_cluster_min_touches` 2->3,
`local_cluster_min_body_dollars` 0->0.40) against BOTH constraints simultaneously (re-running
`pattern_anchor_verify.py` after every candidate tightening) until the rule cleared C27 (33.3%
days, TESTABLE) while both anchors still fired. Neither check alone would have caught this —
anchor-only would have shipped noise; prescreen-only (run before building anchors) would never
have named which 2 tightenings preserve the real exhibits.

## Encoded in
- `backtest/lib/patterns/registry.py`'s `engulfing_at_local_cluster` PatternRule docstring/
  thresholds — the min_touches/min_body floors are explicitly disclosed as "grid-searched
  discriminators, not published stats" (TA-PATTERN-REFERENCE.md citation discipline).
- This lesson (candidate) — for lesson-author to graduate to LESSONS-LEARNED.md + CLAUDE.md
  OP-25 index, ideally cross-referenced with C27 (`inside_day_nr7_break` NOISE-KILL precedent)
  and the swing-shelf fire's inverse finding.
- Suggested future guard (not built this fire, scope discipline): a `pattern_anchor_verify.py`
  convenience flag that ALSO runs a quick prescreen pass on any rule whose anchors it checks, so
  the two checks are never run in isolation by a future fire that only remembers one half.

## L## (optional)
Next available L# per lesson-author's own max-grep convention (this repo's LESSONS-LEARNED.md
was through L249 as of 2026-07-23 CLAUDE.md; several newer L#s were assigned same-day by other
inbox items still pending — lesson-author resolves the true next number at pickup time).
