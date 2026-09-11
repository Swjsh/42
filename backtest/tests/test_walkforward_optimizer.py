"""Anti-leakage guard for the walk-forward exit optimizer.

The whole value of a walk-forward result is that no test bar is chosen using its own
(or future) data. These tests build a synthetic per-trade table and prove:
  1. every test-fold trade date is strictly AFTER its train window,
  2. each test trade is used in exactly one fold (folds partition the test region),
  3. the chosen cell per fold depends ONLY on train data,
  4. a planted leak (test date inside train window) is CAUGHT by the assertion.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch import walkforward_optimizer as wf  # noqa: E402


def _synthetic_trades(n: int) -> list[dict]:
    """n trades on distinct increasing dates; each grid cell gets a deterministic pnl.
    Cell A (first) is best in the first half, cell B (last) best in the second half, so a
    correct WF must SWITCH -- and must never peek at the test half to do it."""
    shapes = list(wf.build_grid_shapes().keys())
    first, last = shapes[0], shapes[-1]
    trades = []
    for i in range(n):
        date = f"2025-{(i // 20) + 1:02d}-{(i % 20) + 1:02d}"
        pnl = {c: 0.0 for c in shapes}
        if i < n // 2:
            pnl[first] = 100.0   # first cell wins early
        else:
            pnl[last] = 100.0    # last cell wins late
        trades.append({"date": date, "side": "C", "strike": 500 + i, "pnl": pnl})
    return trades


def test_walk_forward_no_leakage_and_partition():
    trades = _synthetic_trades(90)  # plenty for K folds at MIN=15
    # force a feasible K
    res = None
    for k in (5, 4, 3, 2):
        r = wf.walk_forward(trades, k)
        if r.get("feasible"):
            res = r
            break
    assert res is not None and res["feasible"], "expected a feasible fold config"
    # folds partition the test region exactly, are ordered and disjoint
    seen: set = set()
    prev_test_end = None
    for f in res["folds"]:
        td0, td1 = f["test_dates"]
        tr0, tr1 = f["train_dates"]
        # strict anti-leakage: every test date after every train date
        assert td0 > tr1, f"leak: test {td0} <= train_end {tr1}"
        key = (td0, td1)
        assert key not in seen, "test fold reused"
        seen.add(key)
        if prev_test_end is not None:
            assert td0 > prev_test_end, "test folds overlap/out-of-order"
        prev_test_end = td1


def test_walk_forward_switches_cell_without_peeking():
    """The early half favours the first cell, the late half the last cell. A leak-free WF
    picks the EARLY-favouring cell for at least the first test fold (it only saw early
    train data), NOT the late-favouring one -- proving it did not peek."""
    trades = _synthetic_trades(90)
    res = None
    for k in (5, 4, 3, 2):
        r = wf.walk_forward(trades, k)
        if r.get("feasible"):
            res = r
            break
    shapes = list(wf.build_grid_shapes().keys())
    first = shapes[0]
    # first test fold's train window is entirely in the early half -> must choose `first`
    assert res["folds"][0]["chosen_cell"] == first, (
        "WF fold 0 should choose the early-favouring cell from train-only data")


def test_planted_leak_is_caught():
    """Manually corrupt trade ordering so a test date falls inside the train window and
    confirm the in-code assertion fires (proves the guard is real, not decorative)."""
    trades = _synthetic_trades(90)
    # shuffle a late trade's date to be very early -> when it lands in a test fold, its
    # date will be <= a train date, tripping the assertion.
    trades[80]["date"] = "2025-01-01"  # earliest possible; now test fold has a date <= train
    with pytest.raises(AssertionError, match="LEAKAGE"):
        # unsorted on purpose: walk_forward assumes caller sorted; feed a config that
        # will surface the leak. We sort by original index NOT date to plant the leak.
        # Re-sort by date would hide it, so call directly on the corrupted, date-unsorted list.
        wf.walk_forward(trades, 3)


def test_grid_is_preregistered_shape():
    shapes = wf.build_grid_shapes()
    assert len(shapes) == len(wf.STOPS) * len(wf.TP1S) == 9
    static = wf._cell_id(wf.STATIC_STOP, wf.STATIC_TP1)
    assert static in shapes, "static cell must be inside the pre-registered grid"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
