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
- [x] K1 (DONE 2026-09-05 03:2x ET) -- Score-ladder shadow retirement package built under
  analysis/recommendations/packages/score-ladder-v2-shadow-retirement/: organs identified
  (task `Gamma_LadderRungShadow`, installer setup/install-ladder-rung-shadow.ps1, worker
  backtest/tools/score_ladder_rung_shadow_nightly.py, ledger analysis/arm-ladder/ladder-
  rung-shadow-ledger.jsonl, existing guard backtest/tests/test_score_ladder_rung_shadow_nightly.py,
  no params keys touched -- accounts.json carries none). change.patch/README.md/guard_test.py/
  apply.ps1 all present; `apply.ps1 -DryRun` prints the plan and exits 0; patch captured via
  git diff then reverted (git status clean on both touched files).
- [x] K2 (DONE 2026-09-05 03:2x ET) -- `setup/scripts/checkpoint_package.py new <row-id>` scaffolder
  built (README/apply.ps1/guard_test.py templates + empty change.patch placeholder);
  backtest/tests/test_checkpoint_package_scaffold_2026_09_05.py (7 tests) passes. Used live to
  scaffold analysis/recommendations/packages/tickers-theta-budget-cadence/ (scaffold-only,
  INSUFFICIENT N -- no real patch yet).
- [x] K3 (DONE 2026-09-05 03:2x ET) -- checkpoint_packet.py reduction rows now carry
  `package`/`package_ready` (additive, read-only `_package_status()`); both CHECKPOINT-*.md
  regenerated via the script. score-ladder-v2-shadow-retirement reads package_ready=true,
  tickers-theta-budget-cadence reads package_ready=false (scaffold-only). Markdown shows
  "Packages ready: 1/2 reduction rows." New test file
  backtest/tests/test_checkpoint_packet_package_field_2026_09_05.py (6 tests) added
  separately from the concurrently-hand-checked test_checkpoint_packet_2026_09_05.py (C6
  lane) to avoid an edit collision.
- [x] K4 (DONE 2026-09-05 03:2x ET) -- setup/scripts/gamma_autonomy.py's checkpoint_packet
  block now rolls up packages_ready/packages_total; dashboard/components/cockpit/producer-tiles.tsx
  Autopilot tile renders "packages ready n/m". Regenerated gamma-companion/public/payload.json
  via gamma_home.py and DOM-verified live in the cockpit preview: find("packages ready") ->
  "Awake — Kitchen DEGRADED (11.0%) — Checkpoint 3✓/0✗/5⋯ — packages ready 1/2".

## J-DECISIONS
- None. Packages are inert until the checkpoint; revert lines inside each README.

## PROGRESS LOG
- 2026-09-05 06:5x ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 03:2x ET -- K1-K4 all DONE (Sonnet worker-tier session a16e320c). Package
  shipped for score-ladder-v2-shadow-retirement (package_ready=true); scaffold-only for
  tickers-theta-budget-cadence (INSUFFICIENT N, no patch content yet). Scaffolder
  (checkpoint_package.py) + packet package_ready field + cockpit tile all built and
  verified this fire. Ran into a concurrent C6 hand-check session editing
  checkpoint_packet.py's `_score_tight_ladder_control4` scorer + its test file mid-fire
  (unrelated expansion row, ledger-drift flakiness observed and left alone, not part of
  this goal's scope) -- coordinated per the goal's brief by keeping K3 additive and in a
  separate new test file.

## HONEST STATE
1. K1-K4 all shipped this fire; nothing was applied to the live trading path -- verified
   `git status --porcelain` clean on both score-ladder package-target files and
   `Get-ScheduledTask -TaskName Gamma_LadderRungShadow` still State=Ready.
2. `tickers-theta-budget-cadence` package is scaffold-only (empty change.patch, guard_test.py
   still the K2 red-by-default template) -- correct, since its packet row reads
   INSUFFICIENT N (n=3 fills, needs >=15) and the goal only requires the scaffold to
   "accommodate it," not to ship a real patch before evidence exists.
3. `pytest -k "checkpoint or package"` and `run_safety_gate.py` both quoted green in the
   goal report; one unrelated pre-existing test (`test_right_tail_control4_row_...`,
   classification=expansion, outside this goal's reduction scope) flickered red/green
   across the fire due to a concurrent session's ledger writes -- flagged, not fixed,
   not this goal's organ.
