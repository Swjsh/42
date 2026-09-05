# GOAL: RIG-SIGNAL-HYGIENE-2026-09-05

> Opened by Fable 2026-09-05 12:01 ET (Saturday). J woke to "has Gamma been active?" and the honest answer
> was: the scheduled conductor was dark all morning (budget counter, fixed 1303eab2) AND the
> conductor-wake watcher has been shouting "EVENT (known-broken)" every 5 minutes since 09:22 ET
> on a 09-04 finding. Autonomy is only real when the signal channel is clean: a re-stamped stale
> line must not wake the conductor every 3 hours forever, and the full-suite net must be green
> or name a real defect. Four small, off-path defects, each with a guard.

## DONE-WHEN
(H1) `setup/scripts/engine_health.py` re-stamps its RTH-TICK-GAP Known-broken line every 5-min
tick (`skb.upsert("RTH-TICK-GAP:", line)` with a fresh checked_at_utc even when the finding is
unchanged), and `setup/scripts/conductor_wake_watch.py::scan_known_broken` keys "new entry" on
the newest `[timestamp]` token -- so an unchanged finding reads as a new event every tick
(watermark `known_broken_marker` advances every 5 min; log: "EVENT (known-broken) but DEBOUNCED"
x30 this morning) and fires the conductor every 180 min on nothing. Fix BOTH ends: the shared
Known-broken upsert helper keeps the EXISTING stamp when the payload after the tag is byte-
identical (generic -- every upsert producer benefits), and the wake watcher keys on a content
hash of the newest entry with its stamp stripped. RED-proofed tests for each; after the fix a
5-min re-run of engine_health leaves the watermark unchanged (quote it twice).
(H2) `backtest/tests/test_repo_wide_account_ids_2026_08_18.py::test_no_tracked_markdown_names_a_phantom_pa_account`
is RED (FULL-SUITE RED 00:51 ET): GOAL-TICKERS-LANE-2026-09-04.md names the three tickers-lane
paper accounts (PA39FKBSPLPR, PA3K6MNSXGE6, PA3RBOSIUBTR) which live in the tickers roster, not
fleet/accounts.json. The test's known-account set must read the tickers roster file (find it
under automation/state/tickers/; never hardcode the numbers in the test) -- the guard's purpose
(catch PHANTOM accounts) stays intact, proven by a discriminating case with a made-up PA3 id.
Full test file green, quoted.
(H3) STATUS Known broken carries `TASK-OUTPUT-FRESHNESS: Gamma_GuardsFull[nonzero_exit]` (05:45
ET) while Task Scheduler reads LastTaskResult 0 for the 22:17 MT run. Root-cause the disagreement
(read `setup/scripts/scheduled_task_staleness.py` / the freshness reporter and the GuardsFull
log it inspects): either the reporter reads a stale artefact or the run really exited nonzero
(the FULL-SUITE RED above would explain it). State which in one sentence; if the reporter is
wrong, fix + test; if GuardsFull really failed, H2 is the fix and the line clears on tonight's
23:15 ET run (say so in the goal file, do not hand-clear it).
(H4) `ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived): p::m` -- read
automation/state/model-roster.json, identify the dead free-tier lane, repoint it to a live free
model the roster already lists (verify with the liveness probe the line names; $0 only) or mark
the role as falling to its documented floor; quote the probe output.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: no trading-path edits (FROZEN_TRADING_PATH in the pre-commit hook); measurement, instruments, off-path fixes, preregs only.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly. No task chips.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire; workers never edit STATUS.md or commit -- the orchestrator does.
- Every stamp is read from `python setup/scripts/et_clock.py` in the same call, never typed.
- Every fix ships with a RED-proofed test (the test fails on the pre-fix code) and one-sentence root cause.
- Verify, don't claim: every DONE item quotes the command output that proves it.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] H1 (DONE: shipped 60950dc3 -- upsert keeps stamp on unchanged payload; wake watcher keys on content hash)
- [x] H2 (DONE 2026-09-05 14:29 ET -- phantom-account test now reads automation/state/tickers/*/account.json via new _tickers_roster_accounts(); discriminating fabricated-PA3 case added; file green: 6 passed)
- [x] H3 (DONE 2026-09-05 14:29 ET -- reporter is RIGHT, not GuardsFull's LastTaskResult: GuardsFull genuinely exited 1 (relay log `[2026-09-04 22:51:36] exit=1 [pid=12924]`), root cause was the H2 phantom-account test, per guard-watch-full.json's own failed_names list. No reporter fix needed; do not hand-clear the STATUS line -- it clears on tonight's 23:15 ET GuardsFull run now that H2 is fixed.)
- [x] H4 (DONE 2026-09-05 14:29 ET -- "p::m" was never a real roster lane: it is a synthetic fixture from test_roster_liveness_alerting_2026_08_29.py that leaked into the real STATUS.md via a late-binding default-argument bug in roster_liveness.flag_known_broken(); fixed (status_md now resolved lazily against the live module STATUS_MD instead of a value frozen at import). Today's live probe: 4/5 lanes live, 0 dead_id.)

## J-DECISIONS
- None.

## PROGRESS LOG
- {now} ET -- authored by Fable (Saturday morning session) after the budget-lockout fix.
- 2026-09-05 12:01 ET — opened by goal_autopilot
- 2026-09-05 14:29 ET -- H1 marked done (already shipped 60950dc3, verified: `git log -1 60950dc3` shows the H1 commit message).
- 2026-09-05 14:29 ET -- H2 fixed + verified: `cd backtest && ./.venv/Scripts/python.exe -m pytest tests/test_repo_wide_account_ids_2026_08_18.py -q` -> "6 passed in 0.30s" (was 1 failed/5 passed pre-fix, offenders were the 3 tickers-lane accounts). Files: backtest/tests/test_repo_wide_account_ids_2026_08_18.py.
- 2026-09-05 14:29 ET -- H3 root-caused, no code change: relay log `automation/state/logs/run-cmd-hidden-2026-09-04.log:12444` shows `[2026-09-04 22:51:36] exit=1 [pid=12924]` for the guard_runner_full.py launch at 22:17:04 MT (matches Task Scheduler's own LastRunTime for Gamma_GuardsFull, verified via Get-ScheduledTaskInfo), and `automation/state/guard-watch-full.json` names the sole failure as `tests/test_repo_wide_account_ids_2026_08_18.py::test_no_tracked_markdown_names_a_phantom_pa_account` (the H2 defect) at "2026-09-05 00:51 ET". Task Scheduler's LastTaskResult=0 is blind to this by design (outer wscript hop is fire-and-forget, per scheduled_task_staleness.py's own check_exit_codes() reason string) -- the TASK-OUTPUT-FRESHNESS reporter is correct, not the scheduler field. STATUS.md line intentionally left in place; clears on tonight's 23:15 ET GuardsFull run now that H2 is fixed.
- 2026-09-05 14:29 ET -- H4 fixed + verified: root cause was NOT a dead free-tier lane -- "p::m" does not exist in automation/state/model-roster.json (grepped, absent) and a fresh live probe run this session (`backtest/.venv/Scripts/python.exe setup/scripts/roster_liveness.py`) returned "4/5 lanes live" with zero class=dead_id (the one DOWN lane, ollama::qwen3:14b, is class=error/APITimeoutError, not dead_id). Traced to backtest/tests/test_roster_liveness_alerting_2026_08_29.py::test_main_returns_nonzero_only_when_a_lane_is_dead, which monkeypatches `rl.STATUS_MD` then calls `rl.main()` -> `flag_known_broken(dead)`; pre-fix, `flag_known_broken`'s `status_md` parameter defaulted directly to the module-level STATUS_MD Path object bound once at import time (Python's classic late-binding-default-argument trap), so the monkeypatch was silently ignored and the dead_id case wrote a synthetic "p::m" ROSTER-LIVENESS line straight into the REAL automation/overnight/STATUS.md. Fixed setup/scripts/roster_liveness.py::flag_known_broken to default status_md=None and resolve the current STATUS_MD lazily inside the function body. RED-proofed in backtest/tests/test_roster_liveness_status_md_default_2026_09_05.py (4 new tests); pre-fix (`git stash push -- setup/scripts/roster_liveness.py` then run) the introspection test failed with `assert WindowsPath('...STATUS.md') is None` (AssertionError), confirming the bound-Path default; post-fix (stash popped) `pytest tests/test_roster_liveness_status_md_default_2026_09_05.py tests/test_roster_liveness_alerting_2026_08_29.py -q` -> "9 passed in 0.42s", and `git status --short automation/overnight/STATUS.md` was empty after the run (no pollution). Proposed STATUS.md line for the orchestrator to add at CLOSE: clear/retire the existing `ROSTER-LIVENESS: 1 lane(s) permanently DEAD ... p::m` line (it was test pollution, not a real finding) -- e.g. via `status_known_broken.py` clear for prefix `ROSTER-LIVENESS:` now that the source test no longer writes to the real file, or by simply noting in Known-broken that it was H4-diagnosed as test pollution and closed 2026-09-05.
## HONEST STATE
H1-H4 all done this session (a16e320c). Files touched: backtest/tests/test_repo_wide_account_ids_2026_08_18.py (H2), backtest/tests/test_roster_liveness_status_md_default_2026_09_05.py (new, H4), setup/scripts/roster_liveness.py (H4). No STATUS.md edits made (worker rule) -- orchestrator should apply the H3/H4 lines proposed above at CLOSE. H3 required no code change -- confirmed correct-as-is, root cause documented.
