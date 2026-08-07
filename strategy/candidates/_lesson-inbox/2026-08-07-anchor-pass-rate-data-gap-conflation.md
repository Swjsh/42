---
filed: 2026-08-07
filed_by: conductor (AFTERHOURS fire, ~01:00-02:00 ET)
kind: lesson
status: pending
---

# A "reproduction rate" metric silently turned "no data to judge" into "judged and wrong" by sharing one denominator

## Symptom

`test_fleet_arm_replay.py::test_anchor_pass_rate_clears_threshold[safe-3|risky-1|risky-3]`
failed at 54-68% against the 70% `ANCHOR_PASS_THRESHOLD` — flagged in `queue.md`/STATUS.md
`## Known broken` as a "genuinely separate exit-walk-fidelity mechanism ... risky-3 produced
75% of Wednesday -- a replay harness that cannot verify that lane's exit fidelity is still a
C7 hazard." The scope note itself named a real candidate mechanism worth checking
(`walk_exit_manager`'s trigger_level resolution, OPRA contract-bar cache staleness) but had
not yet measured which one it actually was.

## Root cause

`fleet_arm_replay.py::run_anchor_validation` computed `pass_rate = n_pass / n_anchors`,
where `n_anchors` = ALL real fills mined from the ledger, but `n_pass` only counted rows that
(a) had an OPRA contract-bar cache available AND (b) reproduced within tolerance. A real fill
whose OPRA cache is missing (`replay_status == "NO_OPRA_CACHE_OR_NO_ENTRY_PREMIUM"` or
`"NO_SPY_DAY"`) is never even handed to `walk_exit_manager` — it carries no `anchor_pass`
verdict at all — but the shared denominator counted it as an automatic FAIL anyway.

Measured live (2026-08-07): safe-3 had 8/34 data-gap rows, risky-1 14/37, risky-3 18/54.
Among the rows that COULD actually be replayed, fidelity was 88.5% / 87.0% / 94.4% — all
comfortably above the 70% bar. **The exit-walk mechanism was never broken.** The trigger_level
hypothesis (also plausible on paper — trigger_level is non-null in <1% of decisions.jsonl
rows) was checked and directly REFUTED by splitting pass-rate by trigger_level presence: rows
*without* a matched trigger_level actually had a HIGHER individual pass rate than rows with
one. The entire 54-68% shortfall was arithmetically explained by the OPRA-coverage gap alone.

## Generalizable rule

**Any "X/Y reproduces" or "X/Y pass" metric that silently treats "could not attempt X" the
same as "attempted X and it failed" will misdiagnose a coverage gap as a mechanism bug.**
This is a sibling of C7 (silent success is failure — audit outputs) but the inverse failure
mode: here a *coverage* gap disguised itself as a *fidelity* failure and sent the prior fire's
scope note hunting for a mechanism bug that didn't exist. The fix pattern: split any such
ratio into (1) a coverage/attempt-rate denominator check and (2) a fidelity-among-attempted
rate, and keep BOTH visible as separate fields rather than blending them into one number a
threshold gate reads. `bold_fullhist_replay.py::run_anchor_validation` (the sibling function
for core Bold, NOT touched this fire — out of scope, its curated `ANCHOR_FILLS` list is small
and hand-picked so the bug is dormant there today) has the textually IDENTICAL
`n_pass / len(ANCHOR_FILLS)` pattern and should be checked before it accumulates its own
data-gap rows.

## Suggested L# slot

Fold into C7 (silent success is failure) as a named sub-case, or C4 (disclose concentration /
normalize denominators) — cross-reference the scope-narrowing note this fire's own predecessor
filed (queue.md `FLEET-ANCHOR-EXIT-WALK-FIDELITY-DRIFT`) as the worked example of "measure
before you build a mechanism theory."
