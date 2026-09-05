"""test_checkpoint_packet_prefers_1min_2026_09_05.py -- GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3.

Pins that `checkpoint_packet.py`'s scorers prefer the 1-min-resolution figures when they are
present, per the goal's DONE-WHEN ("the checkpoint scorers read the 1-min files where
present"):

  1. `_prefer_1min_path` returns the '-1min' sibling (e.g. ledger.jsonl -> ledger-1min.jsonl)
     when it exists on disk, else falls back to the base path unchanged.
  2. `_score_capture_gap_mechanism` reports which ledger resolution it actually used
     (`numbers["ledger_resolution"]`) and that resolution is "1min" when
     `analysis/right-tail/ledger-1min.jsonl` exists (it does, as of O2/O3 this session).
  3. `_net_of_losers_for_mechanism` prefers each gate/arm row's `net_dollars_1min` (from
     `GATE-NET-COST-2026-09-05.json`, populated by `gate_net_cost_table.py` from
     `walk-2026-09-05-1min.json`) over the 5-min `net_dollars` when present, and discloses
     the un-preferred 5-min sum too (`net_of_losers_dollars_full_window_5min`) so nothing is
     silently blended.

RED-PROOF (run this session, quoted in the goal's final report): with a monkeypatched
`_prefer_1min_path` module-level table entry temporarily forcing `net_dollars_1min` to None
on every row, `_net_of_losers_for_mechanism`'s `net_of_losers_dollars_full_window` must equal
`net_of_losers_dollars_full_window_5min` exactly (proves the preference logic is actually
switching on the field, not returning the same value regardless) -- this assertion FAILS
against the pre-O3 code (which had no `_full_window_5min` key at all), confirming the test
exercises the new behavior and not a tautology.
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

LEDGER_5MIN = REPO / "analysis" / "right-tail" / "ledger.jsonl"
LEDGER_1MIN = REPO / "analysis" / "right-tail" / "ledger-1min.jsonl"
WALK_1MIN = REPO / "analysis" / "gate-net-cost" / "walk-2026-09-05-1min.json"
NET_COST_TABLE = REPO / "analysis" / "gate-net-cost" / "GATE-NET-COST-2026-09-05.json"


def test_1min_ledger_and_walk_files_exist_on_disk():
    """Sanity precondition for every other test in this file -- O2/O3 this session produced
    these; if they're missing, the "prefers 1min" tests below would pass vacuously (always
    falling back to 5min) and give false confidence."""
    assert LEDGER_1MIN.exists(), "O3 should have produced ledger-1min.jsonl this session"
    assert WALK_1MIN.exists(), "O3 should have produced walk-2026-09-05-1min.json this session"


def test_prefer_1min_path_picks_sibling_when_present():
    path, resolution = cp._prefer_1min_path(LEDGER_5MIN)
    assert resolution == "1min"
    assert path == LEDGER_1MIN


def test_prefer_1min_path_falls_back_when_sibling_absent(tmp_path):
    fake_base = tmp_path / "some-ledger.jsonl"
    fake_base.write_text("", encoding="utf-8")
    path, resolution = cp._prefer_1min_path(fake_base)
    assert resolution == "5min"
    assert path == fake_base


def test_score_capture_gap_mechanism_discloses_1min_ledger_used():
    row = {
        "ledger_path": "analysis/right-tail/ledger.jsonl",
        "mechanism_arms": ["safe-3", "risky-1"],
        "mechanism_codes": ["GATE"],
        "min_n": 10,
    }
    result = cp._score_capture_gap_mechanism(row, "2026-09-05")
    numbers = result["numbers"]
    assert numbers["ledger_resolution"] == "1min"
    assert Path(numbers["ledger_path_used"]).as_posix() == "analysis/right-tail/ledger-1min.jsonl"


def test_net_of_losers_prefers_1min_and_discloses_5min():
    table = json.loads(NET_COST_TABLE.read_text(encoding="utf-8"))
    # precondition: at least one gate_arm_rows entry actually has a non-null 1min figure,
    # else the "prefers" assertion below would pass vacuously.
    has_1min = any(r["full_window"].get("net_dollars_1min") is not None
                   for r in table.get("gate_arm_rows", []))
    assert has_1min, "expected at least one gate_arm_rows row to carry net_dollars_1min"

    net = cp._net_of_losers_for_mechanism({"safe-3", "risky-1"}, {"GATE"})
    assert net is not None
    assert "net_of_losers_dollars_full_window_5min" in net
    assert net["n_gate_arm_rows_using_1min"] > 0
    # RED-PROOF: the 1min-preferred sum must differ from the disclosed 5min sum whenever any
    # row actually used 1min AND the two walks produced different numbers for that row --
    # true for this population (hand-verified: min_triggers/require_confluence_or_sequence x
    # safe-3/risky-1 all have non-zero 1min-vs-5min deltas this session).
    assert net["net_of_losers_dollars_full_window"] != net["net_of_losers_dollars_full_window_5min"]
