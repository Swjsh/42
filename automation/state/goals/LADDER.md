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
- [x] GOAL-ZERO-ENTER-DAYS-2026-09-03 :: counterfactual table for every zero-enter frozen-window day + a $0 daily instrument, fix pre-registered for 10-30 :: file: automation/state/goals/GOAL-ZERO-ENTER-DAYS-2026-09-03.md :: expires_days:14
- [x] GOAL-RIGHT-TAIL-CAPTURE-2026-09-05 :: Standing instrument: did each arm catch the >=1.3x wave, hold to 2x, take the noon wave; gate refusals ledger for the 09-29 cap decision (J 09-05 ask) :: file: automation/state/goals/GOAL-RIGHT-TAIL-CAPTURE-2026-09-05.md :: expires_days:14
- [x] GOAL-CHECKPOINT-PACKET-2026-09-29 :: The 09-29 / 10-30 checkpoints become a generated packet: every prereg decision with its rule, live numbers and a mechanical verdict, regenerated nightly :: file: automation/state/goals/GOAL-CHECKPOINT-PACKET-2026-09-29.md :: expires_days:14
- [x] GOAL-KITCHEN-INTEGRITY-2026-09-05 :: Kitchen output that cites nonexistent artifacts (440 files) gets tagged, unpromoted, prompt-blocked and rate-gated; the 81 pct with no artifact become UNVERIFIED-BY-CONSTRUCTION :: file: automation/state/goals/GOAL-KITCHEN-INTEGRITY-2026-09-05.md :: expires_days:14
- [x] GOAL-FLEET-CAPTURE-GAP-2026-09-05 :: Why safe-3/bold-2 miss ~40 pct of the waves safe-2 takes: per-missed-wave mechanism + dollars, defects fixed, gate costs pre-registered for 10-30 :: file: automation/state/goals/GOAL-FLEET-CAPTURE-GAP-2026-09-05.md :: expires_days:14
- [x] GOAL-CHECKPOINT-REDUCTION-PACKAGES-2026-09-05 :: Every 09-29 reduction (score-ladder shadow retirement first) becomes a prepared, guarded, revertible package with apply.ps1 -- checkpoint day applies, never builds :: file: automation/state/goals/GOAL-CHECKPOINT-REDUCTION-PACKAGES-2026-09-05.md :: expires_days:14
- [x] GOAL-GATE-NET-COST-2026-09-05 :: per-gate net cost (refused winners minus refused losers, wave-deduped) so the 10-30 gate preregs are decidable; a gate may be found EARNING :: file: automation/state/goals/GOAL-GATE-NET-COST-2026-09-05.md :: expires_days:14
- [x] GOAL-RIGHT-TAIL-FOLLOWUPS-2026-09-05 :: fleet-gate-leak ledger covers min_triggers/confluence; runner-vs-tape-peak prereg for 10-30; 5-min OPRA bias measured as the net table's error bar :: file: automation/state/goals/GOAL-RIGHT-TAIL-FOLLOWUPS-2026-09-05.md :: expires_days:14
- [x] GOAL-EXIT-SHAPE-PARITY-2026-09-05 :: one live truth for the runner exit shape (params vs strategies.py vs CLAUDE.md disagree); doctrine text corrected; Rule-1 parity guard extended; runner_target 99.0 adjudicated :: file: automation/state/goals/GOAL-EXIT-SHAPE-PARITY-2026-09-05.md :: expires_days:14
- [x] GOAL-DOCTRINE-CODE-PARITY-SWEEP-2026-09-05 :: every numeric claim in CLAUDE.md / params docs / playbook checked against code + fills; drift corrected, dead knobs named, unapplied ratifications re-filed; parity guard extended :: file: automation/state/goals/GOAL-DOCTRINE-CODE-PARITY-SWEEP-2026-09-05.md :: expires_days:14
- [x] GOAL-TP1-FRACTION-AB-2026-09-05 :: TP1 0.8-vs-0.667 A/B on real fills under the live exit shape so the 09-29 reduction row is mechanical; playbook/risk-rules parity leftover :: file: automation/state/goals/GOAL-TP1-FRACTION-AB-2026-09-05.md :: expires_days:14
