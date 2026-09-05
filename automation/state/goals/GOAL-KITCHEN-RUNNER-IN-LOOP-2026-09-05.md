# GOAL: KITCHEN-RUNNER-IN-LOOP-2026-09-05

> Opened by Fable 2026-09-05 13:xx ET. The provenance audit (commit 11a45e2d; GOAL-KITCHEN-INTEGRITY)
> scored 4,193 Kitchen verdict files: 357 cite an artifact that exists, 440 cite artifacts that do
> not, 3,396 cite none. The reviewer now refuses the last two classes, which means the Kitchen's
> free-model loop currently produces almost nothing the rig can use. Root cause is structural: the
> chef prompt asks the model for a verdict + numbers; nothing in the loop RUNS anything. This goal
> puts the existing Stage-1 runner inside the loop so a verdict cannot exist without an executed
> artifact, and measures the before/after usable-output rate.

## DONE-WHEN
For every candidate the Kitchen daemon writes after this ships, `strategy/candidates/<file>.md`
carries a `## Provenance` block whose `provenance: <command> -> <artifact>` line names a runner
command the daemon actually executed and an artifact that exists (the provenance audit classifies
it PROVENANCE-OK); the runner is an EXISTING one (`backtest/autoresearch/` Stage-1 / base-engine /
canonical battery entry points -- no new backtest engine), invoked with the candidate's own knobs,
bounded in wall time and CPU (one worker, the grind-reaper exemption respected), on the free/local
data the Kitchen already has (BS-synthetic option data per memory project_free_kitchen_plan_b_hardened;
say so in every artifact -- it is mechanism evidence, never real-fills evidence); a candidate whose
runner fails or times out gets `status: RUNNER-FAILED (<reason>)` and no numbers. Measured: over the
first 10 daemon cycles after shipping, the share of new candidate files classified PROVENANCE-OK
(`setup/scripts/kitchen_provenance_audit.py`) vs the 30-day baseline (~8 pct), quoted. Cost stays $0
(no paid model tier; `kitchen-status.json` today_cost_usd_paid_tier unchanged).

## OPERATING RULES
- OP-31: the daemon NEVER touches heartbeat*/params*/CLAUDE.md, never places orders. Nothing here
  goes near FROZEN_TRADING_PATH.
- Cost discipline (OP-3): $0 -- free models + local CPU only; state the per-cycle CPU minutes.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation only.
- Reuse: markdown/infra/KITCHEN-SPEC.md, setup/scripts/kitchen_daemon.py, kitchen_reviewer.py,
  chef_nemotron.py (prompt template with the provenance requirement from GOAL-KITCHEN-INTEGRITY I3),
  kitchen_provenance_audit.py, the Stage-1 runner the leaderboard's own rows cite (find via
  strategy/candidates/_LEADERBOARD.md "Pre-merge gate" column and backtest/autoresearch/).

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] R1 (WIP 2026-09-05 13:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain R1-R5 -- other sessions do not pick up) -- Map the loop: seeder -> daemon task -> chef_nemotron -> candidate file -> reviewer ->
  leaderboard; where a runner could be invoked with the candidate's knobs; which existing runner
  (name the exact entry point + CLI) fits Stage-1 in <= 10 CPU-min on the local data; quote one
  manual run of it on an existing candidate's knobs producing an artifact under
  strategy/candidates/_analysis/ or analysis/kitchen-review/.
- [~] R2 (WIP 2026-09-05 13:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain R1-R5 -- other sessions do not pick up) -- Wire it: the daemon (or chef step) runs the runner BEFORE asking the model for a verdict,
  passes the artifact path + its summary numbers into the prompt, and writes the `## Provenance`
  block from the executed command (never from model text); runner failure -> RUNNER-FAILED status,
  no numbers. Wall-time cap + single-worker lock + grind-reaper exemption checked. Guard tests
  (RED-proofed): verdict without executed artifact is impossible; failure path writes no numbers.
- [~] R3 (WIP 2026-09-05 13:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain R1-R5 -- other sessions do not pick up) -- Reviewer: kitchen_reviewer refuses any new candidate whose provenance command was not
  executed by the daemon (cross-check a daemon-written run log, not the model's text); test.
- [~] R4 (WIP 2026-09-05 13:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain R1-R5 -- other sessions do not pick up) -- Run 3 daemon cycles manually (the daemon's own single-cycle entry point), quote the 3
  candidate files' provenance blocks and the audit classification (must be PROVENANCE-OK), CPU
  minutes per cycle, and `kitchen-status.json` cost fields unchanged.
- [ ] R5 -- Measurement instrument: `kitchen_provenance_audit.py` gains `--since <date>` and a
  `usable_rate_since_ship` figure; STATUS Known-broken KITCHEN_FABRICATED_ARTIFACT_RATE line and the
  cockpit tile show the post-ship rate separately from the 30-day rate; KITCHEN-SPEC.md updated
  with the new stage (append, do not rewrite).

## J-DECISIONS
- None. Revert = `git revert <sha>`; the daemon's prior prompt path is restored by the revert.

## PROGRESS LOG
- 2026-09-05 13:xx ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 06:27 ET — opened by goal_autopilot
## HONEST STATE
Queued. Nothing started.
