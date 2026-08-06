## Finding: a second, separate exit-code-capturing relay had zero readers too

**Date:** 2026-08-06 (conductor AFTERHOURS fire)
**Class:** C7 (silent success is failure — audit outputs, not exit codes), re-occurrence of the 2026-08-04/08-05 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT gap.

**What happened:** the 2026-08-04/08-05 fix (`self_check.check_run_cmd_hidden_masked_exit`)
closed the exit-code blind spot for the ~24 `Gamma_*` tasks routed through
`run_cmd_hidden.py`'s relay, and was written up as closing "the" gap. It did not: a live
enumeration of the actual scheduled-task fleet (`Get-ScheduledTask`) showed 108 tasks total
route through `run_exe_hidden.vbs`, and 84 of them — including safety-relevant tasks like
`Gamma_EodFlatten` / `Gamma_EodFlatten_Aggressive` / `Gamma_SightBeacon` — were NOT on that
relay. Most of those 84 turned out to be on a SECOND, independently-built relay
(`run_ps1_hidden.py`, dated to a "5/17 evening foot-gun fix" in its own docstring — it
predates the whole `run_cmd_hidden.py` investigation) that has ALSO been synchronously
capturing real exit codes to its own log (`run-ps1-hidden-<date>.log`) the entire time, with
zero consumers, completely independent of the first gap.

**Root cause (one sentence):** two different engineers/sessions independently built two
different "wrap the launcher so we can see the real exit code" mechanisms for two different
task shapes (python-direct vs `.ps1`-wrapper) at two different times, and neither session
checked whether a sibling relay with the same blind spot already existed before declaring
the class of bug closed.

**Generalizable guidance:** when a fix closes a producer/consumer visibility gap for ONE
launcher/relay/wrapper mechanism, explicitly enumerate ALL launcher mechanisms live (don't
trust a docstring's task count, `Get-ScheduledTask` and grep the fleet) before writing the
fix up as closing "the" gap. A "PARTIAL... 24/~150 tasks" scope note in the first fix's own
queue entry was the correct instinct but got read informally as "the gap is closed" by the
next fire's first pass — score/label partial fixes by exact fraction covered, not prose.

**Live finding this surfaced (evidence, not yet root-caused):** `run-eod-flatten-aggressive.ps1`
exited 1 on 3/3 recent trading days; `run-eod-flatten.ps1` and `run-sight-beacon.ps1` each
exited 1 once. Backstopped by the deterministic `Gamma_EodFlattenCore` (confirmed both
accounts flat every date via `engine-health.json`), so not a realized incident — but the
PRIMARY documented EOD-flatten path has apparently been silently degraded to backup-only on
most days, invisible until this fire's fix. Follow-up filed: `EOD-FLATTEN-LLM-PROMPT-EXIT1`
(queue.md, MED).

**Graduation candidate:** if a THIRD independent launcher/relay mechanism is ever found with
the same blind spot, this stops being a one-off and should graduate to a single registry
(one script/test that enumerates every `Gamma_*` task's Action string and asserts it routes
through a KNOWN exit-code-safe mechanism, the same shape as the watcher registry guard in
`backtest/tests/test_watcher_registry.py`) rather than a third bespoke `check_*_masked_exit`
sibling.
