## Lesson candidate: a long multi-pass queue item's "still blocked on X" claim can go stale for many fires if nobody re-checks whether X already happened

**Filed:** 2026-08-28, conductor AFTERHOURS (SEVENTH PASS of `VBS-WRAPPER-EXIT-CODE-BLIND-SPOT`).

**What happened:** `VBS-WRAPPER-EXIT-CODE-BLIND-SPOT` accumulated 6 dated PASS writeups
over 2026-08-04 through 2026-08-21. The THIRD PASS (08-07) ran the `/fable-blast-radius`
audit its own opening paragraph said was the remaining blocker, and reached a real
verdict (blanket vbs flip NOT RECOMMENDED; per-task relay migration is the safer
standing path -- a decision, not a deferral). But `task_scorer.py`'s advisory text
("trace it against CURRENT reality before executing") kept getting satisfied by fires
re-reading the ITEM'S OWN TOP-LINE description (which still says "Fix STILL OPEN...
stage it behind a `/fable-blast-radius` pass first") rather than reading all the way
through the dated PASS history to see that pass already happened. Per STATUS.md, this
item was re-punted as "still gated behind its own blast-radius pass" on at least 3
consecutive fires (2026-08-25/26/27) before this one actually read the full history and
found the real remaining scope was a single 1-file documentation gap.

**Root cause:** a queue item's top-line/opening-paragraph description is the part every
fire reads first and fastest, but it is written ONCE at filing time and never updated as
later PASSes resolve sub-claims within it. A long append-only item (this one runs ~9,000
words across 6 dated passes) makes "read the whole thing" expensive enough that a
sonnet-tier fire under time/cost pressure reasonably stops after the top-line advisory
looks unambiguous, and re-derives the SAME stale conclusion the last 3 fires reached.

**Generalizable fix (not applied to `task_scorer.py` this fire -- flagging for a future
fire, in scope per this item's own text):** when a queue item accrues >= 3 dated PASS
blocks, the AUTHOR of the next pass should update the item's own opening
`Fix STILL OPEN...` sentence (or add a one-line `CURRENT STATUS:` header right after the
`::` marker) rather than relying on the reader to walk the full history. `task_scorer.py`
could also cheaply flag "long item, N dated PASS blocks, last-pass verdict may supersede
the opening description" as part of its own advisory text, nudging the next fire to grep
for the LAST dated pass rather than trust the first paragraph.

**This is a sibling of, not a duplicate of,** `2026-07-18-stale-queue-item-outranked-real-
work.md` (which covers a DIFFERENT failure mode: closing an item because superseding work
already answered its question elsewhere in the repo). This lesson is about a queue item's
OWN internal history going stale to itself -- the same file re-punting on outdated
information about its own prior progress.

**Suggested class:** could fold into C7 (silent success is failure -- audit outputs, not
exit codes) or stand as its own lesson; leaving the exact L## assignment to lesson-author.
