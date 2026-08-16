# Stale CRITICAL priority label survived 8 days past its own resolution

**Filed:** 2026-08-16 ~16:0x ET, conductor-weekend fire.

## Symptom

`CONDUCTOR-BUDGET-ARITHMETIC` sat in `queue.md` tagged `(CRITICAL, ... THE autonomy
blocker)` from 2026-08-08 through 2026-08-16 (8 days, several conductor fires in
between). `task_scorer.py --top`/`--all` kept ranking it near the top of the backlog
by priority weight. But both of its own two named sub-asks (re-measure the 2.16x
correction factor; find the real starvation cause) were **actually answered the same
evening it was filed** — the resolution lives in `conductor_budget.py`'s own module
docstring (a 2026-08-08 "RE-MEASUREMENT" + "CORRECTION" section with full citations)
and in `analysis/recommendations/conductor-cost-correction-measurement-2026-08-08.md`
— but nobody folded that resolution back into the `queue.md` item's own text or
closed/downgraded it. The CRITICAL label was doing real work (biasing every
subsequent fire's task-pick toward re-investigating a solved problem) purely because
nobody re-derived fresh evidence before trusting the label.

## Root cause

A fix landing in CODE (a module docstring, a shipped commit, a config default change)
does not automatically propagate back to the QUEUE ITEM that requested it, if the fix
was built as a spontaneous follow-up under a different informal name (here:
"LANE-A-UNSTARVE-CONDUCTOR", never itself a queue.md entry) rather than as an explicit
close-out of the original ticket. Priority labels (`CRITICAL`/`HIGH`/`MED`/`LOW`) are
static text written once at file-time; nothing re-validates them against current
reality. `task_scorer.py`'s ranking algorithm trusts the static label at face value —
it has no mechanism to notice "the evidence this label was based on is now 8 days
stale and the underlying metric has since gone quiet."

## Fix applied this fire

Re-derived fresh evidence before touching the item at all (`autonomy_report.py`:
7/7 ship this week, 0 `budget_exhausted` noops; grepped `conductor-outcomes.jsonl`
for every budget-exhausted row since 08-02: 13+1 through 08-08, then zero for 8+
days). Confirmed the acute problem is not currently occurring, downgraded the item
to MED with the evidence inline, and left an explicit re-open trigger ("if
`noop_reasons.budget_exhausted` goes non-zero again, re-open at HIGH").

## General lesson

Before spending a fire's effort on a CRITICAL/HIGH-labeled queue item, **re-derive
fresh evidence for the claim the label is based on** — don't inherit the priority at
face value from a filing that may already be stale. This is the same discipline C7
("silent success is failure — audit outputs, not exit codes") applied to the queue
itself, not just to producers: an unrevalidated priority label IS a silent-success
surface. If a re-derivation shows the label's own evidence has decayed, downgrade with
the fresh numbers inline (never silently leave the stale label for the next fire to
re-discover the same staleness).

## Candidate code assertion (if this recurs)

If a queue item's priority is found stale a 2nd time (this is currently a 1st
occurrence — do not over-build yet), consider having `task_scorer.py` flag any item
whose block text has NOT been touched in >14 days as `stale_evidence:true` in its
`--all` output (parallel to the existing `awaiting-j`/14-day staleness check it
already has for J-gated proposals), so a picker sees "this claim hasn't been
re-verified in N days" without having to manually grep outcome logs the way this fire
did.
