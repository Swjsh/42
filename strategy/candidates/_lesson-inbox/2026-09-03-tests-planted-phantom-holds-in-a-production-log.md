# Lesson candidate: a test suite that writes a production log becomes a producer of production state

**Class:** C7 (silent success is failure) + C34 (shared-checkout side effects revert live state) — a third sibling: *test side effects that FORWARD live state*.

**Observed (2026-09-02 23:47 → 2026-09-03 00:43 ET):** `quiet_mode.py`'s catch-up sweep started the same five
`CATCHUP_ELIGIBLE` tasks on every 5-minute enforcer cycle — 41 sweeps, `Gamma_McpDailyAudit` (an LLM fire) twelve times
an hour — with each task's real `LastRunTime` advancing every cycle. Found while verifying an unrelated build
(GUARDS-FULL-NEVER-RUNS-ON-A-GAMING-EVENING); the sweep's own log looked healthy line by line.

**Root cause (one sentence):** five test files imported `quiet_mode` without redirecting `LOG_FILE`, so every full-suite
run appended fixture lines (`QUIET HELD past the clock ... r5apex_dx12.exe`, weekday `PRESENCE -> research band` lines the
real code cannot produce on a weekday, `scheduler unreachable`) into the PRODUCTION `automation/state/quiet-mode.log`;
`scheduled_task_staleness.parse_quiet_holds` then read a phantom OPEN hold, closed it at `now`, and the sweep's
"already ran since the hold closed" idempotency test could never be satisfied.

**Why it was invisible:** every surface was individually consistent — the log said a hold was open, the sweep said it was
catching up, the tasks really ran. Only the *cadence* (identical five names, every 5 minutes) was wrong, and nothing
watched cadence. The fixture lines used the real game's process name, so even a human reading the log saw J gaming.

**Fixed:** `backtest/tests/conftest.py` autouse fixture redirects `quiet_mode.LOG_FILE/HOLD_FILE/STATUS_FILE/RESTORE_FILE`
for every test the moment the module is imported (proof: 113 quiet-mode tests, live log 1572 → 1572 lines);
`_catchup_sweep` defers while the latest hold is genuinely open; 53 provably-fake lines scrubbed (backup kept). Commit `8f69470e`.

**Generalisation worth a rule:** any module whose `_log()`/writer targets a path under `automation/state/` must be
isolated at the CONFTEST level, not per test file — per-file discipline is exactly what failed here (one file had it,
four did not). A grep for `automation/state` path constants in `setup/scripts/*.py` that are imported by tests, without a
matching conftest redirect, is the guard. Same family: `test_trades_enriched.py` rewrote the real `trades-enriched.jsonl`
the same night (fixed in `c362b5b2` with an mtime guard).
