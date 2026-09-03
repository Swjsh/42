# Lesson inbox -- the hidden launch chain's rc=0 is never evidence the script ran

**Filed:** 2026-09-03 17:53 ET (Fable daytime session)  **Theme:** C7 silent success

**Symptom:** two newly registered nightly shadow tasks (Gamma_RetestZoneShadow, Gamma_StructureClassifierShadow) showed LastTaskResult=0 for every fire while their summaries never refreshed. One died at import (installer pointed at the system interpreter; the script transitively imports pandas), the other swallowed a KeyError inside a broad except before its write.

**Root cause:** `setup/scripts/run_exe_hidden.vbs` calls `shell.Run(cmd, 0, False)` -- fire-and-forget -- so Task Scheduler's LastTaskResult only records that wscript launched; the child's exit code lands only in `automation/state/logs/run-cmd-hidden-<date>.log` (`exit=N` lines). Every hidden-chain task (~160) shares this.

**Fix shape:** (1) treat rc=0 as no information; the evidence is the `exit=` line in the run-cmd-hidden log AND the output file's fresh stamp; (2) every new instrument's verification step must quote the output stamp after a real scheduled fire, not the scheduler rc; (3) graduate: extend `setup/scripts/scheduled_task_staleness.py` (Gamma_TaskStaleness 05:45 ET) to read each shadow task's summary `generated_at_et` and flag any task whose last fire did not advance it (queue item HIDDEN-CHAIN-OUTPUT-FRESHNESS-GUARD).

**Cross-refs:** L20/L27/L33 (headless spawn class), the 2026-09-03 STATUS daytime entry, commits fixing both scripts.
