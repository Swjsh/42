# 📦 TOMBSTONE — this file moved

**Folded into the `/goal` schema 2026-08-29 (OP-22).** Same fold as
`automation/state/overnight-goal.md` and `automation/overnight/GOAL-REPLAY-TODAY-GREEN.md`
— three parallel ad-hoc "durable loop state" files, no shared schema, no consumer
wiring. That gap is why `/goal` was built.

➡️ **Full content now lives at**
[`automation/state/goals/GOAL-ENGINE-VISION-2026-07-08.md`](goals/GOAL-ENGINE-VISION-2026-07-08.md)
(reformatted into the DONE-WHEN / OPERATING RULES / QUEUE / J-DECISIONS / PROGRESS
LOG / HONEST STATE schema — content preserved, not summarized).

This goal reached its terminal state 2026-07-08 (see that file's `## HONEST STATE`).

🚫 Do not write new goal state here. Any future durable multi-fire goal is
`automation/state/goals/GOAL-<ID>.md`, opened via `/goal open "<quote>"`
(`.claude/skills/goal/SKILL.md`) — never a new ad-hoc `*-goal.md`.
