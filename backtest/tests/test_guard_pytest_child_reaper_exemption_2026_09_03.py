"""Guard: guard_runner_full.py / guard_runner_slow.py's pytest CHILD process is protected
by a DECLARED reaper exemption, not by the accident this queue item found.

WHY THIS EXISTS (queue.md REAPER-EXEMPTION-COMMENT-DOES-NOT-MATCH-MECHANISM, filed
2026-09-02): _shared.ps1's $EXEMPT_DAEMONS comment used to claim that matching on
'guard_runner_full.py' "covers the parent AND the pytest child, since Stop-ProcessTree
walks the subtree". That was wrong on the mechanism -- Stop-StaleClaudeProcesses's
$isOurs / $isExempt loop evaluates each Win32_Process candidate independently by its OWN
CommandLine; Stop-ProcessTree is only ever called against a candidate that is BOTH
$isOurs AND NOT $isExempt, so it is never invoked against an exempt process at all, and
no subtree walk ever runs for one. The child (`<python> -m pytest tests/ ...`) is a
SEPARATE Win32_Process entry whose own CommandLine names neither the repo path nor
either runner script.

VERIFIED LIVE 2026-09-03 via `Get-ScheduledTask Gamma_GuardsFull` / `Gamma_GuardsNightly`:
both Actions launch through SYSTEM Python313 pythonw.exe
(C:/Users/jackw/AppData/Local/Programs/Python/Python313/pythonw.exe), which sits
OUTSIDE $WorkDir -- so `sys.executable.replace("pythonw","python")` (both runners' own
subprocess.run cmd construction) resolves to a path outside the repo, and the child's
argv (`-m pytest tests/ -q -m "not slow" -p no:cacheprovider`, or `... -m slow -q` for
the slow runner) never references $WorkDir either. That is why the child survived every
5-minute cutoff to date (a 46-minute run observed 2026-09-02): it fails `$isOurs` and is
never even offered to $EXEMPT_DAEMONS, not because the exemption list protects it.

THE FIX pairs two changes that must move together: $isOurs gained a
'-m pytest tests/' disjunct (so the child becomes a recognized candidate at all) and
$EXEMPT_DAEMONS gained the same literal as a marker (so, once recognized, it is
immediately skipped) -- widening one without the other would either do nothing
(exemption alone, unreachable) or newly expose the child to reaping (isOurs alone).

Pure file parsing (mirrors test_crypto_twin_reaper_exemption.py's convention) -- no
live Windows calls, portable to CI. PowerShell's `-like "*text*"` with no `-like`
metacharacters in `text` is a literal substring test (backslash/dot/space are not
`-like` wildcards), so plain Python `in` reproduces it exactly for these markers.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHARED_PS1 = REPO / "setup" / "scripts" / "_shared.ps1"


def _shared_text() -> str:
    return SHARED_PS1.read_text(encoding="utf-8")


def _extract_exempt_daemons(text: str) -> list[str]:
    """Pull every single-quoted string literal inside $EXEMPT_DAEMONS = @(...), line by
    line (a blob regex breaks on the array's own inline comments, some of which contain
    a stray ')'). Same approach as test_crypto_twin_reaper_exemption.py."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip().startswith("$EXEMPT_DAEMONS")), None)
    assert start is not None, "could not find $EXEMPT_DAEMONS = @(...) in _shared.ps1"
    daemons: list[str] = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped == ")":
            break
        if stripped.startswith("#"):
            continue
        daemons.extend(re.findall(r"'([^']+)'", line))
    return daemons


def _extract_is_ours_line(text: str) -> str:
    fn = re.search(r"function Stop-StaleClaudeProcesses\b.*?(?=\nfunction |\Z)", text, re.DOTALL)
    assert fn, "could not find 'function Stop-StaleClaudeProcesses' in _shared.ps1"
    line = next((l for l in fn.group(0).splitlines() if l.strip().startswith("$isOurs =")), None)
    assert line is not None, "could not find the $isOurs = ... assignment line"
    return line


# Real child CommandLines, reconstructed from guard_runner_full.py / guard_runner_slow.py's
# own `cmd = [sys.executable.replace("pythonw", "python"), "-m", "pytest", ...]` under the
# LIVE launch path (system Python313, verified via Get-ScheduledTask 2026-09-03).
FULL_CHILD_CMDLINE = (
    r'"C:\Users\jackw\AppData\Local\Programs\Python\Python313\python.exe" '
    r'-m pytest tests/ -q -m "not slow" -p no:cacheprovider'
)
SLOW_CHILD_CMDLINE = (
    r'"C:\Users\jackw\AppData\Local\Programs\Python\Python313\python.exe" '
    r'-m pytest tests/ -m slow -q'
)
UNRELATED_CMDLINE = r'"C:\Python311\python.exe" some_other_projects_script.py --flag'


class TestPytestChildIsRecognizedAsOurs:
    def test_is_ours_line_matches_the_pytest_child_pattern(self) -> None:
        line = _extract_is_ours_line(_shared_text())
        assert "-m pytest tests/" in line, (
            "$isOurs no longer disjuncts on '-m pytest tests/' -- the pytest child of "
            "guard_runner_full.py/guard_runner_slow.py (which names neither $WorkDir nor "
            "an MCP server under the live system-Python launch path) would again be "
            "invisible to the reaper's isOurs/isExempt gate entirely."
        )

    def test_full_and_slow_child_cmdlines_would_pass_is_ours(self) -> None:
        # $isOurs's disjuncts are all literal-substring '-like "*text*"' tests; reproduce
        # with plain `in` since none of these markers contain -like wildcard chars.
        assert "-m pytest tests/" in FULL_CHILD_CMDLINE
        assert "-m pytest tests/" in SLOW_CHILD_CMDLINE

    def test_unrelated_pytest_free_process_still_fails(self) -> None:
        assert "-m pytest tests/" not in UNRELATED_CMDLINE


class TestPytestChildIsDeclaredExempt:
    def test_exempt_daemons_carries_the_pytest_child_marker(self) -> None:
        daemons = _extract_exempt_daemons(_shared_text())
        assert "-m pytest tests/" in daemons, (
            "$EXEMPT_DAEMONS no longer carries '-m pytest tests/' -- once the child "
            "passes the widened $isOurs check it would have nothing declared to protect "
            "it and would be reaped at the 5-minute mark."
        )

    def test_full_and_slow_child_cmdlines_match_the_declared_marker(self) -> None:
        daemons = _extract_exempt_daemons(_shared_text())
        marker = "-m pytest tests/"
        assert marker in daemons
        assert marker in FULL_CHILD_CMDLINE
        assert marker in SLOW_CHILD_CMDLINE

    def test_runner_script_markers_still_present(self) -> None:
        """Regression guard: the parent-process markers this fix did not touch."""
        daemons = _extract_exempt_daemons(_shared_text())
        assert "guard_runner_full.py" in daemons
        assert "guard_runner_slow.py" in daemons


class TestCommentNoLongerClaimsSubtreeWalkProtectsTheChild:
    def test_wrong_mechanism_claim_is_gone(self) -> None:
        text = _shared_text()
        assert "since Stop-ProcessTree walks the subtree" not in text, (
            "the corrected comment reintroduced the disproven claim that matching the "
            "runner name protects the pytest child via a Stop-ProcessTree subtree walk -- "
            "Stop-ProcessTree is never called against an exempt candidate at all."
        )

    def test_correction_names_the_real_mechanism(self) -> None:
        text = _shared_text()
        assert "REAPER-EXEMPTION-COMMENT-DOES-NOT-MATCH-MECHANISM" in text
        assert "system Python313" in text or "Python313" in text
