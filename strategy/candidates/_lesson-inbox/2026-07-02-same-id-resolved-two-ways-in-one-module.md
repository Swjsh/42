# Foot-gun: the same identifier resolved TWO ways in the same module silently disagrees

**Date:** 2026-07-02
**Surfaced by:** FIX-CD-2026-06-28-002-ID-COLLISION (conductor fire, commit 5e536ca)
**Theme:** C7 (silent success/divergence) + C14 (two consumers of one key drift apart)

## Symptom
`conductor-proposals.jsonl` had `cd-2026-06-28-002` on two DIFFERENT active proposals
(a BOLD-FLEET accounts.json change + the L192 CLAUDE.md doc-fold). A single J
`ship cd-2026-06-28-002` was ambiguous — and worse, the ambiguity resolved
DIFFERENTLY depending on which actuator code path ran.

## Root cause
`setup/scripts/autonomy_actuator.py` resolves a proposal_id two incompatible ways
within the SAME module:
- `sync_companion_approvals` builds `by_id = {r["proposal_id"]: r for r in rows ...}`
  (line ~155) — a dict comprehension, so on a duplicate the **LAST** row wins.
- `apply_approved` / `revert` use `next((r for r in rows if r["proposal_id"] == pid))`
  (lines ~580, ~699) — first-match, so the **FIRST** row wins.

So `ship <dup-id>` could flip one row to `approved` (last) while a later apply/revert
acts on the OTHER row (first). No error is raised; the disagreement is silent and lands
on an order/arm-adjacent surface.

## Fix shipped this fire
Split the ids (BOLD-FLEET orphan -> cd-2026-06-28-003; doc-fold keeps -002) +
`backtest/tests/test_proposal_id_uniqueness.py` guards ACTIVE-status id uniqueness so a
dup active id cannot exist. That closes the SYMPTOM at the data layer.

## Owed follow-up (defense-in-depth, NOT done this fire)
The resolution DIVERGENCE itself is the deeper foot-gun: if a dup ever slips in via a
race between the guard runs, the two paths still disagree silently. Harden the actuator
to fail LOUD on a duplicate id (raise/log, don't silently last-wins or first-wins), OR
route BOTH paths through one shared `resolve_proposal(pid, rows)` helper that is the
single source of truth. Generalize: **any time two code paths look up the same key with
different container semantics (dict vs linear scan), a duplicate key produces a silent
disagreement — pick ONE resolution helper, or assert-unique at the boundary.**
