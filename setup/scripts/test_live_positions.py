"""Tests for live_positions.py -- the shared exit-state.json reader.

Covers: empty-dict flat read, one/two open legs parsed correctly (incl. strike
derived from an OCC-style symbol), missing file raises (never silently "flat"),
corrupt JSON raises, non-dict JSON raises, unknown arm raises,
position_status_label() never returns "flat" on a read failure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import live_positions as lp  # noqa: E402


@pytest.fixture(autouse=True)
def _patch_arm_paths(tmp_path, monkeypatch):
    """Point both arms at tmp files so tests never touch real repo state."""
    safe_path = tmp_path / "safe-2" / "exit-state.json"
    bold_path = tmp_path / "bold-2" / "exit-state.json"
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    bold_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(lp, "ARM_EXIT_STATE", {
        "safe": safe_path, "safe-2": safe_path,
        "bold": bold_path, "bold-2": bold_path,
    })
    return {"safe": safe_path, "bold": bold_path}


def test_empty_dict_is_flat(_patch_arm_paths):
    _patch_arm_paths["safe"].write_text("{}", encoding="utf-8")
    assert lp.read_open_positions("safe") == []
    assert lp.is_flat("safe") is True
    assert lp.position_status_label("safe") == "flat"


def test_one_open_leg_parsed(_patch_arm_paths):
    rec = {
        "SPY260915P00757000": {
            "side": "P", "total_qty": 3, "entry_premium": 1.25,
            "hwm_premium": 1.40, "strategy": "BEARISH_REJECTION_RIDE_THE_RIBBON",
            "runner_stop_premium": 1.0, "profit_lock_armed": True,
        }
    }
    _patch_arm_paths["safe"].write_text(json.dumps(rec), encoding="utf-8")
    rows = lp.read_open_positions("safe")
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "SPY260915P00757000"
    assert row["side"] == "P"
    assert row["strike"] == 757.0
    assert row["qty"] == 3
    assert row["entry_premium"] == 1.25
    assert row["hwm_premium"] == 1.40
    assert row["strategy"] == "BEARISH_REJECTION_RIDE_THE_RIBBON"
    assert row["profit_lock_armed"] is True
    assert lp.is_flat("safe") is False
    assert lp.position_status_label("safe") == "open"


def test_two_open_legs_both_arms(_patch_arm_paths):
    _patch_arm_paths["safe"].write_text(
        json.dumps({"SPY260915P00757000": {"side": "P", "total_qty": 3}}),
        encoding="utf-8",
    )
    _patch_arm_paths["bold"].write_text(
        json.dumps({"SPY260915P00755000": {"side": "P", "total_qty": 5}}),
        encoding="utf-8",
    )
    assert len(lp.read_open_positions("safe-2")) == 1
    assert len(lp.read_open_positions("bold-2")) == 1


def test_missing_file_raises_not_flat(_patch_arm_paths):
    # File was never written -- must NOT be treated as flat.
    with pytest.raises(lp.LivePositionsError):
        lp.read_open_positions("safe")
    with pytest.raises(lp.LivePositionsError):
        lp.is_flat("safe")
    assert lp.position_status_label("safe") == "unknown"


def test_corrupt_json_raises(_patch_arm_paths):
    _patch_arm_paths["safe"].write_text("{not valid json", encoding="utf-8")
    with pytest.raises(lp.LivePositionsError):
        lp.read_open_positions("safe")
    assert lp.position_status_label("safe") == "unknown"


def test_non_dict_json_raises(_patch_arm_paths):
    _patch_arm_paths["safe"].write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(lp.LivePositionsError):
        lp.read_open_positions("safe")


def test_malformed_entry_skipped_not_fatal(_patch_arm_paths):
    rec = {
        "SPY260915P00757000": {"side": "P", "total_qty": 3},
        "GARBAGE_KEY": "not-a-dict",
    }
    _patch_arm_paths["safe"].write_text(json.dumps(rec), encoding="utf-8")
    rows = lp.read_open_positions("safe")
    assert len(rows) == 1
    assert rows[0]["symbol"] == "SPY260915P00757000"


def test_unknown_arm_raises():
    with pytest.raises(lp.LivePositionsError):
        lp.read_open_positions("not-a-real-arm")


def test_strike_parse_failure_yields_none_strike(_patch_arm_paths):
    rec = {"NOT_AN_OCC_SYMBOL": {"side": "P", "total_qty": 1}}
    _patch_arm_paths["safe"].write_text(json.dumps(rec), encoding="utf-8")
    rows = lp.read_open_positions("safe")
    assert rows[0]["strike"] is None
