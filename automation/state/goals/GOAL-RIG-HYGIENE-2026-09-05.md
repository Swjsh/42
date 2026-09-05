# GOAL: RIG-HYGIENE-2026-09-05

> Opened by Fable 2026-09-05 15:xx ET. Two leftovers from the weekend loop that keep the rig honest
> without touching the engine: (1) the 24/7 Kitchen daemon (pid 15576) is still running pre-ship code
> after GOAL-KITCHEN-RUNNER-IN-LOOP because restarting it would kill a 6h grinder job -- the keepalive
> needs a restart-when-idle rule so shipped code goes live within one idle window instead of "whenever
> it next dies"; (2) the working tree carries ~3,000 untracked generated files (analysis/manager 852,
> kitchen-review 326, daily-brief 113, swarm-consult 112, crypto-twin 91, heartbeat-tick-audit 90, ...)
> -- OP-22 says every append-only producer has a retention cap and hitting it triggers consolidation.

## DONE-WHEN
(H1) `Gamma_KitchenDaemonKeepalive` (find the keepalive script via SCHEDULED-TASKS.md) restarts the
daemon when `kitchen-status.json` reads `idle: true` AND the daemon's start time predates the newest
mtime of the scripts it imports (kitchen_daemon.py, kitchen_stage1_runner.py, kitchen_reviewer.py,
chef_nemotron.py); never restarts while `idle: false`; logs the restart reason; guard test RED-proofed;
the live daemon is observed restarted on the new code (quote pid change + `kitchen-status.json`
`daemon_pid` + a run-log line from the new stage1 path) -- if the grinder is still busy at fire time,
say so and leave it for the keepalive's next idle fire rather than killing it. (H2) every untracked
generated directory has a retention policy recorded in `markdown/infra/RETENTION.md` (or the existing
retention doc if one exists -- find it first; append, never a parallel doc): keep-N / keep-days /
archive-to-monthly, applied by the producer's existing retention hook or by `setup/scripts/
status_retention.py`-style consolidation; `.gitignore` covers directories that are pure state (never
evidence); directories that ARE evidence (analysis/right-tail, zero-enter, gate-net-cost, doctrine-
parity, kitchen-review reports) stay tracked. After the pass `git status --porcelain | grep '^??' |
wc -l` is quoted before/after and nothing evidence-grade was deleted (list what was archived/pruned
by directory with counts).

## OPERATING RULES
- No engine, params, or FROZEN_TRADING_PATH edits. No deletion of anything a prereg, adjudication,
  or STATUS entry cites (grep before pruning; a cited file is evidence).
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation only.
- Dry-run first for any prune (POWERSHELL-COMPAT dry-run protocol); quote the dry-run counts, then apply.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] H1 (WIP 2026-09-05 15:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain H1-H4 -- other sessions do not pick up) -- Keepalive restart-when-idle (spec above); RED-proofed test; observed restart or an honest
  "still busy" with the next idle window named.
- [~] H2 (WIP 2026-09-05 15:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain H1-H4 -- other sessions do not pick up) -- Retention inventory: per untracked directory, producer script, current count, evidence or
  state, proposed policy; write the doc section.
- [~] H3 (WIP 2026-09-05 15:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain H1-H4 -- other sessions do not pick up) -- Apply: gitignore for pure-state dirs; retention hooks / consolidation for capped producers;
  dry-run counts then apply; before/after untracked count; list of what moved where.
- [ ] H4 -- Guard: a test that fails when an untracked generated directory has no retention entry
  (reads the doc table + a glob of the producers' output roots).

## J-DECISIONS
- None. Everything is revertible (gitignore lines; archives are moves, not deletes).

## PROGRESS LOG
- 2026-09-05 15:xx ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 07:21 ET — opened by goal_autopilot
## HONEST STATE
Queued. Nothing started.
