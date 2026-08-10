"""Guard for the PYTHONIOENCODING fix (2026-08-10), filed after kitchen_reviewer.py
crashed under Task Scheduler with:

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2265' in position 126

ROOT CAUSE: setup/scripts/_shared.ps1's Invoke-PythonHidden launches its child with
CreateNoWindow=$true -- no real console is allocated, so Python's stdout/stderr fall
back to the Windows ANSI codepage (cp1252 on this box) instead of UTF-8. Any script
that prints a non-cp1252 character (curly quotes, em-dash, >=/<=, emoji -- all routine
in free-LLM-generated text this repo pipes straight to print(), e.g. kitchen_reviewer.py
logging a followup string verbatim) crashes with UnicodeEncodeError and exits 1 --
silently, from Task Scheduler's point of view (LastTaskResult still looks like "ran").

This was NOT a one-off: run-kalshi-tick.ps1 and run-kalshi-auto.ps1 already carried a
local `$env:PYTHONIOENCODING = 'utf-8'` workaround (2026-08-09), proving the class of
bug had already been hit and fixed once -- just never backported to the SHARED launcher
every other wrapper (including the live heartbeat wrappers) depends on. That is exactly
the "re-violated lesson -> graduate to a code assertion" pattern (OP-25/C14): the prose
fix existed in two files; it needed to live in the one function all 37+ callers share.

BLAST RADIUS: Invoke-PythonHidden is called directly by 37 setup/scripts/*.ps1 wrappers
(grepped 2026-08-10) including run-heartbeat-core.ps1 and run-heartbeat-aggressive.ps1 --
so an un-caught UnicodeEncodeError in ANY of their downstream Python could have silently
dropped a live trading tick. This guard proves the fix at the mechanism level (a real
subprocess through the real function), not just a source-text grep.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "setup" / "scripts"
SHARED = SCRIPTS / "_shared.ps1"


def test_invoke_python_hidden_sets_pythonioencoding_utf8_source():
    """Static check: the EXACT line must be present in Invoke-PythonHidden's body."""
    text = SHARED.read_text(encoding="utf-8")
    assert '$psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"' in text, (
        "Invoke-PythonHidden must force PYTHONIOENCODING=utf-8 on its child process -- "
        "without it, headless (CreateNoWindow) Python children fall back to the Windows "
        "ANSI codepage and crash on any non-cp1252 character in printed output.")


# A script that reproduces the EXACT production crash: print() a character outside
# cp1252 (U+2265, the same character that actually crashed kitchen_reviewer.py).
_UNICODE_PRINT_SCRIPT = """\
import sys
print("edge_capture \\u2265 771 threshold check")
sys.exit(0)
"""

_HARNESS_TEMPLATE = """\
$ErrorActionPreference = "Continue"
. "{shared}"
$result = Invoke-PythonHidden -ScriptPath "{script}" -TaskName "test-utf8-stdout" -TimeoutSec 30
$out = [ordered]@{{
    ExitCode = $result.ExitCode
    Stdout   = $result.Stdout
    Stderr   = $result.Stderr
}}
($out | ConvertTo-Json -Compress) | Out-File -FilePath "{result_file}" -Encoding utf8
"""


def test_unicode_stdout_no_longer_crashes_the_child(tmp_path):
    """The mechanism, not just the symptom: spawn a REAL child through the REAL
    Invoke-PythonHidden that prints the exact character class that crashed
    kitchen_reviewer.py, and prove it now exits 0 with no UnicodeEncodeError."""
    script = tmp_path / "print_unicode.py"
    script.write_text(_UNICODE_PRINT_SCRIPT, encoding="utf-8")
    result_file = tmp_path / "result.json"
    harness = tmp_path / "harness.ps1"
    harness.write_text(
        _HARNESS_TEMPLATE.format(
            shared=str(SHARED), script=str(script), result_file=str(result_file),
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(harness)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"harness failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert result_file.exists(), f"harness produced no result: stdout={proc.stdout!r} stderr={proc.stderr!r}"

    out = json.loads(result_file.read_text(encoding="utf-8-sig"))
    assert out["ExitCode"] == 0, (
        f"child crashed instead of printing the unicode character cleanly: {out}")
    assert "UnicodeEncodeError" not in (out.get("Stderr") or ""), (
        f"UnicodeEncodeError still present -- the fix did not take: {out}")
    assert "≥" in (out.get("Stdout") or ""), (
        f"expected the unicode character to survive round-trip in captured stdout: {out}")


def test_kalshi_local_workaround_still_present_regression_guard():
    """The kalshi scripts' local PYTHONIOENCODING workaround predates this shared fix
    and must not be removed as 'redundant' -- they run via a DIFFERENT hand-rolled
    ProcessStartInfo block, not Invoke-PythonHidden, so the shared fix does not cover
    them. Removing either would silently reopen this exact crash class for one lane."""
    for name in ("run-kalshi-tick.ps1", "run-kalshi-auto.ps1"):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "PYTHONIOENCODING" in text, f"{name} lost its local UTF-8 stdout fix"
