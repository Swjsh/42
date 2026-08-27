# Sample-floor gates must scope to the mechanism-relevant sub-population, not total fills

**Date:** 2026-08-27 (conductor AFTERHOURS)
**Class:** C14 (dead/translated-but-unapplied knobs) -- new concrete instance

## What happened

`FLEET-STRIKE-TIER-ATM-EXTENSION-EVAL-2026-08-01` (queue.md) repoints risky-1/risky-3's
**$0-2K equity** strike-tier row from OTM-3 to ATM. Its own frozen prereg's sample-floor gate
reads `"n>=20 live fleet fills... combined"`. By 2026-08-27, 139 real fills existed
(73 risky-1 + 66 risky-3) -- `task_scorer.py` correctly read the dependency as satisfied and
surfaced the item as `ready: true`.

Scoring it against those 139 fills would have been wrong. Every one of them was priced in the
**$2K-10K** bracket (both arms started at $5,000 and have never dropped below $2,000) --
a *different* row of the same tier table, governed by a *separate, already-adjudicated*
prereg (`atm-tier-extension-2k10k-prereg-2026-08-03.json`, executed/killed for risky-3 on
2026-08-06). The $0-2K row this specific prereg touched has fired **zero** times. n=0, not
n=66/139.

## Root cause

The gate's sample-floor text counted the ARM's total fill volume, not fills attributable to
the specific code path/row/condition the change actually modifies. When a change only
activates under a condition (an equity bracket, a VIX regime, a time-of-day window, a
setup-quality tier...), "N fills happened on this arm since arming" is not evidence the
change ever fired -- it can be 100% attributable to unrelated code paths on the same arm.

## Generalizable fix

Any prereg/gate written as "n>=N fills since arming" should also name the **condition
predicate** the fills must satisfy to count (e.g. "fills where `equity` < $2,000 at decision
time", "fills where `setup_quality == 'ELITE'`"), and the evaluator must group by that
predicate BEFORE counting -- not assume total-population count implies mechanism engagement.
`task_scorer.py`'s dependency-readiness check is similarly naive (counts raw fills) and will
flag more of these as falsely "ready" until this becomes a checked pattern.

## Where else to look

Any other `analysis/recommendations/*prereg*.json` whose `gates_frozen_before_arming.sample_floor`
or equivalent says "n>=N fills" without naming a condition predicate should get the same
equity/regime/quality-bucket cross-check before being scored. Not audited exhaustively this
fire (bounded scope) -- flag for a future fire's sweep.

## Evidence

`analysis/recommendations/fleet-strike-tier-atm-extension-2026-08-27.json` -- full derivation,
including the equity-bucket breakdown (all 504 risky-3 + 607 risky-1 named ticks since
2026-08-01 sit in the 2K-10K bucket, zero in 0-2K).
