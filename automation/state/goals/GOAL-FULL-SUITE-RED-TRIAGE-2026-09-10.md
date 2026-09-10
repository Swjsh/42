# GOAL: FULL-SUITE-RED-TRIAGE-2026-09-10

> Opened by conductor AFTERHORS fire 2026-09-10 05:30 ET (ladder was genuinely empty after
> fixing GOAL-GATE-EXPIRY-RECONCILE-2026-09-05 and GOAL-FUTURES-YELLOWS-2026-09-05 sitting
> stuck `[ ]` in LADDER.md despite being fully done -- see this fire's own PROGRESS LOG /
> `setup/scripts/goal_autopilot.py::reconcile_stale_done` for that fix). STATUS.md's own
> "Known broken" carries an un-actioned 2026-09-10 00:18 ET line:
> `FULL-SUITE RED :: 13762 passed, 19 failed, 19 skipped` across 11 distinct test files
> (`test_arm_roster_sweep_2026_09_02.py`, `test_crypto_twin_reaper_exemption.py` x2,
> `test_dojo_engine_step.py`, `test_earnings_calendar_install_wiring_2026_08_24.py` x2,
> `test_engine_liveness_guards.py` x4 (parametrized), `test_gap_prior_close.py`,
> `test_install_script_relay_wiring_drift.py`). A RED full-suite line that nobody re-runs or
> triages is exactly the OP-22 "accumulating, not compounding" anti-pattern -- and several of
> these look install/wiring-drift shaped (the same class the 2026-08-24/09-02 guards were
> built to catch), which is worth knowing about even if the underlying installers are fine.

## DONE-WHEN
(T1) `cd backtest && python -m pytest tests/ -q -m "not slow"` re-run fresh THIS goal (not
re-derived from the stale 00:18 ET line) -- quote the current pass/fail/skip counts. Some of
these may have already self-resolved (the GATE-EXPIRY items on 09-07 and the phantom-account
test on 09-05 both self-resolved between fires without anyone touching the code) -- state
which of the original 19 are still failing NOW vs which already cleared.
(T2) Every STILL-FAILING test gets a one-sentence root cause + a disposition: FIX (code/install
script defect, ship with a RED-proofed guard extending the failing test itself if it was
mis-asserting, or a real code fix if the assertion is correct), STALE-ASSUMPTION (the test
pins a fact that changed for a legitimate reason -- update the test, name the change), or
FLAKY (non-deterministic; name the mechanism, e.g. timing/ordering, and fix or quarantine with
a comment, never silently skip).
(T3) A dated correction/disposition line for each of the 11 files in STATUS.md's Known-broken
FULL-SUITE RED entry (rewritten through this goal's own close, not by hand-duplicating a new
bullet) OR, if the count changed, the corrected count and file list.
(T4) Full suite re-run one more time post-fix: quote the final pass/fail/skip counts. If
anything is a genuine, currently-irreducible flake, name it explicitly rather than claiming a
clean 0-fail suite that isn't real (OP-33 -- suspicion scales with how good a number looks).

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: no trading-path edits (FROZEN_TRADING_PATH in
  the pre-commit hook) -- every one of the 11 files above is test/install-wiring, not a
  trading-path file, but re-verify against `setup/hooks/doctrine.py` before touching anything;
  if a fix genuinely requires a frozen-path edit, flag `[B-J]` instead of shipping it.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent`/`Workflow` fan-out passes `model:"sonnet"` explicitly. No task chips.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire; workers never edit STATUS.md
  or commit -- the orchestrator does.
- Every stamp is read from `python setup/scripts/et_clock.py` in the same call, never typed.
- Every fix ships with a RED-proofed test (fails on pre-fix code) and a one-sentence root cause.
- Verify, don't claim: every DONE item quotes the command output that proves it.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [ ] T1 -- fresh full-suite run, current fail list quoted (which of the original 19 still fail).
- [ ] T2 -- each still-failing test: root cause + disposition (FIX/STALE-ASSUMPTION/FLAKY), fixed or filed.
- [ ] T3 -- STATUS.md Known-broken FULL-SUITE RED line corrected/closed with the real current state.
- [ ] T4 -- final full-suite re-run quoted, any remaining irreducible flake named explicitly.

## J-DECISIONS
- None yet -- flag here if any disposition needs a frozen-path exception.

## PROGRESS LOG
- 2026-09-10 05:30 ET — opened by conductor AFTERHOURS fire after fixing the goal_autopilot
  stale-ladder-entry bug (reconcile_stale_done) that had left GOAL-GATE-EXPIRY-RECONCILE and
  GOAL-FUTURES-YELLOWS stuck `[ ]` since 2026-09-05 despite being fully done. Ladder was
  genuinely empty (only remaining `[ ]` entry, GOAL-SEPT-MIDWINDOW-READ-2026-09-15, is
  not_before-gated until 09-15) -- authored this goal per conductor STAGE 1 clause 2a rather
  than leaving the next scheduled fire to hit the same ladder_empty with nothing to do.
- 2026-09-10 05:37 ET — opened by goal_autopilot
## HONEST STATE
Not started. The 19-failure count is UNVERIFIED as of right-now-2026-09-10 05:30 ET -- it is
quoted verbatim from STATUS.md's 00:18 ET entry, itself already ~5 hours old and this repo has
a documented pattern (09-05/09-07 GATE-EXPIRY items) of RED-looking lines self-resolving between
fires without anyone touching code. T1 exists specifically to re-verify before assuming anything.
