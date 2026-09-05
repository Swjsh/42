# GOAL: CHECKPOINT-REDUCTION-PACKAGES-2026-09-05

> Opened by Fable 2026-09-05. The 09-29 safety checkpoint admits pre-registered kill-type risk
> REDUCTIONS only, each with its own prereg, guard, RED-proof and revert line, applied with
> GAMMA_FREEZE_OVERRIDE. The checkpoint packet (markdown/planning/CHECKPOINT-2026-09-29.md, generated
> nightly) already reads one reduction as RULE MET: retire the score-ladder-v2 rung shadow (KILLED
> 2026-09-05: extras net -$13,760 risky-1 / -$13,435 risky-3-era over 28 sessions). On 09-29 nothing
> should be built; everything should be a prepared package the conductor applies in minutes.

## DONE-WHEN
For every reduction row in the packet (today: score-ladder shadow retirement; plus any row that flips
to RULE MET before 09-28 and is classed reduction), a package exists under
`analysis/recommendations/packages/<row-id>/` containing: the exact diff (a `.patch` produced by
`git diff` against HEAD, touching only what the prereg names), the guard test that fails before and
passes after (RED-proof output quoted in README.md), the one-line revert (`git revert <sha>` or
`Unregister-ScheduledTask`), the packet row id it satisfies, and an `apply.ps1` that applies the patch,
runs the guard + `python backtest/tests/run_safety_gate.py`, and refuses if either is red. The packet
generator links each reduction row to its package path. Nothing is applied before 09-29.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: read-only instruments, preregs and packaged-but-unapplied
  changes only. Nothing in `setup/hooks/doctrine.py` FROZEN_TRADING_PATH is edited by this goal; a
  package is applied ONLY on its checkpoint day, by the conductor, with GAMMA_FREEZE_OVERRIDE in the
  invocation, after the packet reads RULE MET.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly. Fable/Opus = spec + adjudication only.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation are the only
  sanctioned continuation paths.
- Reuse before rebuilding; every number reported is quoted from a command run in the same fire (OP-33).

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] K1 (WIP 2026-09-05 07:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Score-ladder shadow retirement package: identify every organ the rung shadow owns
  (`Gamma_BoldTierRail` / `Gamma_ConvictionC4Sidecar`? -- read analysis/arm-ladder/ and
  automation/state/SCHEDULED-TASKS.md to name the exact task(s) + scripts + ledger writers), produce
  the patch that unregisters the task(s), tombstones the registry rows, and stops the ledger writer;
  guard test asserts the task is absent and the ledger no longer grows; README with RED-proof; apply.ps1.
  DONE-WHEN: `apply.ps1 -DryRun` prints the plan and exits 0 without changing anything.
- [~] K2 (WIP 2026-09-05 07:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Package scaffold: `setup/scripts/checkpoint_package.py new <row-id>` creates the folder
  layout + README template + apply.ps1 from a template, so later packages are mechanical; test.
- [~] K3 (WIP 2026-09-05 07:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Packet link: `checkpoint_packet.py` reduction rows carry `package:` path + `package_ready:
  true/false` (README + patch + apply.ps1 present); regenerate both CHECKPOINT files (via the script).
- [~] K4 (WIP 2026-09-05 07:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Cockpit: the Autopilot/Checkpoint tile shows "packages ready n/m" (DOM read quoted).

## J-DECISIONS
- None. Packages are inert until the checkpoint; revert lines inside each README.

## PROGRESS LOG
- 2026-09-05 06:5x ET -- authored by Fable (EOD-audit session); queued on the ladder.
## HONEST STATE
Queued. Nothing started.
