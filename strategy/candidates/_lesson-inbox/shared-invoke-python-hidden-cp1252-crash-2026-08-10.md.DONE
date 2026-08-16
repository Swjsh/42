# Lesson candidate: headless PowerShell->Python launcher silently crashes on non-cp1252 stdout

> Queued by conductor (AFTERHOURS) 2026-08-10. lesson-author picks up at next wake fire.

## Symptom
`Gamma_KitchenReviewer` (`run-kitchen-reviewer.ps1`) exited 1 at 2026-08-10 04:50:07 ET.
`self_check.py` correctly flagged it as `RUN-PS1-HIDDEN MASKED EXIT` (a real non-zero
exit Task Scheduler's own `LastTaskResult` can never see through the wscript hop).
`kitchen-reviewer-2026-08-10.python.log` showed the real cause:
`UnicodeEncodeError: 'charmap' codec can't encode character '≥' in position 126`
inside `kitchen_reviewer.py`'s own `_log()` -> `print()` call, printing a free-LLM-
generated followup string containing "≥".

## Root cause
`setup/scripts/_shared.ps1`'s `Invoke-PythonHidden` -- the ONE shared launcher used by
**37** `setup/scripts/*.ps1` wrappers (grepped 2026-08-10), including
`run-heartbeat-core.ps1` and `run-heartbeat-aggressive.ps1` -- spawns its child with
`CreateNoWindow=$true`. A child with no real console falls back to the Windows ANSI
codepage (cp1252 on this box) for stdout/stderr instead of UTF-8. ANY script that prints
a non-cp1252 character (curly quotes, em-dash, `≥`/`≤`, emoji -- all routine in
free-LLM-generated text this repo pipes straight to `print()`) crashes with
`UnicodeEncodeError` and exits 1 -- silently, since Task Scheduler's `LastTaskResult`
can't see through the wscript hop either.

**This was a re-violated lesson, not a first occurrence**: `run-kalshi-tick.ps1` and
`run-kalshi-auto.ps1` already carried a local `$env:PYTHONIOENCODING = 'utf-8'`
workaround (added 2026-08-09, same crash class) via their OWN hand-rolled
`ProcessStartInfo` block -- but that fix was never backported to the SHARED
`Invoke-PythonHidden` function every other wrapper depends on. The prose/local fix
existed; the guardrail did not (exactly the OP-25/C14 "prose that gets re-violated is a
missing guardrail" pattern).

A second, related defect surfaced while proving the fix: even after
`PYTHONIOENCODING=utf-8` stops the CRASH, `.NET`'s `StreamReader` for the redirected
pipe decodes the child's now-genuinely-UTF-8 bytes using the CONSOLE codepage by
default -- producing silent mojibake in every captured `.python.log` (proven
empirically: `U+2265` round-tripped as `"Γ\xeb\xd1"`) unless
`$psi.StandardOutputEncoding` / `StandardErrorEncoding` are ALSO forced to UTF8.

## Fix
`setup/scripts/_shared.ps1` `Invoke-PythonHidden`: added
`$psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"` (stops the crash) AND
`$psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8` +
`$psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8` (stops the mojibake) --
both additive, no other line changed. Guard: `backtest/tests/test_invoke_python_hidden_utf8_stdout.py`
(3 tests: static source-assertion, a REAL subprocess repro of the exact `≥` crash
proving `ExitCode==0` + clean round-trip through the real function, and a regression
guard that the kalshi scripts' now-redundant-but-still-needed local workaround --
different ProcessStartInfo block, not covered by this fix -- isn't accidentally
removed). Full existing `_shared.ps1` blast-radius suite (`test_shared_ps_timeout_kill.py`,
8 tests) re-run clean, no regression.

## Encoded in
`backtest/tests/test_invoke_python_hidden_utf8_stdout.py` (new, 3 tests, all green).
Candidate C8 ("Headless Windows spawn = system-pythonw + CREATE_NO_WINDOW + WMI
liveness") in the CLAUDE.md OP-25 lessons index -- this is a new failure mode within
that same theme (encoding, not process liveness).

## L## (optional)
Next available L## per lesson-author's own max+1 grep (index currently runs through
L294 per CLAUDE.md as of this fire).
