# GOAL: GAMMA-AUTONOMY-2026-09-03

> J verbatim (2026-09-03 17:41 ET): *"i need automation. we have an entire 'goal' dashboard and
> nothing is driving it because im literally exhausted of using gamma like a chatbot. how do we get
> it to wakeup and fire off its own goals. we have a good strat that works but we need to be
> constantly testing more and learning and improving"* — then: *"your /goal is gamma autonomy"* —
> then: *"and i need to see it happening, on the dashboard"*.

## THE THREE ROOT CAUSES (verified 2026-09-03 17:42–18:05 ET, this session)

1. **Goal production is human-gated.** `.claude/skills/gamma-goal/SKILL.md` is
   `disable-model-invocation: true`. `active-goal.json` has been `active:false` since
   2026-08-30 13:20 ET. With no goal, `conductor.md` STAGE 1 falls through to tier 3
   (self-audit gaps: 64 rows since 08-27, 328 total) — the last 20 conductor fires were
   100% triage/hygiene/guard work, 0 strategy-learning items. Busy, not learning.
2. **The learning loop runs but never rolls up.** Kitchen: 3,787 completed / 57 pending
   (free-tier, `today_cost 0.0/3.0`). Prospector: 424 ideas, 95 promoted. 47 preregs and
   286 `strategy/candidates` files touched in 7 days; 131 commits in 24 h. SHADOW.md lists
   95 non-terminal preregs, 49 with `no status field`. Nothing scores this as "learned X".
3. **The autonomy panel exists and is never drawn.** `gamma_home.py:583` computes
   `payload["autonomy"]` (`gamma_autonomy.py`: awake/quiet/budget/recent_fires/next_move);
   `RENDER` in `gamma_cockpit_js.py:266` has no view for it; "autonomy" appears exactly once
   in the 717 KB page (the JSON key). `Gamma_Home` is absent from `quiet_mode.ESSENTIAL`
   (25 names), so the page stops regenerating 18:00–23:00 ET — J's evening.
   `Gamma_AutofireCards` has fired 0 cards ever: all 10 current cards are
   `autofire_safe:false` (alarms, not read-and-report).

## DONE-WHEN
Falsifiable, each checked by a command quoted in the PROGRESS LOG:
- (a) **Self-opening goals.** `python setup/scripts/goal_autopilot.py ensure` opens the top
  queued goal from `automation/state/goals/LADDER.md` whenever `active-goal.json` is
  inactive, expired, or has no bare `- [ ]` item left; closes a goal whose QUEUE is fully
  terminal; is registered as `Gamma_GoalAutopilot` (pure Python, $0) and runs before every
  conductor spawn. Proof: deactivate the goal in a temp copy → `ensure` re-activates the
  next ladder entry; test RED-proofed.
- (b) **The ladder is never empty.** ≥3 queued research goals exist with falsifiable
  DONE-WHENs, all freeze-compatible (research/shadow/prereg only, no trading-path file).
- (c) **A learning ledger.** `python setup/scripts/learning_ledger.py` writes
  `automation/state/learning-ledger.json` from existing ledgers only (kitchen, preregs,
  shadow tallies, candidates, conductor outcomes, commits, study, self-audit): today + 7d
  counts and the latest KILL/EXTEND/SHIP/NULL verdicts, each with its source path.
  Missing source → `NO DATA`, never a default.
- (d) **Visible on the dashboard.** `analysis/home/index.html` has an `Autonomy` PRIMARY
  tab rendering: the active goal (id, DONE-WHEN, QUEUE with states, PROGRESS LOG tail),
  next move, tonight's fire budget, recent fires with notes, the learning ledger, and the
  research engines' liveness (kitchen/prospector/autofire, honest). Overview shows a
  "Working on" strip. `Gamma_Home` and `Gamma_GoalAutopilot` are quiet-mode ESSENTIAL so
  the page keeps regenerating in the evening. Proof: regenerate, grep the DOM, screenshot.
- (e) **The conductor executes goal items.** The next scheduled conductor fire
  (00:10 ET) records a `conductor-outcomes.jsonl` row whose task_id is a goal QUEUE item.
  (Checked by the following session; this session verifies the routing clause reads the
  autopilot's output.)

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 → 2026-10-30**: nothing here touches `FROZEN_TRADING_PATH`.
  Goal/state files, page generators, a $0 scheduled task, `quiet_mode.ESSENTIAL`,
  `conductor.md` routing prose, and `run-conductor.ps1`'s pre-spawn step only. A ladder
  goal that would need a frozen edit is illegal — flag `[B-J]`, never queue.
- Every fire that touches this goal calls
  `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only.
- Never `/loop /gamma-goal`; the Stop hook's bounded continuation + `Gamma_Conductor`
  are the sanctioned continuation paths.
- Autopilot is deterministic: no LLM decides which goal opens; it walks the ladder in
  order. Ladder entries are authored by Claude sessions or J and are the one place
  judgment enters.
- `Gamma_Drive` stays dead; `Gamma_Conductor` is the live wake path (skill doc, 08-29).

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] A1 (VERIFIED by Fable: 36 tests green; `status --json` = noop, 1 active + 3 eligible queued; `ensure` noop on real state; Gamma_GoalAutopilot Ready rc=0; run-conductor.ps1 parses; ESSENTIAL has Gamma_Home + Gamma_GoalAutopilot; Gamma_Home re-enabled 18:35 ET inside quiet mode) — Build `setup/scripts/goal_autopilot.py` (`ensure` / `status --json` / `close-if-terminal`)
  + `automation/state/goals/LADDER.md` + `install-goal-autopilot.ps1` (`Gamma_GoalAutopilot`,
  every 30 min, never 09:30–15:55 ET) + registry row (169→170) + `quiet_mode.ESSENTIAL`
  += {Gamma_Home, Gamma_GoalAutopilot} + a pre-spawn `ensure` call in `run-conductor.ps1`
  (fail-open) + tests RED-proofed. DONE-WHEN (a).
- [x] A2 (VERIFIED 18/18 tests; real run today tasks=64 candidates=50 commits=137, 7d preregs_adjudicated=15, errors={}; Fable fixed prose-verdict false FAIL + UTC-as-ET before tick) — Build `setup/scripts/learning_ledger.py` + `automation/state/learning-ledger.json` +
  tests. DONE-WHEN (c).
- [x] A3 (VERIFIED by Fable: 86 tests green; page regenerated, vAutonomy=2 label=1 mojibake=0; in-app browser #autonomy + #overview render with real data, 0 console errors; Fable stripped raw markdown from goal text, fixed ladder chips and FROZEN-prereg false SHIP before tick) — Build the `Autonomy` view: `gamma_cockpit_autonomy_js.py`, VIEWS/RENDER/PRIMARY
  wiring, `payload["goal"]` + `payload["learning"]` in `gamma_home.py`, goal block in
  `gamma_autonomy.py`, Overview "Working on" strip, test. DONE-WHEN (d).
- [x] A4 (VERIFIED: 3 files 137/124/118 lines; doctrine.goal_next_open_item resolves P1/K1/Z1) — Author 3 queued research goals on the ladder (files in `goals/`, status queued):
  PREREG-ADJUDICATION (49 `no status field` → 0), KITCHEN-KEEPERS-TO-SHADOW (every
  `_LEADERBOARD.md` PROMISING candidate gets WF+OOS verdict → SHADOW-FILED or KILLED),
  ZERO-ENTER-DAYS (counterfactual table for every zero-enter frozen-window day + $0 daily
  instrument; fix pre-registered for 10-30). DONE-WHEN (b).
- [x] A5 (VERIFIED: clause 2a edited; page regenerated + DOM-grepped + rendered in-app 0 console errors; commit 5322e780; STATUS OPEN line; memory note written) — `conductor.md` STAGE 1 clause 2a: reads `goal_autopilot.py status --json`; if no
  active goal, runs `ensure` itself before falling through. Regenerate the page, quote the
  DOM grep + screenshot, commit with one-line revert, STATUS line, memory note.
- [x] A6 (CARRIED 2026-09-03 18:55 ET to GOAL-COCKPIT-REDESIGN-2026-09-03 item R7 by J's directive to switch goals; the first goal-driven fire will be proven there) — Next-fire verification.

## J-DECISIONS
- None required. Revoke = `git revert <sha>` + `Unregister-ScheduledTask Gamma_GoalAutopilot`.

## PROGRESS LOG
- 2026-09-03 18:05 ET — Opened by Fable from J's directive. Diagnosis above quoted from
  `conductor-outcomes.jsonl` tail, `kitchen-status.json`, `analysis/prospector/state.json`,
  `gamma_home.py:583`, `gamma_cockpit_js.py:266`, `quiet_mode.ESSENTIAL`, `autofire-ledger.jsonl`.
  A1–A3 dispatched to three Sonnet builders on disjoint file sets.

- 2026-09-03 18:12 ET — Stop-hook continuation reached session b6eea006 (the money-leak/trendline session, NOT the goal's owner). A5 is BLOCKED on A1 (`goal_autopilot.py status --json` still returns NO DATA; A1–A4 are `[~]` in the owning session). Skipped per the goal directive (blocked box -> skip), no files of this goal's lane touched. Owning session continues.

- 2026-09-03 18:20 ET — OWNERSHIP: session 42-98 (Fable, the goal's opener) owns A1–A5 tonight; four Sonnet builders are in flight on disjoint files (goal_autopilot/task, learning_ledger, Autonomy tab, research goals — A4 DONE). Other sessions reaching this goal via the Stop hook: do NOT start A1–A5; A6 is the next-fire check and needs the 00:10 ET conductor outcome.

- 2026-09-03 ~18:45 ET — A1–A5 DONE, commit 5322e780. Verified cold this session: goal_autopilot 36 tests + real ensure=noop + status shows 1 active/3 eligible; Gamma_GoalAutopilot Ready rc=0; learning_ledger 18 tests + real run (today tasks=64, candidates=50, commits=139; 7d preregs_adjudicated=15); Autonomy tab 86 tests, vAutonomy=2, 0 console errors, Overview strip present; quiet enforce tick left Gamma_Home Ready. Next open item = A6 (00:10 ET conductor fire must record a goal QUEUE item). Not verified: the slow graduated-guards run was still executing at commit time.

- 2026-09-03 18:41 ET — Stop-hook continuation 2/3 (session 42-98): A6 is time-gated on the next conductor fire (00:10 ET); stated null, no work possible now. Reworded A6 so that fire has a concrete self-verifying deliverable (quote autopilot status, record under the A6 task_id, tick, let the autopilot open the next ladder goal).

- 2026-09-03 18:42 ET — Stop-hook continuation 2/3 reached session b6eea006 again. A6 is a NEXT-FIRE verification (00:10 ET conductor), not doable now; skipped, not ticked. `goal_autopilot.py status --json` at 18:42 ET: {   "checked_at_et": "2026-09-03 18:20 ET",   "action": "noop",   "reason": "active goal has an open item",   "active_goal_id": "GOAL-GAMMA-AUTONOMY-2026-09-03",   "next_item": "A5 \u2014 `conductor.md` STAGE 1 clause 2a: reads `goal_autopilot.py status --json`; if no",   "ladder": [     {       "id": "GOAL-GAMMA-AUTONOMY-2026-09-03",       "state": "active",       "eligible": true,       "why": "
- 2026-09-03 18:55 ET — closed by goal_autopilot: queue fully terminal (no bare '- [ ] ' item left)
## HONEST STATE
A1–A5 shipped and verified (commit 5322e780). A6 is the only open item: it needs the next scheduled conductor fire (00:10 ET) to prove DONE-WHEN (e). Known soft spots: prereg verdict dates fall back to file mtime (labelled in methods); Gamma_AutofireCards still has never fired because every card is an alarm, not a read-and-report item (separate item, not this goal).
AUTOPILOT CLOSE 2026-09-03 18:55 ET: queue fully terminal (no bare '- [ ] ' item left)
