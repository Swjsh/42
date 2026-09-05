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
- [~] H1 (WIP 2026-09-05 12:01 ET, Fable Saturday session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Known-broken upsert keeps the stamp on unchanged payload + wake watcher keys on content hash; 2 RED-proofed tests; watermark quoted stable across two engine_health runs.
- [~] H2 (WIP 2026-09-05 12:01 ET, Fable Saturday session a16e320c: one Sonnet chain -- other sessions do not pick up) -- phantom-account test reads the tickers roster; discriminating phantom case; file green.
- [~] H3 (WIP 2026-09-05 12:01 ET, Fable Saturday session a16e320c: one Sonnet chain -- other sessions do not pick up) -- GuardsFull freshness disagreement root-caused (one sentence) + fix-or-explain.
- [~] H4 (WIP 2026-09-05 12:01 ET, Fable Saturday session a16e320c: one Sonnet chain -- other sessions do not pick up) -- dead roster lane p::m repointed or floored; probe output quoted.

## J-DECISIONS
- None.

## PROGRESS LOG
- {now} ET -- authored by Fable (Saturday morning session) after the budget-lockout fix.
- 2026-09-05 12:01 ET — opened by goal_autopilot
## HONEST STATE
Queued. Nothing started.
