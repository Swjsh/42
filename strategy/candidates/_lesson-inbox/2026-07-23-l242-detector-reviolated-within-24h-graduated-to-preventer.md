## Symptom
L242 (2026-07-22) documented `self_check.py`'s CANDIDATES-UNTRACKED check
(threshold 20) as the fix for 1,176 untracked `strategy/candidates/` files.
Within 24h, a 2026-07-23 08:00 ET conductor fire found `self_check.py`
reporting DEGRADED again — 39/41 more untracked files (chef-nemo strategy
proposals + grinder-stage keeper analyses) had piled up overnight from the
continuously-running chef/kitchen/prospector daemons.

## Root cause
The 2026-07-22 fix was a DETECTOR, not a preventer. It correctly *reports*
when the untracked count crosses 20, but nothing *acts* on that report
except a human/conductor fire noticing it and manually running the backfill
pattern. Since the daemons write into `strategy/candidates/` continuously
(24/7, not just during a conductor's after-hours window), the count
re-accrues every day between conductor fires — detection without automatic
remediation just delays the same manual-cleanup toil by one day.

## Fix (graduated to code, OP-25)
Built `setup/scripts/auto_commit_candidates.py` + `Gamma_AutoCommitCandidates`
scheduled task (every 2h, every day): stages + commits `strategy/candidates/`
changes ONCE they reach ≥10 untracked/modified entries — a threshold
deliberately set BELOW `self_check.py`'s 20-threshold DEGRADED bar, so the
preventer acts before the detector would ever need to complain again.
Scoped to `strategy/candidates/` only (pathspec, never `-A`), local commit
only (no push), fail-open on any git error (git status/add/commit failure,
including the repo's own pre-commit safety-gate hook rejecting the commit)
— logs and returns 0, never raises, never retry-loops.

Guard: `backtest/tests/test_auto_commit_candidates.py` (9/9) — pins the
core invariant (`COMMIT_THRESHOLD < self_check.CANDIDATES_UNTRACKED_THRESHOLD`)
so a future edit can't silently widen the preventer's threshold above the
detector's and reintroduce this exact class of bug.

## Generalizable lesson
A DETECTOR for a re-violated lesson is necessary but not sufficient —
C7/C14's existing anti-patterns are about visibility (silent success is
failure, dead knobs). This is the sibling case: a detector that is
genuinely visible and genuinely firing can STILL re-violate the underlying
lesson if nothing automatically remediates between the moments a human/
conductor happens to look. Whenever a lesson graduates to a "check that
flags it," ask a second question: does anything *act* on the flag without
a human in the loop? If not, and the underlying condition re-accrues on its
own (a continuously-running producer, not a one-time event), the detector
alone will re-violate on its own schedule.

## Status: DONE (this fire) — encoded as `auto_commit_candidates.py` +
`Gamma_AutoCommitCandidates` scheduled task + `test_auto_commit_candidates.py` guard.
lesson-author: fold into `markdown/doctrine/LESSONS-LEARNED.md` as the next
sequential L# (after L249), cross-ref C7 (silent success) and C14 (dead
knobs) — this is neither, it's "detector without a remediator."
