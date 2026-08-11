# Lesson candidate: an outer subprocess timeout smaller than the callee's own worst-case budget silently swallows real work as "success"

**Date:** 2026-08-11 (conductor AFTERHOURS, priority-3 self-audit-gap pass)
**Class:** C7 (silent success is failure) + C34 (tracked-but-rarely-committed state reverts)

## Symptom

`analysis/self-audit/new-gaps-flagged.md` (the self-audit gap-finder's human-readable
output) kept accumulating entries normally through 2026-08-07/08-08 triage, giving the
appearance of a healthy organ. But `analysis/self-audit/gap-log.jsonl` -- the SAME
script's dedup ledger, its ONLY source of "already seen" gap keys -- had not gained a
single new timestamp since 2026-07-13, a full month.

## Root cause #1 (the immediate silent failure): timeout budget mismatch across a subprocess boundary

`self_audit.py` called `swarm_consult.py audit` via `subprocess.run(..., timeout=300)`.
`swarm_consult.py`'s OWN internal budget for that command is
`PERSPECTIVE_TIMEOUT_S(240, parallel) + SYNTHESIS_TIMEOUT_S(300, sequential-after) = 540s`
worst case. The caller's timeout (300s) was smaller than the callee's own worst-case
single-phase budget (300s for synthesis alone) -- structurally near-guaranteed to fire
whenever synthesis took anywhere close to its own allotted time. When it did,
`subprocess.run` raised `TimeoutExpired`, caught by a bare
`except Exception as e: print(...); return 0` -- printed to a log nobody read routinely,
and returned exit 0 ("success") to Task Scheduler. Measured: 2 consecutive full-audit
failures, 2026-08-09 and 2026-08-10, invisible to every existing monitor.

**General pattern:** whenever code A subprocess-calls code B with its own timeout, A's
timeout MUST exceed B's own worst-case internal budget (sum of B's sequential phases),
not just "feel generous." A caller and callee timeout living in two different files with
no cross-reference is a silent drift hazard -- worth a cross-file guard test that reads
both real constants (regex/import) and asserts the inequality, not a comment promising it.

## Root cause #2 (the compounding, longer-running failure): dedup ledger was tracked-but-rarely-committed

`gap-log.jsonl` is the SAME "tracked-but-rarely-committed live-append file" hazard class
already fixed 4 times in this repo (`test_ledger_gitignore_guard.py`'s LEDGERS /
STATE_SNAPSHOTS / DECISION_GATING_SNAPSHOTS / STATE_FRESHNESS_REVERSION_FOLLOWUP_2, spanning
2026-07-14/07-20/07-21/08-10) -- just a 5th file family outside `automation/state/`
entirely, so the existing state-freshness-manifest-driven guard never saw it. Every append
since the 2026-07-14 stash-drop-recovery commit was silently reverted by SOME tree-wide git
op in the shared checkout, freezing the dedup key set. Effect: even on the days the swarm
consult DID succeed, already-triaged gaps were re-flagged as "new" and re-triaged from
scratch by whatever conductor fire read them next -- real, measurable wasted triage cycles
across roughly a month of `new-gaps-flagged.md` entries (visible in hindsight: many DONE
markers in that file explicitly note "same gap as N days ago", which should never have
recurred if dedup were working).

**Why it went undetected so long:** the CONSUMED, human-facing artifact
(`new-gaps-flagged.md`) is a SEPARATE file that WAS being committed correctly (it's written
by conductor fires closing the loop, which do pathspec-commit it) -- so the organ looked
alive from the outside while its internal dedup mechanism had been silently broken the
entire time. A producer's visible OUTPUT looking healthy is not evidence its INTERNAL STATE
is healthy when the two are decoupled.

## Fix

1. `self_audit.py`: `SWARM_SUBPROCESS_TIMEOUT_S = 600` (was 300 hardcoded), named constant
   with a comment deriving the 540s floor, cross-file guard
   `test_self_audit_swarm_timeout.py` asserting the inequality against both files' real
   source.
2. `gap-log.jsonl`: gitignored + `git rm --cached` (established remedy), new
   `SELF_AUDIT_GAP_LOG` category in `test_ledger_gitignore_guard.py`.
3. `self_check.check_self_audit_organ_alive()`: DEGRADED-only daily check reading the
   ledger's own newest timestamp (mirrors `check_regime_stamp_daily`/
   `check_scout_premarket_fresh`'s "verify the CONSUMED artifact, not the exit code"
   pattern) -- closes the loop so a future recurrence surfaces within a day, not a month.

Full detail: commit `44061a57`, STATUS.md 2026-08-11 entry, queue.md.

## Suggested L## graduation

Fold into C7 (silent success is failure) index AND C34 (tracked-but-rarely-committed
reversion) -- this incident is genuinely both classes at once, compounding each other.
