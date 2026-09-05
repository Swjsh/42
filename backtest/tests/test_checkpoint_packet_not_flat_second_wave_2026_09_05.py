"""RED-proof for GOAL-NOT-FLAT-SECOND-WAVE-PREREG-2026-09-05 W2: the not-flat-second-wave
row in checkpoint-2026-09-29-inventory.json must score via a registered scorer (not fall
through to UNKNOWN) and must surface the NOT_FLAT gate's frozen-window/full-window net
numbers straight from GATE-NET-COST-2026-09-05.json's dedup-to-waves row.

Before the W2 fix: the inventory row did not exist and no `not_flat_second_wave` scorer
was registered in checkpoint_packet.py -- `score_row` would either not find the row at all
(KeyError from `next(...)`) or, if the row existed with an unregistered scorer name, would
report verdict UNKNOWN with "no scorer registered for 'not_flat_second_wave'". This test is
RED against either of those states and GREEN once the row + scorer are both wired.
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


def _row():
    packet = cp.build_packet()
    return next(r for r in packet["rows"] if r["row_id"] == "not-flat-second-wave")


def test_not_flat_second_wave_row_exists_and_is_not_unknown():
    row = _row()
    assert row["verdict"] != cp.VERDICT_UNKNOWN, row.get("note")


def test_not_flat_second_wave_row_is_insufficient_n_while_frozen():
    """The prereg is FROZEN_BEFORE_ANY_RESULT with no forward second-wave-refusal
    sample accrued yet -- verdict must be INSUFFICIENT N, never a premature MET/NOT MET
    on the backward-only numbers."""
    row = _row()
    assert row["verdict"] == cp.VERDICT_INSUFFICIENT_N


def test_not_flat_second_wave_row_surfaces_gate_net_cost_numbers():
    """Numbers must be read from GATE-NET-COST-2026-09-05.json's NOT_FLAT dedup-to-waves
    row, not re-derived: full-window net_dollars=7543.0 over 99 waves, frozen-window
    net_dollars=-631.0 over 14 waves (opposite sign -- the whole point of the prereg)."""
    row = _row()
    n = row["numbers"]
    assert n["full_window_net_dollars"] == 7543.0
    assert n["full_window_n_waves"] == 99
    assert n["frozen_window_net_dollars"] == -631.0
    assert n["frozen_window_n_waves"] == 14
    assert n["frozen_window_net_dollars"] < 0 < n["full_window_net_dollars"]
