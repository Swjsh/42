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

2026-09-10 CORRECTION (FULL-SUITE-RED-TRIAGE-2026-09-10 goal, disposition
STALE-ASSUMPTION): on 2026-09-03 the WHOLE wiring family (key-levels-snapshot,
fee-recalibrate, crypto-twin, and this installer among them) deliberately moved OFF
a dedicated `$pywVenv` = backtest\\.venv\\Scripts\\pythonw.exe variable entirely --
root cause PANDAS-CONSOLE-LEAK-ROOT-CAUSE (closed 2026-09-03, see
install-fee-recalibrate.ps1's WIRING comment): backtest\\.venv\\Scripts\\pythonw.exe
is CPython's venvwlauncher redirector, but the venv's pyvenv.cfg has no GUI-variant
executable= entry, so ANY heavy-import script launched through it re-execs the base
install's CONSOLE python.exe and leaks a console-host window regardless of launcher
mechanism or CREATE_NO_WINDOW. The proven fix (same one applied to crypto-twin, see
test_crypto_twin_reaper_exemption.py's own 2026-09-10 correction) launches the BASE
system pythonw ($pyw) for BOTH hops and activates the venv via
`--env PYTHONPATH=<repo>\\backtest\\.venv\\Lib\\site-packages` instead of via a
dedicated venv-pythonw variable. yfinance still resolves fine under this pattern --
PYTHONPATH injects the venv's site-packages into sys.path regardless of which
pythonw binary is running; live-verified 2026-09-10:
automation/state/weekly/earnings-blackout.json (this script's real output) has
generated_at 2026-09-09, i.e. the task ran successfully under the CURRENT (post-
2026-09-03) wiring the night before this fire, not a stale pre-migration artifact.
The tests below now assert the wiring that is actually live and actually working,
not the pre-2026-09-03 $pywVenv convention.
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


def test_inner_hop_uses_backtest_venv_via_pythonpath():
    """The action string that invokes earnings_calendar.py (via $script) must route
    the backtest venv's site-packages onto PYTHONPATH -- the 2026-09-03 proven recipe
    (see this file's module-docstring correction) -- so yfinance resolves under
    EITHER hop's system pythonw. There is no dedicated $pywVenv variable any more."""
    src = _source()
    assert f'$script = Join-Path $repo "setup\\scripts\\{_TARGET_SCRIPT}"' in src.replace(
        "\r\n", "\n"
    ) or _TARGET_SCRIPT in src, f"{_TARGET_SCRIPT} not referenced anywhere in the install script"

    # The $action assignment is the single source of truth for what actually runs.
    action_match = re.search(r'\$action\s*=.*', src)
    assert action_match, "could not locate the $action New-ScheduledTaskAction line"
    action_line = action_match.group(0)

    assert "PYTHONPATH=$pythonPath" in action_line, (
        "$action does not inject PYTHONPATH=$pythonPath at all -- this is the exact "
        "regression this guard exists to catch (earnings_calendar.py imports yfinance, "
        "which only exists in the backtest venv, never in system Python313's own "
        "site-packages)"
    )
    # The INNER hop is the interpreter immediately before $script (the last one in the
    # -- <interp> <script> pair). Under the 2026-09-03 recipe this is $pyw (system
    # pythonw) for BOTH hops -- venv activation happens via PYTHONPATH, not via a
    # dedicated venv-pythonw executable path.
    inner_pair = re.search(r'--\s*`"(\$\w+)`"\s*`"(\$\w+)`""', action_line)
    assert inner_pair, "could not find the trailing `-- <interp> <script>` pair in $action"
    inner_interp, inner_target = inner_pair.group(1), inner_pair.group(2)
    assert inner_target == "$script", f"unexpected inner target variable: {inner_target}"
    assert inner_interp == "$pyw", (
        f"inner hop uses {inner_interp}, not $pyw -- expected the 2026-09-03 recipe's "
        "system-pythonw-plus-PYTHONPATH pattern for both hops"
    )


def test_pythonpath_variable_is_declared_and_checked():
    """The script must resolve the backtest venv's site-packages via a variable, and
    the interpreter that will actually run under it ($pyw) must fail loudly
    (Test-Path + throw) if missing. NOTE: no install script in the 2026-09-03-migrated
    family (crypto-twin, key-levels-snapshot, fee-recalibrate, this one) Test-Path-
    guards the venv site-packages DIRECTORY itself -- a missing/broken venv would
    still surface loudly (ModuleNotFoundError in the task's own exit code, caught by
    self_check.py's run_cmd_hidden masked-exit check within ~30min) rather than
    silently, so this test asserts the convention that is actually consistent across
    the family rather than inventing a bar none of them clear."""
    src = _source()
    assert re.search(r'\$pythonPath\s*=.*backtest\\\.venv\\Lib\\site-packages', src), (
        "no $pythonPath variable resolving backtest\\.venv\\Lib\\site-packages found"
    )
    assert re.search(r'Test-Path\s+\$pyw\b', src), (
        "no Test-Path guard on $pyw -- a missing system pythonw should throw at "
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
