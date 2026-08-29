# 📦 TOMBSTONE — this file moved

**Folded into the `/goal` schema 2026-08-29 (OP-22).** Same fold as
`automation/state/overnight-goal.md` and `automation/state/engine-vision-goal.md` —
three parallel ad-hoc "durable loop state" files, no shared schema, no consumer
wiring. That gap is why `/goal` was built.

➡️ **Full content now lives at**
[`automation/state/goals/GOAL-REPLAY-TODAY-GREEN-2026-07-17.md`](../state/goals/GOAL-REPLAY-TODAY-GREEN-2026-07-17.md)
(content preserved verbatim — this was already the most schema-like of the three, so
it got schema-alias headers inserted rather than a rewrite).

This goal reached its terminal, DONE state 2026-07-17 ~22:47 ET (see that file's
`## GOAL DISPOSITION`).

**Code still cites this filename in comments/docstrings** (e.g.
`backtest/lib/exit_manager_walk.py`, `backtest/tools/exit_manager_replay.py`,
`backtest/tools/regime_readjudication_correctexit.py`) — those citations are prose
references to a historical fact, not file reads (verified 2026-08-29: `grep -n
GOAL_DOC backtest/tools/replay_today_eval.py` shows the one `GOAL_DOC` path constant
in the codebase is defined but never actually opened). They remain valid; this
tombstone does not need to chase them.

🚫 Do not write new goal state here. Any future durable multi-fire goal is
`automation/state/goals/GOAL-<ID>.md`, opened via `/goal open "<quote>"`
(`.claude/skills/gamma-goal/SKILL.md`) — never a new ad-hoc `*-goal.md`.
