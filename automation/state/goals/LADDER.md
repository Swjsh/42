# LADDER.md -- the goal-autopilot's ordered queue of durable Gamma goals

> Producer: `setup/scripts/goal_autopilot.py` (task A1, GOAL-GAMMA-AUTONOMY-2026-09-03).
> This is the ONE place judgment enters the autonomy loop -- the autopilot itself is
> a deterministic walker, never an LLM choosing between entries. Order = priority:
> the autopilot always opens the FIRST eligible `[ ]` line, top to bottom.
>
> Line grammar (ONE line per entry, grep-able, no continuation prose):
>   `- [ ] GOAL-<ID> :: <one line> :: file: automation/state/goals/GOAL-<ID>.md :: expires_days:14`
>
> Markers: `[ ]` queued (not yet opened) -- `[~]` active (this IS today's
> active-goal.json pointer) -- `[x]` done/closed (its DONE-WHEN was met, or it was
> closed expired/terminal; the goal file + its PROGRESS LOG/HONEST STATE remain the
> permanent audit trail, never deleted).
>
> Eligibility (checked at open time, never assumed from this line alone): the
> entry's `file:` must exist AND contain both a `## DONE-WHEN` heading and a
> `## QUEUE` section with at least one bare `- [ ] ` item. An entry that fails
> this check is SKIPPED (logged in goal-autopilot.json/.jsonl) and never opened --
> the autopilot walks past it to the next `[ ]` line rather than opening a goal
> with nothing left to do.
>
> Author new entries by appending a line (Claude sessions or J). Never delete a
> `[x]` line -- it is the ladder's own history.

- [x] GOAL-COCKPIT-REDESIGN-2026-09-03 :: Command-center overhaul: real design assets, Army+Autonomy merged, expandable tiles for every producer, judged >=7/10 (J 2026-09-03 18:50 ET) :: file: automation/state/goals/GOAL-COCKPIT-REDESIGN-2026-09-03.md :: expires_days:14
- [x] GOAL-TICKERS-LANE-2026-09-04 :: Three dedicated non-SPY 0DTE paper accounts trade the PRODUCTION scorer unmodified from 2026-09-04 (J 00:4x ET: 'they trade tomorrow ... test everything thoroughly') :: file: automation/state/goals/GOAL-TICKERS-LANE-2026-09-04.md :: expires_days:14
- [x] GOAL-GAMMA-AUTONOMY-2026-09-03 :: Gamma opens and drives its own goals; learning ledger; Autonomy tab :: file: automation/state/goals/GOAL-GAMMA-AUTONOMY-2026-09-03.md :: expires_days:14
- [x] GOAL-PREREG-ADJUDICATION-2026-09-03 :: 49 preregs with no status field -> 0, every frozen/never-run prereg adjudicated RUN/KILL/PARK :: file: automation/state/goals/GOAL-PREREG-ADJUDICATION-2026-09-03.md :: expires_days:14
- [x] GOAL-KITCHEN-KEEPERS-TO-SHADOW-2026-09-03 :: every kitchen _LEADERBOARD.md PROMISING candidate gets a WF+OOS verdict -> SHADOW-FILED or KILLED :: file: automation/state/goals/GOAL-KITCHEN-KEEPERS-TO-SHADOW-2026-09-03.md :: expires_days:14
- [~] GOAL-ZERO-ENTER-DAYS-2026-09-03 :: counterfactual table for every zero-enter frozen-window day + a $0 daily instrument, fix pre-registered for 10-30 :: file: automation/state/goals/GOAL-ZERO-ENTER-DAYS-2026-09-03.md :: expires_days:14
