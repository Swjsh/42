"""Guards for WP-3 blocker naming + the nightly histogram.

The point of WP-3 is that "why didn't the lane trade" must be answerable in one read. Two ways
that promise breaks: a HOLD row with no blockers (unanswerable), and a summary that prints an
impossible number (untrustworthy — the first draft rendered "160% of scored").
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi import core  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "multi_blocker_histogram", REPO / "setup" / "scripts" / "multi_blocker_histogram.py")
HIST = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(HIST)


def test_blocker_numbers_become_readable_names():
    got = core.name_blockers([9, 10])
    assert got == ["F9:breakdown_bar", "F10:level_tied_trigger"], got


def test_unknown_filter_number_is_labelled_not_dropped():
    """An unmapped filter must still appear — silently dropping it would hide a real veto."""
    got = core.name_blockers([99])
    assert got == ["F99:unknown"], got


def test_garbage_blocker_entries_do_not_crash_the_row():
    assert core.name_blockers([None, "x", 5]) == ["F5:ribbon_stack"]
    assert core.name_blockers(None) == []


def _ledger(tmp_path, rows):
    import json
    p = tmp_path / "shadow-ledger.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    HIST.LEDGER = p
    return p


def test_percentage_can_never_exceed_100(tmp_path, monkeypatch):
    """THE regression guard. F10 appears on BOTH sides; a combined count over a one-side
    denominator rendered 160%, which is a number that destroys trust in the whole surface."""
    rows = [{"ts_et": "2026-08-20T12:00:00-04:00", "decision": "HOLD", "gate": "action_directional",
             "bear_blockers": ["F10:level_tied_trigger"],
             "bull_blockers": ["F10:level_tied_trigger"]} for _ in range(5)]
    _ledger(tmp_path, rows)
    monkeypatch.setattr(HIST, "OUT_DIR", tmp_path)
    h = HIST.build("2026-08-20")
    assert h["top_blocker"]["pct_of_scored"] <= 100.0, h["top_blocker"]
    for side in ("bear_blockers", "bull_blockers"):
        for b in h[side]:
            assert b["pct_of_scored"] <= 100.0, (side, b)


def test_top_blocker_names_its_side(tmp_path, monkeypatch):
    rows = [{"ts_et": "2026-08-20T12:00:00-04:00", "decision": "HOLD", "gate": "action_directional",
             "bear_blockers": ["F5:ribbon_stack"], "bull_blockers": []} for _ in range(4)]
    _ledger(tmp_path, rows)
    monkeypatch.setattr(HIST, "OUT_DIR", tmp_path)
    h = HIST.build("2026-08-20")
    assert h["top_blocker"]["side"] == "bear"
    assert h["top_blocker"]["blocker"] == "F5:ribbon_stack"


def test_zero_scored_rows_is_reported_not_divided_by(tmp_path, monkeypatch):
    rows = [{"ts_et": "2026-08-20T12:00:00-04:00", "decision": "BLOCKED", "gate": "bars_ok"}]
    _ledger(tmp_path, rows)
    monkeypatch.setattr(HIST, "OUT_DIR", tmp_path)
    h = HIST.build("2026-08-20")
    assert h["rows_scored"] == 0
    assert h["top_blocker"] is None
    assert h["gate_counts"]["bars_ok"] == 1
