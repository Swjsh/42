# wscript hidden-launch chain structurally masks EVERY task's real exit code

**Symptom:** `Gamma_EodFlatten` + `Gamma_EodFlatten_Aggressive` both FAILED on 2026-07-08
(`=== END tick exit=1 ===`, "Error: Exceeded USD budget (1)") yet
`Get-ScheduledTaskInfo` showed `LastTaskResult: 0` for both — and
`preopen_readiness.py` trusted that masked 0, so the pre-open gate would have reported
GREEN on a day the flatten backstop was broken.

**Root cause (found by the 2026-07-09 overnight-drive flatten executor, verified live):**
the standard window-flash-free launch chain (SCHEDULED-TASKS.md §"Window hidden":
wscript.exe → run_hidden.vbs → pythonw) uses `Shell.Run cmd, 0, False` —
`WaitOnReturn=False` means wscript exits 0 the instant it LAUNCHES the child. Task
Scheduler records wscript's exit, so **LastTaskResult is structurally incapable of
reflecting the child's real outcome for EVERY task using this pattern** — which is most
of the ~69-task registry. This is not a flatten-specific bug; it is the pattern.

**Fix shipped (2026-07-09, commit 2b9d938, scope = flatten class only):** registered the
non-LLM `eod_flatten.py` as `Gamma_EodFlattenCore` (15:52 ET) and rewrote
`preopen_readiness.py` to read each flatten task's REAL log tail (`=== END tick exit=N ===`
/ structured outcome lines) instead of LastTaskResult, failing toward RED on
missing/stale evidence.

**The lesson to encode (C7-adjacent, graduate of OP-33a):** any monitor/gate/audit that
reads `LastTaskResult` (or any wrapper exit code) for a wscript-chained task is reading
NOISE — health checks must read the task's own output artifact (log tail, state file,
ledger row). Candidate guardrail: a grep-based guard asserting no monitoring surface
consumes `LastTaskResult`/`LastRunResult` for tasks whose action is wscript.exe, or a
sweep converting remaining critical-task checks (self_check, pulse, watchdogs) to
artifact-reads. Cross-ref: L-class "silent success is failure — audit outputs, not exit
codes" (C7); this adds the MECHANISM (WaitOnReturn=False) and the blast radius (the
whole registry).

**GUARDRAIL GRADUATED 2026-07-18 (conductor-weekend):** re-hit this exact mechanism live
-- `Gamma_MacroCalendar` showed `LastTaskResult=0` + `LastRunTime=2026-07-17 05:45` while
its own `refresh_log`'s last real entry was `2026-07-15` (a 2-day silent gap). Audited the
5 monitor/glance scripts (`self_check.py`, `engine_health.py`, `preopen_readiness.py`,
`gamma_glance.py`, `gamma_status.py`) with a repo-wide grep: confirmed the sweep this
lesson asked for is ALREADY effectively done -- `self_check.py`/`engine_health.py`/
`gamma_glance.py`/`gamma_status.py` have ZERO references to LastTaskResult (they already
read artifacts), and `preopen_readiness.py`'s one reference is the already-audited
cross-check-only exception (explicitly documented UNTRUSTED, real verdict comes from its
own log-tail parse). Shipped the missing piece: a repo-wide regression guard,
`backtest/tests/test_graduated_guards.py::test_no_monitor_trusts_lasttaskresult_as_authoritative`,
so a FUTURE monitor script can never silently reintroduce this trust (RED-proofed live:
injecting a bare `LastTaskResult` string into self_check.py made the test fail with the
exact expected assertion; removing it restored green). Also self-healed the acute finding
(ran `macro_calendar.py` by hand -- fresh refresh_log entry written, self_check clean) --
the ROOT infra bug (`run_exe_hidden.vbs`'s `Shell.Run cmd, 0, False`) stays unfixed by
design: flipping WaitOnReturn=True would make wscript BLOCK for the child's full runtime
across ~60 registered tasks including the live trading heartbeat, which is a much larger,
riskier change than fits one bounded conductor fire -- correctly left as a
propose-and-scope item, not silently attempted. Ready for lesson-author to assign an L#
and fold into LESSONS-LEARNED.md + the CLAUDE.md OP-25 index (recommend under C7 or a new
"exit-code trust across a fire-and-forget launch chain" sibling theme).
