"""RED-proof for GOAL-TP1-FRACTION-AB-2026-09-05 A4: the tp1-qty-fraction-safe-0-8 row in
checkpoint-2026-09-29-inventory.json must flip from UNKNOWN to a real verdict once
checkpoint_packet.py reads analysis/recommendations/tp1-fraction-ab-2026-09-05.json.

Before the A4 fix: row["scorer"] == "n/a -- UNAPPLIED-RATIFICATION refile, not a scored
shadow" -> score_row's dispatcher finds no registered scorer -> verdict UNKNOWN (quoted in
the goal brief as the starting state). This test is RED against that state and GREEN once
_score_tp1_qty_fraction_safe_0_8 is registered and the inventory row's scorer field points
to it.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
for _p in (str(SCRIPTS_DIR), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import checkpoint_packet as cp  # noqa: E402


def test_tp1_fraction_row_is_not_unknown():
    packet = cp.build_packet()
    row = next(r for r in packet["rows"] if r["row_id"] == "tp1-qty-fraction-safe-0-8")
    assert row["verdict"] != cp.VERDICT_UNKNOWN, row.get("note")


def test_tp1_fraction_row_reads_the_ab_file_and_reports_not_met():
    """The A3 result (safe-2 net delta $0.00 no-op; safe-3 net delta -$182.00 both windows,
    negative bootstrap CI-lower) fails the prereg's gate-1 (OOS/full-window positive) for
    both Safe arms -- verdict must be RULE NOT MET."""
    packet = cp.build_packet()
    row = next(r for r in packet["rows"] if r["row_id"] == "tp1-qty-fraction-safe-0-8")
    assert row["verdict"] == cp.VERDICT_NOT_MET
    assert row["numbers"]["safe_2_net_delta"] == 0.0
    assert row["numbers"]["safe_3_net_delta"] < 0
