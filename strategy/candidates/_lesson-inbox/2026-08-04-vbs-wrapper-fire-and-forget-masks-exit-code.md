# Lesson candidate: `run_exe_hidden.vbs`'s fire-and-forget launch makes Task Scheduler's `LastTaskResult` a FAKE success signal on 107 tasks

**Date:** 2026-08-04 (conductor AFTERHOURS fire)
**Class:** C7/C8 sibling -- a launcher-layer analogue of the 2026-07-31
"scheduled task can silently stop firing" lesson (already in-inbox/graduated),
one level deeper: this time the task WAS dispatched and DID run, but the
launcher hid its real outcome from Task Scheduler.

## What happened

`Gamma_RegimeStamp` (08:22 ET daily) ran today (`LastRunTime` = 2026-08-04
06:22 local / 08:22 ET, `LastTaskResult` = **0**), yet
`automation/state/regime-stamp.json` stayed frozen on YESTERDAY's content
(`date: "2026-08-03"`, `generated_at_et: "2026-08-03T08:22:03-04:00"`) --
caught independently by two instruments the same morning: this fire's own
`self_check.py` run (REGIME-STAMP DRIFT, DEGRADED) and the standing
`monday_verify.py` WS6 check in today's STATUS.md (RED).

Root-caused to two independently-real bugs stacked:

1. **The actual script crash:** `regime_stamp.py`'s `main()` called
   `STAMP_PATH.write_bytes(...)` directly (open-for-write in place). On this
   OneDrive-synced repo (`%OneDrive%` env var set; the whole user profile
   including `Desktop\42` is a Known-Folder-Move sync target) that raised a
   one-off `OSError: [Errno 22] Invalid argument` -- almost certainly a
   transient OneDrive/AV handle race grabbing the file at the exact moment of
   write. The exception was uncaught, so the real Python process exited
   nonzero.
2. **The launcher hid it.** Every one of these headless tasks (107 of the
   ~150 registered `Gamma_*` actions, grepped live this fire) runs through
   `setup/scripts/run_exe_hidden.vbs`, whose payload is:
   ```vbs
   shell.Run cmd, 0, False
   ```
   The **third argument `False` means "don't wait."** `wscript.exe` fires the
   child process and exits IMMEDIATELY with its own success code (0),
   *never* observing or propagating the child's real exit code. Task
   Scheduler's `LastTaskResult` therefore reflects "did wscript.exe launch
   successfully," not "did the wrapped Python script succeed" -- for **every
   one of the 107 tasks using this wrapper**, including
   `Gamma_HeartbeatCore` and other trading-critical tasks. `LastTaskResult=0`
   has been silently meaningless as a health signal this whole time.

## Why this is a genuinely new gap (not a duplicate of the 2026-07-31 lesson)

The 2026-07-31 lesson (`2026-07-31-scheduled-task-silent-stop-firing.md`,
already graduated) is about Task Scheduler declining to DISPATCH a trigger at
all (root cause never determined, remediated via a self-heal
`Start-ScheduledTask` retry). This is different: the trigger DID fire, the
process DID run, and it DID fail -- but the wrapper's fire-and-forget design
means Task Scheduler (and anyone reading `LastTaskResult` as a proxy for
script success, including future watchdogs) is structurally blind to that
failure. `LastTaskResult` is not "sometimes stale" here -- for every
`run_exe_hidden.vbs`-launched task, it can ONLY ever read the wscript
dispatch outcome, never the payload's.

## What was fixed THIS fire (scoped, low blast-radius)

`automation/scripts/regime_stamp.py`: both write sites (`STAMP_PATH`,
`BIAS_PATH`) now go through a new `_atomic_write_bytes_with_retry()` helper
(temp file in the same directory + `os.replace` atomic swap + up to 4
attempts with backoff on `OSError`). This closes bug #1 (the actual crash)
for this one script. Guard: `backtest/tests/test_regime_stamp_atomic_write_2026_08_04.py`
(6 tests, RED-proofed via `git stash` -- 5/6 correctly failed with
`AttributeError: module has no attribute '_atomic_write_bytes_with_retry'`
pre-fix). Curated safety gate 59/59 PASS. Live-verified: re-running the
script now writes `date: "2026-08-04"` and clears self_check's
REGIME-STAMP DRIFT flag (4 problems -> 3). Zero trading-path files touched
(this artifact is explicitly documented "DESCRIPTIVE ONLY -- never a live
entry input for the current day").

## What was NOT fixed this fire (deliberately, scope discipline)

Bug #2 (the vbs wrapper's fire-and-forget exit-code blind spot) touches the
SHARED launcher used by 107 tasks, including `Gamma_HeartbeatCore` -- the
live trading engine. Changing `shell.Run cmd, 0, False` to
`shell.Run(cmd, 0, True)` (wait=True) + `WScript.Quit(errcode)` would make
`LastTaskResult` trustworthy fleet-wide, but is a genuine blast-radius
change: it alters whether `wscript.exe` blocks until the child exits, which
could interact with Task Scheduler's own per-task execution-time-limit
settings differently than today's detached-process behavior, for tasks
nobody has audited against this specific change. This needs a dedicated
`/fable-blast-radius` pass (grep every task's execution-time-limit setting,
confirm none assume the current fire-and-forget semantics, and stage the
vbs change behind a NEW smoke test firing a deliberately-slow script through
it) before it touches the live-trading launch path -- not a same-fire
mechanical fix. Filed as `VBS-WRAPPER-EXIT-CODE-BLIND-SPOT` in `queue.md`
(HIGH, scoped follow-up, explicitly NOT touching `Gamma_HeartbeatCore`'s
trigger until validated on a low-frequency non-trading task first).

## Suggested guard once graduated

A drift/presence-ratchet style test that asserts: for any `Gamma_*` task
this codebase treats `LastTaskResult` as a success signal for (grep
`LastTaskResult` across `setup/scripts/*.py`), the task's action must NOT
route through `run_exe_hidden.vbs` in its current fire-and-forget form --
OR the consumer must independently corroborate via content-freshness (the
pattern `self_check.check_regime_stamp_daily()` already uses) rather than
trusting the field alone. This generalizes today's fix's "don't trust
`LastTaskResult`, verify content" principle into a standing rule for any
NEW watchdog written against this fleet.
