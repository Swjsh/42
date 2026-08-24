"""Regression guard: install-earnings-calendar.ps1's INNER hop must use the backtest
venv pythonw, never system pythonw, for the earnings_calendar.py call.

THE BUG THIS GUARDS (found live, 2026-08-24 conductor fire). The original install
script (2026-08-21) copied install-macro-calendar.ps1's wiring VERBATIM -- correct for
macro_calendar.py (stdlib-only) but wrong for earnings_calendar.py, which does
`import yfinance` (only installed in backtest\\.venv, never in system Python313).
Every single scheduled 07:50 ET fire crashed "FATAL earnings_calendar.py: No module
named 'yfinance'" from registration (2026-08-21) through discovery (2026-08-24) --
masked from Task Scheduler by the wscript fire-and-forget hop (LastTaskResult stayed 0
the whole time), but the real exit=1 sat unread in
automation/state/logs/run-cmd-hidden-<date>.log. self_check.py correctly flagged
EARNINGS-CALENDAR STALE (RED) once the file crossed its 48h fail-closed threshold, but
nothing before this fire distinguished "genuinely never re-ran" from "ran and crashed
every time" -- this test pins the actual wiring so the fix (backtest-venv pythonw for
the inner hop) can never silently regress back to the broken system-pythonw shape the
way install-crypto-twin.ps1's WIRING-DRIFT precedent (2026-08-07) already proved can
happen on a routine future cadence/setting edit.

Static source-parse only (no live Task Scheduler query) -- same precedent as
test_install_script_relay_wiring_drift.py.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_INSTALL_SCRIPT = _REPO / "setup" / "scripts" / "install-earnings-calendar.ps1"
_TARGET_SCRIPT = "earnings_calendar.py"


def _source() -> str:
    assert _INSTALL_SCRIPT.exists(), f"missing: {_INSTALL_SCRIPT}"
    return _INSTALL_SCRIPT.read_text(encoding="utf-8")


def test_install_script_exists():
    assert _INSTALL_SCRIPT.exists()


def test_inner_hop_uses_backtest_venv_pythonw():
    """The action string that invokes earnings_calendar.py (via $script) must route
    through the $pywVenv variable, not the bare system-Python313 $pyw variable, for
    the INNER (last) interpreter hop."""
    src = _source()
    assert f'$script = Join-Path $repo "setup\\scripts\\{_TARGET_SCRIPT}"' in src.replace(
        "\r\n", "\n"
    ) or _TARGET_SCRIPT in src, f"{_TARGET_SCRIPT} not referenced anywhere in the install script"

    # The $action assignment is the single source of truth for what actually runs.
    action_match = re.search(r'\$action\s*=.*', src)
    assert action_match, "could not locate the $action New-ScheduledTaskAction line"
    action_line = action_match.group(0)

    assert "$pywVenv" in action_line, (
        "$action does not reference $pywVenv at all -- this is the exact regression this "
        "guard exists to catch (earnings_calendar.py imports yfinance, which only exists "
        "in the backtest venv, never in system Python313)"
    )
    # The INNER hop is the interpreter immediately before $script (the last one in the
    # -- <interp> <script> pair). Confirm $pywVenv, not $pyw, sits directly before $script.
    inner_pair = re.search(r'--\s*`"(\$\w+)`"\s*`"(\$\w+)`""', action_line)
    assert inner_pair, "could not find the trailing `-- <interp> <script>` pair in $action"
    inner_interp, inner_target = inner_pair.group(1), inner_pair.group(2)
    assert inner_target == "$script", f"unexpected inner target variable: {inner_target}"
    assert inner_interp == "$pywVenv", (
        f"inner hop uses {inner_interp}, not $pywVenv -- earnings_calendar.py needs the "
        "backtest venv's yfinance package, system Python313 does not have it"
    )


def test_venv_pythonw_variable_is_declared_and_checked():
    """The script must resolve backtest-venv pythonw via a variable AND fail loudly
    (Test-Path + throw) if it's missing, not silently fall through to system pythonw."""
    src = _source()
    assert re.search(r'\$pywVenv\s*=.*backtest\\\.venv\\Scripts\\pythonw\.exe', src), (
        "no $pywVenv variable resolving backtest\\.venv\\Scripts\\pythonw.exe found"
    )
    assert re.search(r'Test-Path\s+\$pywVenv', src), (
        "no Test-Path guard on $pywVenv -- a missing venv pythonw should throw at "
        "install time, not silently produce a broken task"
    )


def test_synthetic_regression_is_caught_by_the_pattern():
    """Vacuity check: prove the assertion pattern above is not a rubber stamp by
    running the SAME regex extraction against the KNOWN-BROKEN 2026-08-21 original
    wiring (system $pyw for both hops) and confirming it correctly identifies the
    inner interpreter as $pyw, not $pywVenv."""
    broken_action_line = (
        '$action = New-ScheduledTaskAction -Execute "wscript.exe" '
        '-Argument "//nologo `"$vbs`" `"$pyw`" `"$runCmdHidden`" --cwd `"$repo`" '
        '-- `"$pyw`" `"$script`""'
    )
    inner_pair = re.search(r'--\s*`"(\$\w+)`"\s*`"(\$\w+)`""', broken_action_line)
    assert inner_pair, "regex should still find a pair in the broken fixture"
    inner_interp, inner_target = inner_pair.group(1), inner_pair.group(2)
    assert inner_target == "$script"
    assert inner_interp == "$pyw", "sanity: the broken fixture really does use $pyw for the inner hop"
    assert inner_interp != "$pywVenv", (
        "the vacuity check itself is broken -- the known-broken fixture should NOT "
        "pass the $pywVenv assertion"
    )
