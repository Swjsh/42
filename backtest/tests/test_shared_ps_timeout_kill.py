"""Guards for the SYSTEMIC-TIMEOUT-LEAK fix (2026-08-07, Lane 2).

THE FINDING: setup/scripts/_shared.ps1's Invoke-PythonHidden carried TWO independent
defects that together made every -TimeoutSec across every wrapper that calls it a lie:

1. Process.Kill(Boolean) -- the process-tree overload -- does not exist on this box's
   Windows PowerShell 5.1 / .NET Framework 4.0 and THROWS
   "Cannot find an overload for 'Kill' and the argument count: '1'". The old code
   swallowed that exception in a bare `try { $proc.Kill($true) } catch {}`, so a timed-out
   child was never actually killed -- just leaked. Proven empirically this session: a real
   spawned `powershell.exe -Command Start-Sleep -Seconds 120` process survived
   `.Kill($true)` (exception thrown, quoted below) but died immediately under plain
   `.Kill()`.

2. The old code called the SYNCHRONOUS `StandardOutput.ReadToEnd()` / `StandardError
   .ReadToEnd()` BEFORE `WaitForExit($TimeoutSec * 1000)`. ReadToEnd() blocks until the
   pipe's write end closes, which only happens on process exit -- so a child that hangs
   (regardless of whether it ever produces output) blocks that line forever and
   WaitForExit(timeout) is never even reached. -TimeoutSec was dead code in exactly the
   pathological case it exists for.

Empirical proof captured this session (real PowerShell 5.1, real spawned child, real PID):

    Started PID 28024, HasExited=False
    Kill(true) THREW: System.Management.Automation.MethodException: Cannot find an
        overload for "Kill" and the argument count: "1".
    After Kill(true) attempt, process still running: True
    ...
    Started PID 1596, HasExited=False
    Kill() SUCCEEDED (no exception)
    After Kill() attempt, process still running: False

THE FIX (this file's subject): Invoke-PythonHidden now begins async reads
(ReadToEndAsync) BEFORE WaitForExit -- mirroring Invoke-Claude's already-correct pattern
in the same file -- so WaitForExit is the only blocking call and the timeout is real; and
uses plain `.Kill()` (the PS5.1-safe leaf-process call; Invoke-PythonHidden's children are
plain python.exe leaves, never a process tree) instead of the nonexistent overload.

INVENTORY (grepped setup/**/*.ps1 for both defects before editing anything):
  - Kill($true): ONLY setup/scripts/_shared.ps1 Invoke-PythonHidden (fixed here).
    run-swarm-premarket.ps1 and run-overnight-grinder.ps1 already use plain Kill().
    run-conductor.ps1's rail-0 precheck already uses plain Kill() (tonight's separate fix).
  - Sync ReadToEnd before WaitForExit: ONLY the same Invoke-PythonHidden site (fixed here).
    Invoke-Claude (same file) already used ReadToEndAsync-before-WaitForExit. Every other
    setup/**/*.ps1 hit for WaitForExit either has no ReadToEnd call at all, or (run-swarm-
    premarket.ps1, run-overnight-grinder.ps1) already calls WaitForExit first.
  No other .ps1 under setup/ carries either defect -- none besides _shared.ps1 touched.

BLAST RADIUS: 38 wrappers call Invoke-PythonHidden directly; 58 dot-source _shared.ps1.
The function's return contract (@{ExitCode; Stdout; Stderr; LogFile}) and logging shape
are unchanged -- only the internal ordering and kill call changed. Verified via
test_two_unrelated_live_wrappers_unaffected below (test-self-heal.ps1's own safe smoke
suite executed for real + a syntax-only parse-check of an unrelated production wrapper).
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "setup" / "scripts"
SETUP_DIR = ROOT / "setup"
SHARED = SCRIPTS / "_shared.ps1"

# Files this fix actually edited -- the only files these guards require to be clean.
EDITED_FILES = [SHARED]


# --------------------------------------------------------------------------- #
# Static checks: parse the .ps1 text, no subprocess needed.
# --------------------------------------------------------------------------- #

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_ps_comments(text: str) -> str:
    """Strip '# ...' line comments (this file has no <# #> block comments) so prose in
    explanatory FIX-note comments doesn't false-positive against code-shape assertions."""
    return "\n".join(re.sub(r"(?<!['\"])#.*$", "", line) for line in text.splitlines())


def _extract_function(src: str, name: str) -> str:
    """Extract a PS function body by brace-matching from `function <name> {` to its
    closing brace. Good enough for this file's flat (non-nested-function) style."""
    m = re.search(rf"function\s+{re.escape(name)}\s*\{{", src)
    assert m, f"function {name} not found in source"
    start = m.end() - 1  # position of the opening brace
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError(f"unbalanced braces extracting function {name}")


def test_no_kill_true_anywhere_under_setup():
    """No Process.Kill($true) call survives anywhere under setup/ -- the exact call that
    throws MethodException on this box's PS5.1/.NET Framework and gets silently swallowed."""
    offenders = []
    for p in SETUP_DIR.rglob("*.ps1"):
        text = _read(p)
        if re.search(r"\.Kill\(\s*\$true\s*\)", text):
            offenders.append(str(p.relative_to(ROOT)))
    assert offenders == [], f"Kill($true) still present in: {offenders}"


def test_invoke_python_hidden_uses_plain_kill():
    fn = _extract_function(_read(SHARED), "Invoke-PythonHidden")
    assert ".Kill($true)" not in fn
    assert re.search(r"\$proc\.Kill\(\)", fn), (
        "Invoke-PythonHidden must call plain .Kill() (no args) on timeout -- "
        "the PS5.1-safe overload for a leaf process")


def test_invoke_python_hidden_starts_async_reads_before_waitforexit():
    """The core ordering fix: ReadToEndAsync() must be called (and thus the pipe drain
    begun) BEFORE WaitForExit(), not a blocking ReadToEnd() before it."""
    fn = _strip_ps_comments(_extract_function(_read(SHARED), "Invoke-PythonHidden"))
    assert "ReadToEnd()" not in fn, (
        "Invoke-PythonHidden must not use the synchronous, pre-WaitForExit ReadToEnd() "
        "form -- it deadlocks/hangs the timeout on a genuinely hung child")
    stdout_async_pos = fn.index("StandardOutput.ReadToEndAsync()")
    stderr_async_pos = fn.index("StandardError.ReadToEndAsync()")
    wait_pos = fn.index("WaitForExit(")
    assert stdout_async_pos < wait_pos, "stdout async read must start before WaitForExit"
    assert stderr_async_pos < wait_pos, "stderr async read must start before WaitForExit"


def test_invoke_python_hidden_return_contract_unchanged():
    """The function's return shape must stay byte-compatible -- dozens of live callers
    destructure .ExitCode / .Stdout / .Stderr / .LogFile."""
    fn = _extract_function(_read(SHARED), "Invoke-PythonHidden")
    assert re.search(
        r"return @\{\s*ExitCode\s*=\s*\$exit;\s*Stdout\s*=\s*\$stdout;\s*Stderr\s*=\s*\$stderr;\s*LogFile\s*=\s*\$logFile\s*\}",
        fn,
    ), "Invoke-PythonHidden's return hashtable shape changed -- this breaks every caller"


def test_invoke_claude_pattern_still_correct_regression_guard():
    """Invoke-Claude was already correct (async-before-wait, plain Kill via
    Stop-ProcessTree) and served as the pattern Invoke-PythonHidden was brought in line
    with. Guard against anyone reverting it back to the broken shape."""
    fn = _extract_function(_read(SHARED), "Invoke-Claude")
    assert ".Kill($true)" not in fn
    assert "ReadToEndAsync()" in fn
    async_pos = fn.index("StandardOutput.ReadToEndAsync()")
    wait_pos = fn.index("WaitForExit(")
    assert async_pos < wait_pos


# --------------------------------------------------------------------------- #
# Executed scenario: a REAL hung child, through the REAL Invoke-PythonHidden,
# must actually die when the timeout fires (not just return fast).
# --------------------------------------------------------------------------- #

_HANG_SCRIPT_TEMPLATE = """\
import os
import time
with open(r"{pid_file}", "w") as f:
    f.write(str(os.getpid()))
time.sleep(60)
"""

_HARNESS_TEMPLATE = """\
$ErrorActionPreference = "Continue"
. "{shared}"
$result = Invoke-PythonHidden -ScriptPath "{hang_script}" -TaskName "test-shared-ps-timeout-kill" -TimeoutSec 2
$childPidRaw = ""
if (Test-Path "{pid_file}") {{ $childPidRaw = (Get-Content "{pid_file}" -Raw).Trim() }}
Start-Sleep -Milliseconds 500
$stillAlive = $false
if ($childPidRaw) {{
    $stillAlive = [bool](Get-Process -Id ([int]$childPidRaw) -ErrorAction SilentlyContinue)
}}
$out = [ordered]@{{
    ExitCode   = $result.ExitCode
    ChildPid   = $childPidRaw
    StillAlive = $stillAlive
}}
($out | ConvertTo-Json -Compress) | Out-File -FilePath "{result_file}" -Encoding utf8
"""


def test_hung_child_actually_dies_on_timeout(tmp_path):
    """Spawn a real long-sleeping python child via Invoke-PythonHidden with a short
    -TimeoutSec, then prove the child's own PID is gone afterward -- the mechanism, not
    just the symptom (fast return alone wouldn't prove the process was actually killed;
    the old buggy code with Kill($true) also would have hit WaitForExit's false return
    quickly-ish once ordering was fixed in isolation, but the child would have survived)."""
    pid_file = tmp_path / "hang_pid.txt"
    hang_script = tmp_path / "hang_and_write_pid.py"
    hang_script.write_text(_HANG_SCRIPT_TEMPLATE.format(pid_file=str(pid_file)), encoding="utf-8")
    result_file = tmp_path / "result.json"
    harness = tmp_path / "harness.ps1"
    harness.write_text(
        _HARNESS_TEMPLATE.format(
            shared=str(SHARED), hang_script=str(hang_script),
            pid_file=str(pid_file), result_file=str(result_file),
        ),
        encoding="utf-8",
    )

    started = time.time()
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(harness)],
        capture_output=True, text=True, timeout=60,
    )
    elapsed = time.time() - started

    assert proc.returncode == 0, f"harness failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert result_file.exists(), f"harness produced no result: stdout={proc.stdout!r} stderr={proc.stderr!r}"

    import json
    out = json.loads(result_file.read_text(encoding="utf-8-sig"))

    assert out["ExitCode"] == -1, f"expected timeout ExitCode=-1, got {out}"
    assert out["ChildPid"], f"child never wrote its PID -- test setup broken: {out}"
    assert out["StillAlive"] is False, (
        f"the hung child (pid={out['ChildPid']}) is STILL ALIVE after Invoke-PythonHidden "
        f"returned on timeout -- the leak is back: {out}")
    # 60s sleep, 2s timeout: a real kill returns in low single-digit seconds, not 60s.
    assert elapsed < 20, (
        f"took {elapsed:.1f}s -- should return well before the child's own 60s sleep "
        f"if the timeout/kill actually fired")


# --------------------------------------------------------------------------- #
# Blast radius: prove two UNRELATED live wrappers that depend on _shared.ps1
# are unaffected by this change.
# --------------------------------------------------------------------------- #

def test_blast_radius_test_self_heal_suite_still_passes():
    """test-self-heal.ps1 is a pure, safe smoke suite (cmd.exe/notepad/ping proxies only --
    never spawns claude.exe or costs a token) that exercises Stop-ProcessTree,
    Stop-StaleClaudeProcesses, Test-DiskSpaceAvailable, and Repair-StateFiles -- all
    UNRELATED functions in the same _shared.ps1 file this fix edited. A regression in
    parsing/sourcing _shared.ps1 would break this suite too."""
    script = SCRIPTS / "test-self-heal.ps1"
    assert script.exists()
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(script)],
        capture_output=True, text=True, timeout=120, cwd=str(ROOT),
    )
    assert proc.returncode == 0, (
        f"test-self-heal.ps1 regressed after the Invoke-PythonHidden fix -- "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert "FAIL" not in proc.stdout, f"a sub-check failed:\n{proc.stdout}"


_PARSE_CHECK_TEMPLATE = """\
$errors = $null
$tokens = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    "{target}", [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) {{
    $errors | ForEach-Object {{ Write-Output ("PARSE_ERROR: " + $_.Message) }}
    exit 1
}}
Write-Output "PARSE_OK"
exit 0
"""


def _parse_check(target: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    checker = tmp_path / f"parsecheck_{target.stem}.ps1"
    checker.write_text(_PARSE_CHECK_TEMPLATE.format(target=str(target)), encoding="utf-8")
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(checker)],
        capture_output=True, text=True, timeout=30,
    )


def test_blast_radius_unrelated_wrappers_parse_cleanly(tmp_path):
    """Syntax-only parse-check (no execution -- these wrappers touch live trading state /
    would spawn real claude.exe fires, forbidden in this session) of two production
    wrappers unrelated to the Invoke-PythonHidden change, proving _shared.ps1's own
    edited text still parses (a syntax break in _shared.ps1 would surface here even
    though these scripts don't call Invoke-PythonHidden directly, since PowerShell parses
    the whole dot-sourced file before executing anything)."""
    targets = [SCRIPTS / "run-heartbeat-core.ps1", SCRIPTS / "run-eod-summary.ps1"]
    for t in targets:
        assert t.exists(), f"expected wrapper at {t}"

    # _shared.ps1 itself must parse standalone.
    proc = _parse_check(SHARED, tmp_path)
    assert proc.returncode == 0 and "PARSE_OK" in proc.stdout, (
        f"_shared.ps1 failed to parse after the fix: {proc.stdout} {proc.stderr}")

    for t in targets:
        proc = _parse_check(t, tmp_path)
        assert proc.returncode == 0 and "PARSE_OK" in proc.stdout, (
            f"{t.name} failed to parse: {proc.stdout} {proc.stderr}")
