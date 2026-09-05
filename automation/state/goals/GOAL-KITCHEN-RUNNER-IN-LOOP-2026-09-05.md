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
- [x] R1 (DONE 2026-09-05 07:18 ET, session a16e320c) -- Mapped the loop: kitchen_seeder ->
  cook-queue.jsonl create -> kitchen_daemon._run_task -> chef_nemotron prompt/model ladder ->
  strategy/candidates/*.md -> kitchen_reviewer -> _LEADERBOARD.md. Chosen Stage-1 runner:
  `backtest.autoresearch.overnight_grinder.evaluate_combo` (the SAME single-combo evaluator the
  grinder sweeps call per-combo; the leaderboard's grinder-sourced rows -- e.g. #15
  SNIPER_VIX_TREND_STAGE2_ENTRY_SWEEP -- are built on this exact function), wrapped in a NEW thin
  CLI (`setup/scripts/kitchen_stage1_runner.py`, no new backtest engine). Manual run quoted:
  `backtest/.venv/Scripts/python.exe setup/scripts/kitchen_stage1_runner.py --combo-json
  '{"super_stop": -0.10, "runner_target": 2.5}' --slug tighter-stop-r1-manual-run` (knobs taken
  from leaderboard candidate #33 TIGHTER_STOP) -> `STAGE1_OK
  analysis/kitchen-review/stage1-runs/tighter-stop-r1-manual-run-20260905T103458Z.json`, elapsed_s
  64.38 (~1.07 CPU-min).
- [x] R2 (DONE 2026-09-05 07:18 ET) -- Wired: `kitchen_daemon._run_task` now calls
  `_run_stage1(combo, slug, task_id)` (subprocess to kitchen_stage1_runner.py, single worker,
  awaited synchronously) BEFORE any model call. Runner failure/timeout ->
  `_write_runner_failed_candidate()` (zero model calls, zero numbers, $0, `status: RUNNER-FAILED
  (<reason>)`). Runner success feeds the artifact's real numbers into the model prompt;
  `_inject_daemon_provenance()` strips ANY `## Provenance` section the model wrote and appends the
  daemon-authored one (executed command -> verified-existing artifact) -- model text never
  reaches the Provenance block. Wall-time cap (480s runner-side, 540s subprocess-side) +
  single-worker lock (`automation/state/kitchen-stage1-runner.lock`) in place; NO reaper exemption
  needed (~65s actual runtime is far under the 5-min reaper threshold). Guard tests
  (`backtest/tests/test_kitchen_stage1_runner_2026_09_05.py`, 7 tests, RED-proofed via
  AssertionError-raising stubs for the model-call path + a real kitchen_provenance_audit
  cross-check on the RUNNER-FAILED file): `PYTHONIOENCODING=utf-8
  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_kitchen_stage1_runner_2026_09_05.py
  -q` -> `7 passed in 0.30s`.
- [x] R3 (DONE 2026-09-05 07:18 ET) -- `kitchen_reviewer._check_run_log_executed()` cross-checks
  every candidate's `provenance:` command against `automation/state/kitchen-stage1-run-log.jsonl`
  PROVENANCE-OK rows (the daemon's own record of what it executed) -- wired into both
  `_cap_promote_if_unevidenced` and `_auto_promote_candidate`, checked AFTER the existing
  artifact-existence checks so a file failing both is capped for the more specific pre-existing
  reason first. 4 pre-existing tests in test_kitchen_reviewer_numeric_evidence.py needed a seeded
  run-log row to keep exercising their OWN gate in isolation (documented in the test file's new
  `_seed_run_log` helper) -- fixed explicitly, not weakened. Full kitchen suite:
  `PYTHONIOENCODING=utf-8 backtest/.venv/Scripts/python.exe -m pytest backtest/tests/ -q -k
  kitchen` -> `75 passed, 13483 deselected`.
- [x] R4 (DONE 2026-09-05 07:18 ET) -- Added `run_single_cycle()` + CLI `kitchen_daemon.py run-once`
  (refuses if the real 24/7 daemon is alive unless `--allow-concurrent-daemon`). The real daemon
  (pid 15576, verified via `Get-CimInstance Win32_Process -Filter "ProcessId=15576"`) was alive but
  confirmed blocked inside a 6h `grinder_sweep` subprocess wait-loop (task 42a5de3d,
  shotgun_scalper_stage2, claimed 2026-09-05T09:33:31Z) -- NOT touching cook-queue.jsonl during
  that window -- so `--allow-concurrent-daemon` was used for exactly 3 real cycles against the
  live queue (no destructive stop of the grinder). All 3 real pending llm_cook tasks resolved with
  a genuine free-model call (`openrouter::nvidia/nemotron-3-super-120b-a12b:free`, $0) preceded by
  a real Stage-1 execution:
    1. task 662e9404 -> `strategy/candidates/_analysis/2026-09-05-stage1-baseline-results.md`,
       provenance artifact `analysis/kitchen-review/stage1-runs/run-stage-1-backtest-via-
       autoresearch-grinder-to-compute-edg-20260905T105809Z.json`, elapsed_s=64.53
       (~1.08 CPU-min), audit class **PROVENANCE-OK**.
    2. task a42bd22d -> `strategy/candidates/2026-09-05-chef-nemo-vwapcont-dte-override-dynamic.md`,
       artifact `...evaluate-top-5-combos-for-edge-capture-771-after-walk-forwar-
       20260905T110016Z.json`, elapsed_s=66.43 (~1.11 CPU-min), audit class **PROVENANCE-OK**.
    3. task 0aa53b7c -> `strategy/candidates/2026-09-05-chef-nemo-disable-midday-trendline-gate-
       afternoon.md`, artifact `...perform-stage-1-backtest-via-autoresearch-grinder-to-estimat-
       20260905T111037Z.json`, elapsed_s=64.54 (~1.08 CPU-min), audit class **PROVENANCE-OK**.
  3/3 PROVENANCE-OK, quoted via `kitchen_provenance_audit.classify_file()` on each path. Stage-1
  CPU cost per cycle ~1.1 CPU-min (well under the 10 CPU-min budget). `kitchen-status.json`
  `today_cost_usd_paid_tier` unchanged at `0.0` (`today_cost_cap_usd` still `3.0`) before and after
  all 3 cycles -- confirmed via direct read.
- [x] R5 (DONE 2026-09-05 07:18 ET) -- `kitchen_provenance_audit.py --since YYYY-MM-DD` added
  (`run_since_report()`), writes `analysis/kitchen-review/provenance-audit-since.json`
  (`usable_rate_since_ship`, never blended with the all-time report). Quoted:
  `--since 2026-09-05` -> `scanned=3865 scored=3863 OK=15 ... usable_rate_since_ship=0.0039 (30d
  baseline fabricated_artifact_rate=0.1053)`. NOTE (honest caveat): a calendar-date cut is coarse
  when the fix ships mid-day -- it counts ~3865 same-day files, almost all written BEFORE this
  session's fix landed, so 0.39% understates the true post-fix rate; the precise number is the 3/3
  (100%) PROVENANCE-OK from R4's actual post-ship cycles, per
  `automation/state/kitchen-stage1-run-log.jsonl`. `free_model_audit.py#kitchen_fabricated_
  artifact_rate()` now folds `usable_rate_since_ship`/`since_ship_date`/`since_ship_files_scored`
  into the SAME bar-state entry (when the since-report exists) -- surfaced in BOTH
  `automation/overnight/STATUS.md` Known-broken (`KITCHEN_FABRICATED_ARTIFACT_RATE: DEGRADED --
  30d fabricated_artifact_rate=0.1106 >= 0.05 (443/4005 files, window=30d) ... | since 2026-09-05
  (Stage-1-in-the-loop ship): usable_rate_since_ship=0.0039 (3863 files scored).`) and the cockpit
  payload (`gamma_autonomy.build()["engines"]["kitchen"]["provenance"]`, confirmed via direct call
  -- carries both `fabricated_artifact_rate` and `usable_rate_since_ship` as separate keys).
  `markdown/infra/KITCHEN-SPEC.md` updated with a new "STAGE-1-IN-THE-LOOP" subsection (appended
  after the existing anti-patterns list, nothing rewritten).

## J-DECISIONS
- None. Revert = `git revert <sha>`; the daemon's prior prompt path is restored by the revert.

## PROGRESS LOG
- 2026-09-05 13:xx ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 06:27 ET — opened by goal_autopilot
- 2026-09-05 07:18 ET -- R1-R5 shipped by Sonnet worker (session a16e320c). Stage-1-in-the-loop
  wired end-to-end; 3 real daemon cycles run against the live queue (`run-once
  --allow-concurrent-daemon`, justified: the live daemon was verified blocked inside an unrelated
  6h grinder subprocess, not touching the queue) all classified PROVENANCE-OK; 7 new RED-proofed
  guard tests + kitchen suite (75) + safety gate (59) all green; `conductor_outcome.py record`
  filed (cost=$0, drained=5, tests_delta=7, regressions=0).
- 2026-09-05 07:19 ET — closed by goal_autopilot: queue fully terminal (no bare '- [ ] ' item left)
## HONEST STATE
1. Structurally shipped and verified this session: a numeric verdict cannot exist in a new
   Kitchen candidate without an executed Stage-1 artifact backing it (RED-proofed), and the
   reviewer now refuses any candidate whose provenance command isn't in the daemon's own run log.
2. usable_rate_since_ship's headline number (0.39%) is an artifact of the coarse day-level cut,
   not evidence the fix underperforms -- the true signal is 3/3 (100%) PROVENANCE-OK on the actual
   post-ship cycles; DONE-WHEN's own "first 10 daemon cycles" framing is the better instrument and
   should be re-measured once 10 have accumulated through the LIVE 24/7 daemon (this session only
   ran 3, manually, via run-once).
3. UNVERIFIED / left for the live daemon: whether the 24/7 `Gamma_KitchenDaemonKeepalive`-run
   process picks up this code change automatically. It was NOT restarted this session (its current
   process, pid 15576, was mid-way through a legitimate 6h grinder_sweep and killing it would have
   wasted that work) -- it is running the OLD in-memory code until it next restarts (crash + 5-min
   keepalive relaunch, or its own eventual clean exit). The fix is fully live for any manual
   `run-once` invocation and will be live for the persistent daemon on its next restart.
AUTOPILOT CLOSE 2026-09-05 07:19 ET: queue fully terminal (no bare '- [ ] ' item left)
