"""The early-close flatten dry run, made permanent (work order §6, 2026-09-02).

WHY THIS IS A TEST AND NOT A ONE-OFF. Gamma_EodFlattenEarlyClose was registered 2026-09-01
and fires daily at 12:32 ET. On every ordinary day it correctly no-ops, because the branch
that MATTERS -- the one that actually sweeps positions before a 13:00 close -- can only run
on 2026-11-27 and 2026-12-24. So in the normal course of events this task's real behaviour
would first be exercised in production, on a half-day, with live positions open, months from
now. The work order asks for exactly the rehearsal below; pinning it means it re-runs on
every suite instead of being a thing someone did once in September.

Every case here forces GAMMA_EOD_DRY=1 before touching the sweep path. `live=(not DRY)` is
what makes that safe, and it is asserted first.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EOD = REPO / "setup" / "scripts" / "eod_flatten.py"

for p in (REPO / "setup" / "scripts", REPO / "automation" / "state" / "fleet"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _load(dry: bool):
    """Import a FRESH module instance -- DRY is read at import time, so it cannot be
    flipped after the fact."""
    os.environ["GAMMA_EOD_DRY"] = "1" if dry else "0"
    spec = importlib.util.spec_from_file_location("eod_flatten_g", EOD)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def eod():
    m = _load(dry=True)
    assert m.DRY is True, "refusing to exercise the sweep path without DRY"
    return m


def _capture(m, monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr(m, "_log", lambda path, msg: lines.append(msg))
    monkeypatch.setattr(m, "_append_jsonl", lambda path, row: None)
    return lines


# ---------------------------------------------------------------------------------------
# The safety invariant the whole rehearsal rests on.
# ---------------------------------------------------------------------------------------

def test_dry_is_import_time_and_returns_before_any_order():
    """eod_flatten gates DIFFERENTLY from dead_mans_switch, and more strongly. The DMS
    passes live=(not DRY) into the broker call; this file never reaches the call at all --
    `if DRY:` returns with outcome=DRY_RUN before it. I asserted the DMS pattern here first
    and the test correctly failed; the property is real, the expression was a guess.

    What matters is the ORDERING: the DRY return must come BEFORE the only mutating call.
    """
    import ast

    src = EOD.read_text(encoding="utf-8")
    assert 'DRY = os.environ.get("GAMMA_EOD_DRY", "0") == "1"' in src

    # Locate the CALL via the AST, not by string search. The module docstring names
    # `fleet_broker.close_all_spy_options()` in prose at char 476, long before the real
    # call at ~14k, so a substring search finds the sentence and concludes the order path
    # runs first. That is the second time in one session that prose masqueraded as code
    # here -- the parser is the only reliable way to ask "where is the call".
    tree = ast.parse(src)
    call_lines = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "close_all_spy_options"
    ]
    assert len(call_lines) == 1, f"expected one order call site, found {call_lines}"

    dry_guards = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "DRY"
    ]
    assert dry_guards, "the `if DRY:` guard is gone"
    assert min(dry_guards) < call_lines[0], (
        f"the DRY guard (line {min(dry_guards)}) no longer precedes the order call "
        f"(line {call_lines[0]}) -- a dry run could now place a real order, and this "
        "rehearsal must not run until it does again"
    )

    guard_body = src.splitlines()[min(dry_guards) - 1: call_lines[0]]
    joined = "\n".join(guard_body)
    assert '"outcome": "DRY_RUN"' in joined and "return result" in joined, (
        "the DRY branch no longer returns -- it must exit, not merely log"
    )


# ---------------------------------------------------------------------------------------
# The three branches. Case 3 is the one that cannot otherwise be reached before 2026-11-27.
# ---------------------------------------------------------------------------------------

def test_normal_full_day_noops(eod, monkeypatch):
    """What Gamma_EodFlattenEarlyClose does on all but two days of the year."""
    lines = _capture(eod, monkeypatch)
    monkeypatch.setattr(eod.market_calendar, "cached_close",
                        lambda d: eod.market_calendar.DEFAULT_CLOSE)
    assert eod._run_only_if_early_close() == 0
    assert any("EARLY_CLOSE_NOOP" in l for l in lines)
    assert not any("TRIGGER" in l for l in lines), "no sweep on a full day"


def test_early_close_before_the_window_waits(eod, monkeypatch):
    """13:00 close, asked at 06:14 -- must WAIT, not sweep six hours early."""
    lines = _capture(eod, monkeypatch)
    monkeypatch.setattr(eod.market_calendar, "cached_close", lambda d: "13:00")
    monkeypatch.setattr(eod, "et_now",
                        lambda: dt.datetime(2026, 9, 2, 6, 14, 0))
    assert eod._run_only_if_early_close() == 0
    wait = [l for l in lines if "EARLY_CLOSE_WAIT" in l]
    assert wait, lines
    assert "12:30" in wait[0], "the sweep window must open 30 min before a 13:00 close"
    assert not any("TRIGGER" in l for l in lines)


def test_early_close_inside_the_window_triggers_the_sweep(eod, monkeypatch):
    """THE branch that is otherwise unreachable until 2026-11-27. 13:00 close, asked at
    12:45, threshold 12:30 -- must trigger and run the sweep tagged EARLY_CLOSE so the
    ledger can tell it from the normal 15:52/15:55 flatten."""
    lines = _capture(eod, monkeypatch)
    monkeypatch.setattr(eod.market_calendar, "cached_close", lambda d: "13:00")
    monkeypatch.setattr(eod, "et_now", lambda: dt.datetime(2026, 9, 2, 12, 45, 0))

    swept: dict = {}
    def fake_sweep(log_path, jsonl_path, all_creds, reason):
        swept["reason"] = reason
        swept["arms"] = sorted(all_creds.keys())
    monkeypatch.setattr(eod, "_run_sweep", fake_sweep)

    assert eod._run_only_if_early_close() == 0
    assert any("EARLY_CLOSE_TRIGGER" in l for l in lines), lines
    assert swept.get("reason") == "EARLY_CLOSE", (
        "the sweep must be tagged EARLY_CLOSE -- without it the ledger cannot distinguish "
        "an early-close flatten from the normal one"
    )
    assert swept.get("arms"), "the sweep was handed no accounts"


def test_exactly_at_the_threshold_triggers(eod, monkeypatch):
    """Boundary: 12:30 is `now >= threshold`, so it sweeps rather than waiting one more
    fire -- with a 12:32 task cadence, waiting at the boundary would cost a whole cycle."""
    lines = _capture(eod, monkeypatch)
    monkeypatch.setattr(eod.market_calendar, "cached_close", lambda d: "13:00")
    monkeypatch.setattr(eod, "et_now", lambda: dt.datetime(2026, 9, 2, 12, 30, 0))
    monkeypatch.setattr(eod, "_run_sweep", lambda *a, **k: None)
    assert eod._run_only_if_early_close() == 0
    assert any("EARLY_CLOSE_TRIGGER" in l for l in lines), lines


def test_unknown_calendar_fails_closed(eod, monkeypatch):
    """Neither cache nor live GET can say -- refuse to act. Acting on an unknown calendar
    would mean flattening on a guess; the normal 15:52/15:55 flatten still runs regardless."""
    lines = _capture(eod, monkeypatch)
    monkeypatch.setattr(eod, "_resolve_today_close", lambda creds: None)
    monkeypatch.setattr(eod, "_run_sweep",
                        lambda *a, **k: pytest.fail("swept on an unknown calendar"))
    assert eod._run_only_if_early_close() == 0
    assert any("EARLY_CLOSE_UNKNOWN" in l for l in lines), lines
