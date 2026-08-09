## Lesson candidate: `-MaxBudgetUsd` mis-sized-at-birth is now a NAMED, RECURRING class -- the roster sweep itself is the graduation

**Date:** 2026-08-08 (conductor-weekend fire)
**Class:** C14 (dead/translated-but-unapplied knobs: vary-and-assert) / C7 (silent success is failure)

**Recurrence count for this exact shape** ("a `-MaxBudgetUsd` cap set once at script birth,
never revisited, quietly fails a real fraction of runs, invisible to `LastTaskResult` because
the vbs/ps1 launcher hop swallows the real exit code"):

1. 2026-08-06: `run-scout-premarket.ps1` (0.50, ~7-8 weeks, EVERY day failing)
2. 2026-08-08 (earlier fire same day): `run-eod-flatten*.ps1` (1, 8/10 recent dates failing)
3. 2026-08-08 (this fire): `run-mcp-daily-audit.ps1` (0.30, 45% of 42 dated fires failing --
   the highest failure rate found yet, and STILL ACTIVE as of the two most recent failures
   checked, 08-05/08-06)

**This fire ran the roster-wide audit queue item (`BUDGET-ROSTER-AUDIT-MAXBUDGETUSD`) that
the 2026-08-08T00:00 fire pre-filed exactly for this reason.** It found one more live
instance (mcp-daily-audit) and correctly ruled out two false leads by checking real logs
first (futures-heartbeat is a deliberately disabled task, not a bug; analyst-eod is genuinely
not failing despite a low-looking cap) -- proving the "cross-check real logs before touching
anything" discipline in the queue item's own Action line is load-bearing, not boilerplate.

**Recommendation:** this is now 3 independent instances of the identical mechanism across ~2
days of fires. Per OP-25 ("a re-violated lesson MUST become a test"), the NEXT recurrence
(if any) should not be a 4th manual grep-and-fix -- it should trip a STANDING guard. Concrete
shape for `lesson-author` / a future fire to build: a single parametrized pytest
(`test_budget_roster_no_silent_failures.py`) that walks every `run-*.ps1` with a
`-MaxBudgetUsd` flag, reads its matching `automation/state/logs/{task}-*.log` files, and RED's
if any task's `Exceeded USD budget` + timeout(124) rate over its last N dated logs exceeds a
threshold (e.g. 15%) -- turning "audit the roster" from a periodic manual sweep into a
standing regression guard, closing the loop this lesson names.

No code changed by this note -- it is the graduation trigger for `lesson-author` to fold an
`L##` into `LESSONS-LEARNED.md` + the CLAUDE.md OP-25 C14 index row, and for a future
conductor fire to build the standing guard described above.
