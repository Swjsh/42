# `automation/state/goals/` — the ONE home for durable multi-fire goals

Opened/read/closed via `/gamma-goal` (`.claude/skills/gamma-goal/SKILL.md`). One `GOAL-<ID>.md`
per goal, schema: `## DONE-WHEN` / `## OPERATING RULES` / `## QUEUE` /
`## J-DECISIONS` / `## PROGRESS LOG` / `## HONEST STATE`.

**Which one is live right now:** `automation/state/active-goal.json` — `active:true`
+ its `file` field points at the current goal. At most one active goal at a time.

**Two consumers already read the pointer:**
- `automation/prompts/conductor.md` STAGE 1 clause 0a — routes each scheduled fire
  to the active goal's top `[ ]` `## QUEUE` item.
- `setup/hooks/gamma_doctrine.py::_check_goal_continuation` (Stop hook, third
  clause) — keeps the current interactive session going up to
  `max_continuations_per_session` extra turns while the goal has open work.

**Who keeps `active-goal.json` filled in (2026-09-03, task A1
GOAL-GAMMA-AUTONOMY-2026-09-03):** `/gamma-goal` is `disable-model-invocation:
true`, so only J can open a goal by hand — without a second mechanism the pointer
just sits `active:false` between J's directives. `LADDER.md` (this directory) is
the ordered, human/Claude-authored backlog of goals; `setup/scripts/
goal_autopilot.py ensure` (registered `Gamma_GoalAutopilot`, every 30 min, 24/7,
pure stdlib, no LLM) walks it deterministically — opens the first eligible
queued (`[ ]`) entry whenever nothing is active/unexpired/non-terminal, and
closes a goal whose `## QUEUE` has gone fully terminal or whose expiry has
passed. The ladder is the only place judgment enters (which goals get queued,
in what order); the autopilot itself never chooses between entries.

## Files here

| File | Status |
|---|---|
| `GOAL-COCKPIT-BUILD-2026-08-29.md` | ACTIVE |
| `GOAL-REPLAY-TODAY-GREEN-2026-07-17.md` | archived/terminal — folded from `automation/overnight/GOAL-REPLAY-TODAY-GREEN.md` |
| `GOAL-ENGINE-VISION-2026-07-08.md` | archived/terminal — folded from `automation/state/engine-vision-goal.md` |
| `GOAL-OVERNIGHT-IMPROVE-2026-07-07.md` | archived/terminal — folded from `automation/state/overnight-goal.md` |

Never create a new ad-hoc `*-goal.md` outside this directory (OP-22) — that drift is
exactly what these three folds closed.
