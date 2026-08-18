"""Guard for self_check.check_run_py_venv_hidden_masked_exit -- the THIRD relay in the
VBS-WRAPPER-EXIT-CODE-BLIND-SPOT family (run_cmd_hidden.py shipped 2026-08-05,
run_ps1_hidden.py shipped 2026-08-06, this one 2026-08-18).

Motivation: run_py_venv_hidden.py (built 2026-08-13, "STOP THESE FUCKING CMD POPUS" --
J's console-leak complaint) launches scripts needing the backtest venv's site-packages via
SYSTEM pythonw + PYTHONPATH, instead of the venv's own pythonw (which allocates a
WindowsTerminal -Embedding host on `import pandas`). At least 12 Gamma_* tasks
(ChartAutoDraw, EodBrief, EodDojoManifest, GateExpiryCheck, JIntentExecutor,
LadderRungShadow, MorningBrief, RegimeShadow, RegimeStamp, RiskyDivergenceWeekly,
ShadowSignalAudit, WinnerAutopsy) were imperatively migrated onto it sometime after its
2026-08-13 birth (live-enumerated via Get-ScheduledTask 2026-08-18, not guessed) -- the
outer wscript hop is still fire-and-forget, so Task Scheduler's LastTaskResult can never
see their real outcome, but run_py_venv_hidden.py's own process runs the child
SYNCHRONOUSLY and has logged the true exit code to
automation/state/logs/run-py-venv-hidden-<date>.log on every fire since birth. Zero prior
consumers (verified live via grep, same C7 shape as its two siblings). This closes the gap
using evidence that already exists on disk -- no vbs edits, no live-trading-path touch.

Log format (single self-contained line per record, like run_ps1_hidden.py -- NOT
run_cmd_hidden.py's launching/exit line-order pairing):
    [2026-08-17 07:35:22] draw_key_levels.py exit=0
    [2026-08-17 07:36:06] daily_brief.py exit=0 args=['--mode', 'morning']
"""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "self_check.py"

_spec = importlib.util.spec_from_file_location("self_check", MOD_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


# ---- _parse_run_py_venv_hidden_log (pure parser) ----

def test_parse_extracts_name_and_exit_simple_line():
    text = "[2026-08-17 07:35:22] draw_key_levels.py exit=0\n"
    assert sc._parse_run_py_venv_hidden_log(text) == [{"name": "draw_key_levels.py", "exit": 0}]


def test_parse_handles_trailing_args_list():
    text = "[2026-08-17 07:36:06] daily_brief.py exit=0 args=['--mode', 'morning']\n"
    assert sc._parse_run_py_venv_hidden_log(text) == [{"name": "daily_brief.py", "exit": 0}]


def test_parse_extracts_nonzero_exit():
    text = "[2026-08-17 23:01:48] gate_expiry_check.py exit=1\n"
    assert sc._parse_run_py_venv_hidden_log(text) == [{"name": "gate_expiry_check.py", "exit": 1}]


def test_parse_multiple_lines_all_captured():
    text = (
        "[t] draw_key_levels.py exit=0\n"
        "[t] j_intent_executor.py exit=0 args=['--daemon']\n"
        "[t] winner_autopsy.py exit=1 args=['--out', 'all']\n"
    )
    records = sc._parse_run_py_venv_hidden_log(text)
    by_name = {r["name"]: r["exit"] for r in records}
    assert by_name == {
        "draw_key_levels.py": 0,
        "j_intent_executor.py": 0,
        "winner_autopsy.py": 1,
    }


def test_parse_ignores_fatal_log_lines_without_a_py_exit():
    text = "[2026-08-17 07:35:22] FATAL: target missing: C:\\foo\\bar.py\n"
    assert sc._parse_run_py_venv_hidden_log(text) == []


# ---- check_run_py_venv_hidden_masked_exit (the wired check) ----

def test_missing_log_never_flags(tmp_path):
    now = dt.datetime(2026, 8, 17, 12, 0)
    missing = tmp_path / "run-py-venv-hidden-2026-08-17.log"
    assert sc.check_run_py_venv_hidden_masked_exit(now, log_path=missing) == []


def test_all_clean_exits_never_flags(tmp_path):
    now = dt.datetime(2026, 8, 17, 12, 0)
    p = tmp_path / "log.log"
    p.write_text(
        "[t] draw_key_levels.py exit=0\n[t] regime_stamp.py exit=0\n",
        encoding="utf-8",
    )
    assert sc.check_run_py_venv_hidden_masked_exit(now, log_path=p) == []


def test_single_nonzero_exit_flags_degraded_with_script_name(tmp_path):
    now = dt.datetime(2026, 8, 17, 12, 0)
    p = tmp_path / "log.log"
    p.write_text("[t] gate_expiry_check.py exit=1\n", encoding="utf-8")
    problems = sc.check_run_py_venv_hidden_masked_exit(now, log_path=p)
    assert len(problems) == 1
    assert "RUN-PY-VENV-HIDDEN MASKED EXIT" in problems[0]
    assert "gate_expiry_check.py" in problems[0]
    assert "exit=[1]" in problems[0]
    assert not sc._problem_is_broken(problems[0]), "R&D/telemetry relay -- must be DEGRADED, never BROKEN"


def test_repeated_failures_of_same_script_collapse_to_one_line(tmp_path):
    now = dt.datetime(2026, 8, 17, 12, 0)
    p = tmp_path / "log.log"
    p.write_text(("[t] draw_key_levels.py exit=1\n" * 4), encoding="utf-8")
    problems = sc.check_run_py_venv_hidden_masked_exit(now, log_path=p)
    assert len(problems) == 1, "4 fires of the SAME failing script must collapse to ONE finding, not spam"
    assert "4x" in problems[0]


def test_two_distinct_failing_scripts_named_separately(tmp_path):
    now = dt.datetime(2026, 8, 17, 12, 0)
    p = tmp_path / "log.log"
    p.write_text(
        "[t] winner_autopsy.py exit=1 args=['--out', 'all']\n"
        "[t] shadow_signal_audit.py exit=2\n",
        encoding="utf-8",
    )
    problems = sc.check_run_py_venv_hidden_masked_exit(now, log_path=p)
    assert len(problems) == 1
    assert "winner_autopsy.py" in problems[0] and "shadow_signal_audit.py" in problems[0]


def test_wired_into_run_verdict():
    """The check must actually be reachable from run()'s aggregate problems list -- not
    just defined and orphaned (C7: being-defined != being-run)."""
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_run_py_venv_hidden_masked_exit" in src


def test_live_log_2026_08_17_surfaces_clean_verdict():
    """OP-33 verify-not-claim: run the check against the ACTUAL on-disk log from a real
    session, not just a synthetic fixture. 2026-08-17's real log has zero non-zero exits
    (all 15 real fires that day exit=0) -- proves the parser doesn't false-positive against
    the real 'args=[...]' trailing-clause shape live tasks actually emit."""
    real_log = REPO / "automation" / "state" / "logs" / "run-py-venv-hidden-2026-08-17.log"
    if not real_log.exists():
        import pytest
        pytest.skip("real 2026-08-17 log not present on this machine")
    now = dt.datetime(2026, 8, 17, 23, 59)
    problems = sc.check_run_py_venv_hidden_masked_exit(now, log_path=real_log)
    assert problems == []
