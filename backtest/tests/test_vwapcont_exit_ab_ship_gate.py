"""Guard for the vwap_continuation exit-param OOS ship-gate harness.

Protects the invariants that make the SHIP verdict trustworthy:
  1. The A/B compares the LIVE-armed cell: CURRENT = -0.08/0.30, CANDIDATE = -0.06/0.40,
     both at ATM (strike_offset=0). If someone edits the cells, this REDs -- because a
     ship gate that silently changes what it validates is worse than no gate.
  2. drop_topk_positive removes the top-k trades and reports positivity correctly
     (concentration robustness must not be faked by an off-by-one).
  3. The parity target is the scorecard's full-sample static exp (47.27) with a tight
     tolerance -- a loosened tolerance would let a non-reproducing baseline pass.

These are pure-logic guards (no OPRA fetch) so they run in CI. The real-fills numbers
live in analysis/recommendations/vwapcont-exit-ab-ship-gate.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch import vwapcont_exit_ab_ship_gate as sg  # noqa: E402


def test_cells_are_the_live_and_candidate_pair():
    """CURRENT must be the live-armed cell; CANDIDATE the proposed one. ATM only (C29)."""
    assert sg.CURRENT["premium_stop_pct"] == -0.08
    assert sg.CURRENT["tp1_premium_pct"] == 0.30
    assert sg.CANDIDATE["premium_stop_pct"] == -0.06
    assert sg.CANDIDATE["tp1_premium_pct"] == 0.40
    assert sg.STRIKE_OFFSET == 0, "must validate ATM = the live Safe-2 cell, not ITM-2"


def test_base_shape_identical_across_cells():
    """The ONLY difference between the two cells is (stop, tp1) -- exit shape is held."""
    ignore = {"premium_stop_pct", "tp1_premium_pct"}
    cur = {k: v for k, v in sg.CURRENT.items() if k not in ignore}
    cand = {k: v for k, v in sg.CANDIDATE.items() if k not in ignore}
    assert cur == cand == sg.BASE_SHAPE


class _Row:
    def __init__(self, pnl):
        self.pnl = pnl


def test_drop_topk_removes_top_k_and_reports_positive():
    rows = [_Row(p) for p in [1000.0, 5.0, 4.0, 3.0, -2.0]]
    r = sg.drop_topk_positive(rows, 3)
    # top-3 removed = {1000, 5, 4}; kept = {3, -2} -> total 1.0 > 0
    assert r["n_dropped"] == 3
    assert r["total_ex_topk"] == 1.0
    assert r["positive"] is True


def test_drop_topk_flags_negative_when_edge_is_top_heavy():
    rows = [_Row(p) for p in [1000.0, 900.0, 800.0, -50.0, -60.0]]
    r = sg.drop_topk_positive(rows, 3)
    # kept = {-50, -60} -> negative: a top-heavy edge must NOT pass drop-top3
    assert r["total_ex_topk"] == -110.0
    assert r["positive"] is False


def test_parity_tolerance_is_tight():
    """A loose parity tolerance would let a non-reproducing baseline masquerade as valid."""
    assert sg.PARITY_TARGET_FULL_EXP == 47.27
    assert sg.PARITY_TOL <= 1.0, "parity tolerance must stay tight (< $1/tr)"


def test_wf_gate_is_070():
    assert sg.WF_GATE == 0.70
