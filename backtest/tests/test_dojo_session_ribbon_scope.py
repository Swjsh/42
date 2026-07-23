"""Guard: setup/scripts/dojo/session.py's `_ribbon_scope_line` -- RIBBON-SESSION-SCOPE-
DIVERGENCE Lane-A wiring (automation/overnight/queue.md 2026-07-23, PART-2-RESOLVED
remainder: "wire compare_at into the dojo session step + morning-brief gap-day line").

Checks:
  1. A genuine RTH-vs-ETH disagreement at a real cached bar produces a whisper line +
     ledger-ready dict, using the SAME regression-anchor bars test_ribbon_scope_compare.py
     already pins (2026-06-05 09:30 ET, disagreement) -- proves the wiring reaches the real
     comparator, not a stub.
  2. An agreeing bar (2026-06-16 09:30 ET) returns None -- never spam the whisper with a
     line when the two scopes already agree.
  3. Fail-open: the function catches an exception from the comparator (simulated via a fake
     module) and returns None rather than raising -- the step loop must never break over
     this diagnostic.
  4. Fail-open: an ImportError (comparator module genuinely unavailable) also returns None.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_dojo_session_ribbon_scope.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "setup" / "scripts"
for _p in (SCRIPTS_DIR, ROOT / "backtest", ROOT / "automation" / "state" / "fleet"):
    _ap = str(_p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from dojo import session  # noqa: E402

ET = ZoneInfo("America/New_York")


def test_disagreement_bar_produces_line_and_data():
    bar_et = datetime(2026, 6, 5, 9, 30, tzinfo=ET)
    result = session._ribbon_scope_line("2026-06-05", bar_et)
    assert result is not None
    assert "ribbon scope divergence" in result["line"]
    assert result["data"]["rth_stack"] == "MIXED"
    assert result["data"]["eth_stack"] == "BEAR"
    assert result["data"]["agree"] is False


def test_agreement_bar_returns_none():
    bar_et = datetime(2026, 6, 16, 9, 30, tzinfo=ET)
    assert session._ribbon_scope_line("2026-06-16", bar_et) is None


def test_comparator_exception_fails_open(monkeypatch):
    class _BoomModule:
        @staticmethod
        def compare_at(day, bar_et):
            raise RuntimeError("synthetic comparator failure")

    fake_tools_pkg = type(sys)("tools")
    fake_tools_pkg.ribbon_scope_compare = _BoomModule()
    monkeypatch.setitem(sys.modules, "tools", fake_tools_pkg)
    monkeypatch.setitem(sys.modules, "tools.ribbon_scope_compare", _BoomModule())
    result = session._ribbon_scope_line("2026-06-05", datetime(2026, 6, 5, 9, 30, tzinfo=ET))
    assert result is None


def test_comparator_import_error_fails_open(monkeypatch):
    """Simulate the comparator module genuinely being unavailable (mirrors engine_step/
    whisper's own graceful-degrade-on-ImportError pattern) -- must not raise."""
    monkeypatch.setitem(sys.modules, "tools", None)
    monkeypatch.setitem(sys.modules, "tools.ribbon_scope_compare", None)
    result = session._ribbon_scope_line("2026-06-05", datetime(2026, 6, 5, 9, 30, tzinfo=ET))
    assert result is None
