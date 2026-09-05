# GOAL: RIG-HYGIENE-2026-09-05

> Opened by Fable 2026-09-05 ~05:00-07:40 ET (stamp corrected: earlier value was inferred, not read from et_clock). Two leftovers from the weekend loop that keep the rig honest
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
- [x] H1 (DONE 2026-09-05 07:37 ET, Sonnet chain a16e320c) -- `setup/scripts/kitchen_daemon_restart_policy.py`
  (pure `decide_restart(idle, daemon_start_utc, script_mtimes_utc)` + I/O wrapper) wired into
  `run-kitchen-daemon-keepalive.ps1`'s alive-and-fresh branch via `Invoke-PythonHidden`; restarts ONLY
  when idle=true AND daemon start predates newest watched-script mtime, logs the reason, never touches a
  busy daemon. RED-proofed: `backtest/tests/test_kitchen_daemon_restart_policy_2026_09_05.py` (7 tests) +
  confirmed a naive "restart if stale regardless of idle" impl returns True on the busy case (would fail
  the guard). Observed: pid 15576 (kitchen-status.json daemon_pid 23904 — pre-existing pid-vs-status
  mismatch, UNVERIFIED why, not this goal's scope) is `idle: false` (updated_at_et 07:09, current_task_id
  set) as of 07:24 ET — busy, correctly NOT killed; the keepalive now auto-fires this check every 5 min
  (Gamma_KitchenDaemonKeepalive), so the next idle tick restarts it without manual action.
- [x] H2 (DONE 2026-09-05 07:37 ET) -- No prior retention doc existed (grepped markdown/infra first).
  Authored `markdown/infra/RETENTION.md`, linked from `markdown/README.md`'s infra row. Full inventory
  table: producer script, untracked count, evidence-or-state, policy for every directory `git status
  --porcelain` surfaced with >=5 untracked files (manager 874, daily-brief 113, swarm-consult 112,
  free-model-audit 95 across 4 subdirs, crypto-twin/reviews 86, autopsies 77, automation/state loose
  dated prefixes 623 combined across 11 producers, eod 45, gym 48, participation-cascade 33, +7 small
  <10-file dirs deferred). Evidence-grade dirs (recommendations, journal, deep-research .md, right-tail/
  zero-enter/gate-net-cost/doctrine-parity/kitchen-review/winner-autopsies — the last 6 already 0
  untracked) explicitly marked no-action.
- [x] H3 (DONE 2026-09-05 07:37 ET) -- `setup/scripts/retention_sweep.py` (dry-run default, `--apply`
  flag, MOVE via shutil never delete, scoped to untracked files only, skips any filename cited under
  markdown/STATUS.md/recommendations). Dry-run quoted 1193 candidate moves; applied: 1193 moved into
  `<dir>/_archive/YYYY-MM/`. `.gitignore` appended for the pure-state archive dirs + deep-research scratch
  json globs. Before/after `git status --porcelain | grep '^??' | wc -l`: 2742 -> 1537 (NOTE: this metric
  undercounts the effect since git collapses a newly-all-untracked directory to one porcelain line — the
  file-level move count is the trustworthy number: 1193 quoted above).
- [x] H4 (DONE 2026-09-05 07:37 ET) -- `backtest/tests/test_retention_doc_coverage_2026_09_05.py`:
  re-derives live untracked top-2-segment dirs (>=5 files) from `git status --porcelain` each run and
  fails if any isn't covered by `retention_sweep.py`'s DIRECTORIES or the doc's no-action allowlist.
  RED-proofed via `test_fails_on_an_undocumented_directory` (fabricated dir, asserted flagged). First run
  caught 7 real undocumented dirs (backtests/conviction/fleet-weekly/futures-eod/multi-lane/prospector/
  automation-swarm) — documented + allow-listed (all <10 files, deferred per doc).

## J-DECISIONS
- None. Everything is revertible (gitignore lines; archives are moves, not deletes).

## PROGRESS LOG
- 2026-09-05 ~05:00-07:40 ET (stamp corrected: earlier value was inferred, not read from et_clock) -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 07:21 ET — opened by goal_autopilot
- 2026-09-05 07:37 ET -- H1-H4 all DONE by Sonnet worker chain (session a16e320c). 168 pytest
  passed (-k "keepalive or retention or kitchen"), safety gate 59 passed, 0 regressions.
  conductor_outcome.py recorded (tests-delta 11, drained 4, added 0). No commit made (per
  OPERATING RULES) -- working tree has the new files + gitignore + moved archives, ready for
  the next weekend/after-hours commit pass.
- 2026-09-05 07:38 ET — closed by goal_autopilot: queue fully terminal (no bare '- [ ] ' item left)
## HONEST STATE
H1: keepalive now restarts on idle+stale-code, never mid-job; the live daemon (pid 15576) was
BUSY at observation time so it was correctly left alone -- not yet observed restarting on new
code this session (that will happen on its own next idle 5-min tick; UNVERIFIED until then).
H2/H3: retention doc + sweep shipped and applied -- 1193 files archived (moved, not deleted),
untracked porcelain count 2742->1537. Small (<10-file) research dirs deliberately deferred, not
swept -- see RETENTION.md's no-action row. H4: guard is live and already proved itself by
catching 7 real undocumented directories on first run.
AUTOPILOT CLOSE 2026-09-05 07:38 ET: queue fully terminal (no bare '- [ ] ' item left)
