"""Guard for self_check.check_self_audit_organ_alive -- the Gamma_SelfAudit (~17:30 ET,
daily incl. weekends) -> gap-log.jsonl DAILY liveness detector.

Motivation: found live 2026-08-11 (conductor AFTERHORS priority-3 self-audit-gap pass).
self_audit.py's outer subprocess timeout to swarm_consult.py (300s) was smaller than
swarm_consult's own worst-case internal budget (PERSPECTIVE_TIMEOUT_S=240 +
SYNTHESIS_TIMEOUT_S=300 = 540s), so 2 consecutive full audits (2026-08-09, 2026-08-10)
were silently killed and swallowed by a bare `except Exception: return 0` -- Task
Scheduler still read LastTaskResult=0. COMPOUNDING: gap-log.jsonl (the dedup ledger,
self_audit.py's ONLY source of "already seen" keys) was itself tracked-but-rarely-
committed and had been silently reverting to its 2026-07-14 committed snapshot for a
month (see backtest/tests/test_ledger_gitignore_guard.py SELF_AUDIT_GAP_LOG) --
new-gaps-flagged.md (a separate, properly-committed narrative file) kept growing the
whole time, masking that the dedup ledger itself was frozen.

Mirrors test_self_check_scout_premarket_freshness.py's import convention and structure --
same DEGRADED-not-BROKEN classification (the gap-finder is a visibility organ, not a
trading-path input)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "self_check.py"

_spec = importlib.util.spec_from_file_location("self_check", MOD_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


# ---- before the slack window: never flags, regardless of weekday/weekend ----

def test_before_slack_window_never_flags(tmp_path):
    missing = tmp_path / "gap-log.jsonl"
    now = dt.datetime(2026, 8, 8, 17, 45)  # Saturday, before 18:15 ET slack expiry
    assert sc.check_self_audit_organ_alive(now, log_path=missing) == []


def test_weekday_before_slack_window_never_flags(tmp_path):
    missing = tmp_path / "gap-log.jsonl"
    now = dt.datetime(2026, 8, 10, 12, 0)  # Monday noon, well before the ~17:30 ET fire
    assert sc.check_self_audit_organ_alive(now, log_path=missing) == []


# ---- missing ledger past the slack window ----

def test_missing_ledger_flags_after_slack_window(tmp_path):
    missing = tmp_path / "gap-log.jsonl"
    now = dt.datetime(2026, 8, 10, 18, 20)
    problems = sc.check_self_audit_organ_alive(now, log_path=missing)
    assert len(problems) == 1
    assert "SELF-AUDIT DEGRADED" in problems[0]
    assert not sc._problem_is_broken(problems[0]), "visibility-only -- must be DEGRADED, never BROKEN"


# ---- stale ledger (newest entry is a prior day) -- the exact 08-09/08-10 incident shape ----

def test_stale_ledger_flags(tmp_path):
    log = tmp_path / "gap-log.jsonl"
    log.write_text(
        json.dumps({"ts_et": "2026-08-08T17:33:38", "key": "abc123", "gap": "some gap", "new": True}) + "\n",
        encoding="utf-8",
    )
    now = dt.datetime(2026, 8, 10, 18, 20)  # 2 days after the last real entry
    problems = sc.check_self_audit_organ_alive(now, log_path=log)
    assert len(problems) == 1
    assert "SELF-AUDIT STALE" in problems[0]
    assert "2026-08-08" in problems[0]
    assert not sc._problem_is_broken(problems[0])


# ---- fresh today -- no problem ----

def test_fresh_ledger_produces_no_problem(tmp_path):
    log = tmp_path / "gap-log.jsonl"
    log.write_text(
        json.dumps({"ts_et": "2026-08-10T17:31:00", "key": "def456", "gap": "some gap", "new": False}) + "\n",
        encoding="utf-8",
    )
    now = dt.datetime(2026, 8, 10, 18, 20)
    assert sc.check_self_audit_organ_alive(now, log_path=log) == []


# ---- multiple lines, newest wins (out-of-order-on-disk safety) ----

def test_multiple_lines_uses_newest_date(tmp_path):
    log = tmp_path / "gap-log.jsonl"
    lines = [
        {"ts_et": "2026-08-08T17:33:38", "key": "a", "gap": "g1", "new": True},
        {"ts_et": "2026-08-10T17:31:00", "key": "b", "gap": "g2", "new": True},
        {"ts_et": "2026-08-09T17:30:00", "key": "c", "gap": "g3", "new": True},
    ]
    log.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    now = dt.datetime(2026, 8, 10, 18, 20)
    assert sc.check_self_audit_organ_alive(now, log_path=log) == []


# ---- corrupt file -- fail-open, never crash ----

def test_corrupt_ledger_treated_as_unreadable(tmp_path):
    log = tmp_path / "gap-log.jsonl"
    log.write_text("{not valid json at all", encoding="utf-8")
    now = dt.datetime(2026, 8, 10, 18, 20)
    problems = sc.check_self_audit_organ_alive(now, log_path=log)
    assert len(problems) == 1
    assert "SELF-AUDIT" in problems[0]
    assert not sc._problem_is_broken(problems[0])


# ---- malformed individual lines are skipped, not fatal ----

def test_malformed_line_is_skipped_not_fatal(tmp_path):
    log = tmp_path / "gap-log.jsonl"
    good = json.dumps({"ts_et": "2026-08-10T17:31:00", "key": "b", "gap": "g", "new": False})
    log.write_text("not json\n" + good + "\n", encoding="utf-8")
    now = dt.datetime(2026, 8, 10, 18, 20)
    assert sc.check_self_audit_organ_alive(now, log_path=log) == []


# ---- wiring: run() must call the check and feed it into problems ----

def test_run_source_wires_self_audit_organ_alive_check():
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_self_audit_organ_alive(now)" in src
    assert "problems.extend(check_self_audit_organ_alive(now))" in src
