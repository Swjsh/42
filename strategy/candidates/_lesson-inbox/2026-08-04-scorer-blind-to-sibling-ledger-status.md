# A readiness parser that reads only ITS OWN file is blind to a sibling ledger's status

**Filed:** 2026-08-04 (conductor, AFTERHOURS)
**Class:** C14 sibling (dead/translated-but-unapplied knobs: vary-and-assert) — extends the
existing task_scorer readiness-parsing lesson family (L245/L246, TASK-SCORER-MULTILINE-STATUS-READ,
TASK-SCORER-STATUS-VOCAB-GAP) to a NEW mechanism: the gap isn't a bug in reading queue.md's own
status field this time — it's that `task_scorer.py` had no notion that a queue item's true state can
be gated by a completely SEPARATE ledger (`automation/state/conductor-proposals.jsonl`, the
Discord/wrist approve-bus).

## Symptom

`task_scorer.py --top` ranked `TWIN-DOCTRINE-FIRST-DEPLOY` (score 6.5) #1 for at least 2 consecutive
after-hours fires (2026-08-03, 2026-08-04) even though the item is a CLAUDE.md doctrine proposal
already sitting on Discord/wrist awaiting J's reply since 2026-07-23 — `status:pending` in
queue.md AND in `conductor-proposals.jsonl`, but with no `eval_bar_cleared`, i.e. genuinely nothing
a conductor fire can DO except re-ping (spam on an 11-12 day old ask). The 2026-08-03 fire manually
noticed this, skipped to the #2 item, and named the fix in a queue.md addendum rather than build it
(scope discipline — one bounded task per fire). The SAME thing would have happened a 3rd time on
2026-08-04 had this fire not implemented the named fix.

## Root cause

`task_scorer.py`'s readiness model was single-file: it parsed `queue.md`'s own `status:` field
(after two prior fixes for multi-line/status-vocab gaps within that ONE file) but had zero awareness
that an item's real gating state can live in a companion ledger the FILING fire itself wrote to.
`status:pending` + satisfied `depends:` looked exactly like a genuinely actionable item, because the
distinguishing signal (a Discord approval-bus row, `status:pending` + no `eval_bar_cleared`) was
never cross-referenced.

## Fix (graduated to code same-fire, not left as prose)

`task_scorer.py` now loads `conductor-proposals.jsonl`, finds any `gp-...` proposal id named inside
a queue item's own block text (the filing fire always writes the id inline), and treats a
`status:pending`/no-`eval_bar_cleared` match as J-gated: suppressed from `ready` while <=14 days
old, resurfaces past 14 days as an explicit "RE-PING J" task (never "implement this"). Resolved
proposals, `eval_bar_cleared=true` proposals (auto-ratifiable edges, not human-reply-only gates),
and a missing/garbled ledger are all unaffected (fail-open toward surfacing on uncertainty, matching
the existing `_recency_explicitly_red` pattern in the same module).

10 guard tests, RED-proofed via `git stash`. Commit `5f79e3c9`.

## General pattern (for lesson-author to fold as a new L#)

A readiness/state parser over file A is not safe from silent staleness just because file A's own
format is fully understood — if file A's items can reference gating state that actually lives in
file B (a sibling ledger, a companion approval bus, an external proposal system), the parser needs
an EXPLICIT cross-reference step, or a class of "technically pending, actually blocked-on-a-human"
items will always look identically ready to a genuinely actionable one. This is the same shape as
C11 (broker is source of truth — two different READ endpoints for the same state can transiently
disagree) generalized to READINESS state instead of POSITION state: whenever two files both claim
to describe "is this item actionable", the parser must read BOTH, not just the one it started with.
