# Lesson candidate: an OP-22 "retention cap" stated only in prose silently fails

**Date:** 2026-08-19
**Filed by:** conductor (AFTERHOURS)

## What happened

`automation/overnight/queue.md` was consolidated on 2026-08-09 (archived to
`queue-archive-2026-08.md`) specifically to stay under the Read tool's
256KB single-call limit. The archive note left in the file said so
explicitly. By 2026-08-19 -- ten days later -- the file had silently
regrown to 598,612 bytes (2.3x the limit), with 119 fully-resolved
`[x] ... status:done/closed/resolved` items (each a multi-hundred-word
after-action writeup) sitting in the live backlog instead of an archive.

Nobody was warned. Every fire in between either worked around the size
limit (via `task_scorer.py` instead of raw `Read`) or never noticed the
file had ballooned, because there was no artifact whose job was "notice
this."

## Root cause

OP-22 states the principle in prose ("every append-only producer has a
retention cap; hitting it triggers CONSOLIDATION") but `queue.md` had no
CODE enforcing it -- the cap lived only in a one-time archive note's
memory, not in anything that runs again. A prose retention cap on an
append-only file is not a retention cap; it is a wish.

## Fix shipped this fire

1. Consolidated `queue.md` back down (598,612 -> 348,523 bytes),
   archiving to `queue-archive-2026-08-19.md` with a documented, verified
   selection method (checked + terminal status only; zero `depends:`
   breakage confirmed programmatically before removal).
2. **Graduated to a guard:** `backtest/tests/test_queue_md_retention_cap.py`
   RED-fails once `queue.md` crosses 450,000 bytes, and separately asserts
   the 2026-08-19 archive file exists and is non-trivial (so a future "fix"
   for a failing size test can't just delete the overflow instead of
   archiving it).

## Suggested generalization (not done this fire -- flagging for the
lesson-author to consider as an `L##`)

Any OTHER append-only-by-design markdown/JSONL file that has ONLY ever been
consolidated by a one-time manual pass (not a recurring script or a guard
test) is carrying the same latent risk. Worth an inventory sweep:
`journal/mistakes.md`, `analysis/self-audit/new-gaps-flagged.md` (already
has DONE markers inline, may be fine), `STATUS.md` itself (has an explicit
"append-only producer... retention cap" line in OP-25 already -- worth
checking it has a CODE guard, not just the same prose pattern this lesson
documents).
