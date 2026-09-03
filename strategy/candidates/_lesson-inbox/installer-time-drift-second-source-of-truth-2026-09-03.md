# Lesson inbox: an install script is a second source of truth for a trigger (2026-09-03)

**Symptom:** the 2026-09-03 evening self-heal sweep (commit dceb125e) re-ran three install scripts to add a
PT15M/PT30M repetition window and silently dragged Gamma_OosCheck / Gamma_GateRecency / Gamma_FreeModelAudit
back from the quiet-mode LOUD band (23:40 / Sun 23:35 / 23:48 ET) into the blackout (20:30 / 20:00 / 21:00 ET).
`test_quiet_mode_starvation` went RED in the next GuardsFull run (04:45 ET); caught before any fire was lost.

**Root cause:** on 2026-08-26 the tasks were re-timed LIVE with `Set-ScheduledTask`; the installers kept the
old `-At` values. Any later re-run of an installer (for any reason) reverts the live trigger to the stale time.

**Fix:** installers corrected to the registry's ET times and re-registered (commit 70935ba5); new guard
`backtest/tests/test_install_script_times_match_registry_2026_09_03.py` parses 46 installers against
`automation/state/SCHEDULED-TASKS.md` (84 unparseable/batch/dynamic listed in its docstring) and pins 9
pre-existing dormant drifts in a self-checking allowlist (queue INSTALL-SCRIPT-TIME-DRIFT-DORMANT-9).

**Rule:** a live trigger change is not done until the installer AND the registry row carry the same time in
the same commit. Class: C14 (translated-but-unapplied knobs) / C34 (state reverted backward by a re-run).
