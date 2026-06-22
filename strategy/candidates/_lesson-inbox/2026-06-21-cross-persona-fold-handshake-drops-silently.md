---
proposed_lesson: cross-persona authoring handshake silently drops a step when only one persona runs
theme: C7 (silent success is failure) + C18 (status discipline)
date: 2026-06-21
source: conductor fire (test_op25_index_reconciliation.py graduation)
---

# Lesson candidate: a split authoring handshake drops its second half silently

**Symptom.** Six `L###-CLAUDE-FOLD` follow-ups (L169/L170/L173/L174/L177/L178)
accumulated across consecutive conductor fires, each a rail-4-blocked TODO that
nothing drained. A reconciliation pass then found **12 additional older**
un-indexed lessons (L3/L13/L16/L24/L25/L29/L31/L43/L56/L126/L137/L146) -- 18 total
gaps no guard had ever flagged.

**Root cause.** Authoring a lesson is a TWO-persona handshake: the conductor (or
any fire) writes the full prose into `LESSONS-LEARNED.md`, and `lesson-author`
folds the one-line entry into the `CLAUDE.md` OP-25 index (the ONLY persona with
OP-25 write access, rail-4). When the Agent tool / `lesson-author` is unavailable
in a fire, the conductor authors the prose directly but CANNOT do the fold (rail-4
forbids the conductor editing CLAUDE.md). The fold half is silently dropped; the
only trace is a LOW queue follow-up that no consumer drains. Generalizes to ANY
multi-persona/multi-step handshake where one half is gated to a persona that may
not run.

**Fix (already graduated).** `backtest/tests/test_op25_index_reconciliation.py`
reconciles the defined-lesson set against the OP-25 index and ratchets the
unindexed set so it can only shrink -- a newly authored, unfolded lesson now fails
loud at test time instead of accumulating invisibly. Phantom index refs
(indexed-but-undefined) are guarded too.

**Generalizable principle.** When an authoring step is split across personas and
one half is access-gated, the gated half WILL be dropped on fires where that
persona is absent -- so reconcile the two artifacts with a ratcheting guard rather
than trusting the handshake. (Sibling to L170 author-inbox closing-handshake.)

**Disposition.** Fold this lesson's own new L## into the OP-25 index when encoded
-- the new ratchet will flag it if you forget (nicely self-consistent). Also:
trim `KNOWN_UNINDEXED_BASELINE` as the 18 pending folds land.
