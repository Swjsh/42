## A FIFO-of-1 parser over a shared append-only log silently misattributes results under concurrent writers

**Symptom:** `self_check.py#check_run_cmd_hidden_masked_exit()` under-reported and
occasionally could have mis-attributed failures. Live evidence 2026-08-21: the day's
real `run-cmd-hidden-<date>.log` had 3208 `launching:` lines but the parser
(`_parse_run_cmd_hidden_log`, pair each `launching:` with the NEXT `exit=` line seen)
produced only 1944 completed records — a ~40% loss — because this relay routinely runs
5+ concurrent `run_cmd_hidden.py` processes that all append to the SAME shared
per-date log file, so their `launching:`/`exit=` lines interleave.

**Root cause:** the parser assumed strict sequential ordering (each `launching:` is
immediately followed by its OWN `exit=` line before the next fire's `launching:`
appears). That assumption is false the moment two writers run concurrently against a
shared append-only file with no per-writer identifier in the record. Worse than
undercounting: under real interleaving, an exit line can get paired with a DIFFERENT
script's `launching:` line entirely — a diagnostic instrument that blames the wrong
process is worse than no diagnostic, because it sends the next debugging session
looking at the wrong file.

**Generalizable rule:** before writing (or trusting) a parser over a log file that
MULTIPLE CONCURRENT PROCESSES append to, check whether the log format carries a
per-writer identifier (PID, request-id, correlation token). If it doesn't, either (a)
add one to the producer before trusting adjacency-based pairing, or (b) design the
consumer's record format to be self-contained per line (the sibling
`run_ps1_hidden.py` parser already does this — its exit line embeds the script name
directly, so it never needed pairing at all; that was a deliberate 2026-08-06 design
choice specifically to dodge this class, but the choice wasn't propagated back to the
already-shipped `run_cmd_hidden.py` sibling).

**Fix shipped 2026-08-21 (commit `ea0ba538`):** tag both the `launching:` and `exit=`
lines with the writer's own PID; pair by PID (dict keyed on PID, not scalar FIFO-of-1);
fall back to the old FIFO behavior only for legacy/pid-less lines so historical logs
and existing test fixtures still parse.

**Where else to check for the same shape (not audited this fire, flag for a future
pass):** any other append-only log/state file written by multiple concurrent
processes/tasks without a request-id or PID — a quick grep for
`.open("a", ...)` inside `setup/scripts/` combined with "does more than one scheduled
task write to this same path" would surface candidates. `run_py_venv_hidden.py`'s own
launcher log (the THIRD relay, shipped 2026-08-18) was not checked for this exact bug
this fire — worth a 10-minute look next time that file is touched.
