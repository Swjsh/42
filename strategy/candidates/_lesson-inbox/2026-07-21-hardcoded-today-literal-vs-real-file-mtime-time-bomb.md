# Lesson candidate: a test that hardcodes "TODAY" as a date literal but relies on a REAL
filesystem mtime is a time bomb, not a passing test

## What happened

`backtest/tests/test_eod_full_audit.py::test_stale_source_none_when_fresh` was authored
2026-07-14 as part of the fix for the tick-audit zero-count bug (commit `cc6755b`). It set
`mod.TODAY = "2026-07-14"` (a hardcoded literal), wrote a temp file (whose mtime is the REAL
current wall-clock time, set by the OS — not mockable by assigning a module attribute), and
asserted `_stale_source_note(p, now)` returns `None` (i.e. "not stale") when `now` is also
hardcoded to `2026-07-14 14:00`.

This passed on 2026-07-14 (the day it was written, when real-mtime == "2026-07-14") and on every
day since UNTIL 2026-07-21 — the exact day it went silently RED with zero code change, caught
only because a conductor fire happened to run the full suite (`pytest backtest/tests/
test_eod_full_audit.py -q`) 7 days later. Nobody was watching this specific test file in the
interim; it would have kept failing every day forever once the real date diverged from the
hardcoded literal, with no CI signal calling it out as "this is a time-bomb, not a regression."

## Root cause

The function under test (`_stale_source_note`) compares a file's REAL `path.stat().st_mtime`
against a caller-supplied `TODAY` string — that's correct, intentional production behavior (it's
literally testing "is this source file stale relative to today"). The BUG is in the test
harness: it tried to simulate "fresh" by freezing `TODAY` to a fixed string while leaving the
actual file-write (and therefore mtime) tied to the real, unmocked system clock. The two clocks
(hardcoded literal vs. real OS mtime) only agree on the day the test was written.

## The generalizable pattern (C6-adjacent, but a distinct sub-class)

C6 ("no look-ahead: filter <= current bar, verify bar closed") is about DATA leaking future
information into a backtest. This is the same shape but for TEST FIXTURES: any test that (a)
creates a real filesystem artifact (file write, whose mtime is the real OS clock) and (b)
separately hardcodes a date literal meant to represent "today" for the code path being exercised
will silently expire on the day those two diverge — and it is NOT caught by the normal red/green
signal until someone happens to re-run that specific file after the expiry date.

**How to spot it:** grep test files for a hardcoded date-string literal (`"20XX-XX-XX"`)
assigned to a module attribute in the same test as a real `.write_text()` / file-creation call
that the test's assertion implicitly expects to be "fresh" / "today" / "current."

**How to fix it:** derive the date literal FROM the real artifact (as this fix does — read the
file's own real mtime, convert to the same timezone the production code uses, and set `TODAY`
from that), never the reverse. If the test genuinely needs a frozen historical date (as the
OTHER tests in this same file correctly do — `test_stale_source_flags_old_mtime_during_market_
hours` etc. — which assert "stale" for an intentionally-old vs-mtime mismatch), that's fine and
time-invariant BY DESIGN, because a real mtime being newer than an old-fixed-`TODAY` stays true
forever. The landmine is specifically the "assert FRESH / no-staleness" case, where the test
needs the two clocks to match.

## Recommended graduated guard

Not proposing a blanket structural guard here (a generic "no hardcoded dates in tests" linter
would false-positive heavily on the correctly-time-invariant "stale" tests in the same file) —
this is a narrow, cheap-to-recur bug class best caught by cheap review discipline: any new test
combining a real file write + a hardcoded "today" literal used for a fresh/no-staleness
assertion should derive the literal from the artifact instead. If this exact pattern recurs a
second time in a different file, THAT'S the trigger to write a repo-wide grep-based CI check
(pattern: hardcoded date literal + `write_text`/`touch()` in the same test body, assigned to a
variable also compared against `datetime.now()`/`.stat().st_mtime`).

## Evidence

- Failure signature (RED-proofed via `git stash`, reproduced live 2026-07-21):
  `AssertionError: assert 'STALE SOURCE -- core-decisions.jsonl last modified 2026-07-21, not
  2026-07-14; a 0 count here may reflect a dead/misrouted path, not a quiet engine' is None`
- Fix commit: this fire, 2026-07-21 (test-only, `backtest/tests/test_eod_full_audit.py`).
- Sibling tests in the SAME file that correctly avoided this trap (asserting "stale", not
  "fresh"): `test_stale_source_flags_old_mtime_during_market_hours`,
  `test_stale_source_silent_before_market_open`, `test_stale_source_silent_on_weekend` — all set
  an intentionally-OLD `TODAY` and stay correct forever because "real mtime is newer than an old
  frozen TODAY" never flips.
