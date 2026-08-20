# Lesson candidate: bare-text audit regexes false-flag prose comments — twice in one night

**Date:** 2026-08-20
**Source:** Gamma_Conductor fire (after-hours, 18:37 ET)
**Theme fit:** C7 (audit outputs, not exit codes) + OP-25 (re-violated lesson graduates to code)

## Symptom
The 2026-08-14 incident roster's `no-console-popups` check RED-flipped twice in one
night on two INDEPENDENT audit scripts, both times because a bare-text regex matched
a doc COMMENT describing the fix, not an actual violation:

1. `test_no_ps1_bare_python` (05:36 ET fire) — a doc-comment line in
   `install-ledger-custody.ps1` happened to start with the literal text
   `python.exe`, matching `BARE_PYTHON_RE` even though it was prose.
2. `test_no_py_subprocess_missing_creationflags` (this fire, 18:37 ET) — a doc
   comment in `automation/scripts/mcp_audit_probe.py` reading
   "Every subprocess.run() call in this module carries creationflags." matched
   `SUBPROC_CALL_RE` (`subprocess\.(run|Popen|...)\s*\(`) because the prose
   literally contained `subprocess.run()`.

Both times the "fix" available in the moment was to reword the comment so it no
longer matched — which works for THAT instance but leaves the detector class
open to the next doc comment that happens to mention the audited pattern in
prose (a near-certainty in a codebase whose whole job is auditing subprocess
calls and bare-python invocations).

## Root cause
`setup/scripts/audit_window_leak_compliance.py`'s two text-regex detectors
(`_audit_ps1_bare_python`, `_audit_py_missing_creationflags`) scan raw file text
without excluding comment lines. Any regex-based code auditor that doesn't
strip/skip comments will eventually match the audit's OWN vocabulary inside a
comment describing the audit — the more precisely-named the flag (`subprocess.run`,
`creationflags`, `python.exe`), the more likely a maintenance comment near the
fix site will contain that exact string.

## Fix (shipped this fire, `_audit_py_missing_creationflags` only)
Skip any regex match whose line, once stripped, starts with `#` (a full-line
comment) before doing the paren-depth call-site scan. Guarded by
`test_comment_mentioning_subprocess_run_is_not_flagged`
(`backtest/tests/test_window_leak_compliance.py`).

**Not yet done:** `_audit_ps1_bare_python` (`BARE_PYTHON_RE`) still has the SAME
class of gap — its 05:36 ET fix was a comment reword, not a comment-skip in the
detector. If a future `.ps1` comment mentions `python.exe` again, it will
re-flag. Left out of THIS fire's bounded scope (only the RED item on tonight's
roster was in scope), but the fix is mechanical: mirror the same
`.lstrip().startswith("#")` (or PowerShell's `#`) check into
`_audit_ps1_bare_python` before the `BARE_PYTHON_RE.finditer` loop.

## Generalizable principle
A text-regex code auditor that hasn't excluded comments WILL eventually flag its
own documentation, and the failure mode compounds: every future maintenance
comment near an audited call site is now a landmine that can silently RED a
build-time ratchet. Any new regex-based audit in this codebase should skip
full-line (and ideally trailing) comments from day one, not discover the gap
per-incident. This is the second occurrence in one night — per OP-25 that is
the threshold for "graduate to code," which is why the fix above is a permanent
regression guard, not just a reworded string.
