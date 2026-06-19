"""Tests for the canonical decision-ledger writer (``backtest/lib/ledger.py``).

Proves the two contract guarantees that kill the DECISION-LEDGER corruption at
the WRITE side:

  1. A VALID row -> exactly ONE compact physical line is appended, and that line
     re-reads as a valid :class:`DecisionRowModel` via the contract tooling.
  2. An INVALID row -> :class:`StateContractError` is raised and NOTHING is
     written (fail-loud, never corrupt the ledger with a partial/garbage line).

Run:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_ledger_writer.py -q
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.contracts import (  # noqa: E402
    DecisionRowModel,
    StateContractError,
    load_jsonl_rows,
)
from lib.ledger import append_decision, serialize_decision  # noqa: E402


def _valid_row() -> dict:
    """A canonical decision row (mirrors the heartbeat.md template)."""
    return {
        "tick_id": 7,
        "date": "2026-06-18",
        "time_et": "10:33",
        "action": "HOLD_DEV",
        "position_status": None,
        "bull_score": 9,
        "bear_score": 4,
        "spy": 746.34,
        "vix": 16.96,
        "vix_dir": "falling",
        "ribbon_stack": "MIXED",
        "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "reason": "developing setup armed",
    }


def test_valid_row_appends_one_clean_line(tmp_path):
    """Valid row -> one physical line, re-readable as a valid DecisionRowModel."""
    led = tmp_path / "sub" / "decisions.jsonl"  # parent created on demand
    append_decision(led, _valid_row())
    append_decision(led, {**_valid_row(), "tick_id": 8, "action": "HOLD"})

    raw = led.read_text(encoding="utf-8")
    # exactly 2 physical lines, each ending in newline (one row == one line)
    assert raw.count("\n") == 2
    lines = raw.splitlines()
    assert len(lines) == 2
    # compact: no pretty-print indentation, no spaces after separators
    assert ", " not in lines[0] and ": " not in lines[0]

    # strict re-read through the SAME contract the consumers use -> all valid
    rows = load_jsonl_rows(led, DecisionRowModel)  # strict=True raises on any bad row
    assert len(rows) == 2
    assert rows[0].tick_id == 7 and rows[0].action == "HOLD_DEV"
    assert rows[0].bull_score == 9 and rows[0].bear_score == 4
    assert rows[1].tick_id == 8


def test_invalid_row_raises_and_writes_nothing(tmp_path):
    """Invalid row (missing required 'action') -> StateContractError, file untouched."""
    led = tmp_path / "decisions.jsonl"
    bad = {"tick_id": 1, "date": "2026-06-18"}  # no 'action'

    with pytest.raises(StateContractError) as ei:
        append_decision(led, bad)

    msg = str(ei.value)
    assert "decisions.jsonl" in msg  # names the destination ledger
    assert "action" in msg           # names the offending field
    # fail-loud means fail-CLOSED: no garbage line reached disk
    assert not led.exists()


def test_invalid_row_does_not_append_to_existing_ledger(tmp_path):
    """A bad write after good writes must NOT corrupt the existing ledger."""
    led = tmp_path / "decisions.jsonl"
    append_decision(led, _valid_row())
    before = led.read_text(encoding="utf-8")

    with pytest.raises(StateContractError):
        append_decision(led, {"date": "2026-06-18", "action": "HOLD"})  # missing tick_id

    after = led.read_text(encoding="utf-8")
    assert after == before  # unchanged -- the good line is intact, no partial append


def test_serialize_is_single_line_even_with_nested_objects():
    """Nested dicts (filter_state) must still serialize to ONE line."""
    row = {
        "tick_id": 1,
        "date": "2026-06-18",
        "action": "HOLD",
        "filter_state": {"bear_blocked": [6, 8, 9, 10], "bull_blocked": [5, 6]},
    }
    line = serialize_decision(row)
    assert "\n" not in line
    # round-trips back through the contract
    rows = DecisionRowModel.model_validate(row)
    assert rows.tick_id == 1
