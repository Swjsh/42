"""test_checkpoint_packet_net_of_losers_2026_09_05.py -- GOAL-GATE-NET-COST-2026-09-05 N4.

Pins `checkpoint_packet._score_capture_gap_mechanism`'s new behavior: it must surface
`net_of_losers_dollars_full_window` / `_frozen_window` (read from
`analysis/gate-net-cost/GATE-NET-COST-2026-09-05.json`'s per-(gate,arm) NET, i.e. winners +
losers walked through the real exit shape) in its `numbers` dict, for both mechanism-1
(gate_override, code "GATE" -> min_triggers + require_confluence_or_sequence combined) and
mechanism-6 (sizing floor, code "SKIP_MIN_PREMIUM_FLOOR" -> direct match). Never the raw
refused-winner CEILING (`dollar_figure`) -- this scorer must not read that field at all.

RED-PROOF (run this session): monkeypatching `_NET_COST_TABLE_PATH` to a path that does not
exist makes `_net_of_losers_for_mechanism` return None and `numbers` carry NO
`net_of_losers_dollars_*` key -- `test_mechanism1_net_of_losers_present` then fails its
`assert "net_of_losers_dollars_full_window" in numbers` line, confirming the key is not
present unconditionally / by accident.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import checkpoint_packet as cp  # noqa: E402

NET_COST_TABLE = REPO / "analysis" / "gate-net-cost" / "GATE-NET-COST-2026-09-05.json"


def _row(mechanism_arms, mechanism_codes, min_n=10):
    return {
        "ledger_path": "analysis/right-tail/ledger.jsonl",
        "mechanism_arms": mechanism_arms,
        "mechanism_codes": mechanism_codes,
        "min_n": min_n,
        "forward_window_start": "2026-09-05",
    }


def test_net_cost_table_exists_on_disk():
    """Precondition every other test in this file relies on: N3 must have run."""
    assert NET_COST_TABLE.exists(), "run setup/scripts/gate_net_cost_table.py (N3) first"


def test_mechanism1_net_of_losers_present():
    row = _row(["safe-3", "risky-1"], ["GATE"])
    result = cp._score_capture_gap_mechanism(row, "2026-09-05")
    numbers = result["numbers"]
    assert "net_of_losers_dollars_full_window" in numbers
    assert "net_of_losers_dollars_frozen_window" in numbers
    # matched rows must be exactly the 4 (gate x arm) combos this mechanism covers
    matched = numbers["matched_gate_arm_rows"]
    seen = {(m["gate"], m["arm"]) for m in matched}
    assert seen == {
        ("min_triggers", "safe-3"), ("min_triggers", "risky-1"),
        ("require_confluence_or_sequence", "safe-3"), ("require_confluence_or_sequence", "risky-1"),
    }


def test_mechanism6_net_of_losers_present_bold2_only():
    row = _row(["bold-2"], ["SKIP_MIN_PREMIUM_FLOOR"])
    result = cp._score_capture_gap_mechanism(row, "2026-09-05")
    numbers = result["numbers"]
    matched = numbers["matched_gate_arm_rows"]
    seen = {(m["gate"], m["arm"]) for m in matched}
    assert seen == {("SKIP_MIN_PREMIUM_FLOOR", "bold-2")}
    # bold-2's SKIP_MIN_PREMIUM_FLOOR net must be negative (EARNING) per N3's own table --
    # pin the SIGN, not the exact cent value, so this test survives a future N2/N3 data refresh.
    assert numbers["net_of_losers_dollars_full_window"] < 0


def test_scorer_never_reads_ceiling_dollar_figure():
    """`dollar_figure` (the raw refused-WINNER ceiling, e.g. 4354.92 / 1664.00) must never
    appear anywhere in this scorer's output -- the goal explicitly requires reading the NET,
    not the ceiling."""
    row = _row(["bold-2"], ["SKIP_MIN_PREMIUM_FLOOR"])
    row["dollar_figure"] = 1664.00  # simulate the prereg's own ceiling leaking into the row
    result = cp._score_capture_gap_mechanism(row, "2026-09-05")
    assert "dollar_figure" not in result["numbers"]
    assert 1664.00 not in result["numbers"].values()


def test_net_of_losers_helper_fails_open_on_missing_table(monkeypatch):
    """RED-PROOF fixture: point the table path at a file that does not exist -- the helper
    must return None (fail open), never raise, and the scorer's `numbers` must then have NO
    net_of_losers_dollars_* key at all (proving the key's presence above is conditional on a
    real read, not hardcoded)."""
    monkeypatch.setattr(cp, "_NET_COST_TABLE_PATH", REPO / "analysis" / "gate-net-cost" / "DOES-NOT-EXIST.json")
    row = _row(["bold-2"], ["SKIP_MIN_PREMIUM_FLOOR"])
    result = cp._score_capture_gap_mechanism(row, "2026-09-05")
    assert "net_of_losers_dollars_full_window" not in result["numbers"]
    assert "net_of_losers_dollars_frozen_window" not in result["numbers"]


def test_score_row_dispatches_capture_gap_mechanism_without_unknown():
    """End-to-end through the public score_row dispatcher (not the scorer directly) --
    confirms the scorer is actually registered in _SCORERS and reachable by name."""
    row = _row(["bold-2"], ["SKIP_MIN_PREMIUM_FLOOR"])
    row["scorer"] = "capture_gap_mechanism"
    result = cp.score_row(row, "2026-09-05")
    assert result["verdict"] != cp.VERDICT_UNKNOWN
    assert "net_of_losers_dollars_full_window" in result["numbers"]
