"""Guard: strike-axis (and any cross-cell) comparisons must gate on OPRA-bar
coverage parity before a delta is trusted.

WHY THIS GUARD EXISTS (conductor 2026-08-03, OPTION-CACHE-ITM-COVERAGE-GAP)
-----------------------------------------------------------------------------
`ribbon_ride_strike_exit_ab.py`'s strike-axis study found the 5-min OPRA disk
cache's missing-bar rate widens monotonically with distance from OTM-2 (real
illiquidity on far-ITM 0DTE strikes, not a fetch-script bug -- confirmed
`expand_opra_cache.py` requests a symmetric +/-5 strike window every day):
0/250 missing at OTM-2, 1/250 at OTM-1, 6/250 at ATM, 19/250 at ITM-2
(analysis/recommendations/ribbon-ride-strike-exit-ab-1min-coverage-matched-
2026-08-02.json). Each cell already DISCLOSES `n_no_local_bars` -- but nothing
GATED on it: a caller could compare a 0%-missing control against a 7.6%-missing
candidate and treat the resulting delta as a clean strike edge, silently
comparing differently-sized populations (this session's own check confirmed the
already-shipped ITM-2 verdict was unaffected -- but a FUTURE strike study
wouldn't get that check for free without a reusable gate).

Fix: `backtest/lib/coverage_parity.py#check_coverage_parity` -- a pure,
reusable assertion any strike-axis (or other cross-cell) study can call. Wired
into `ribbon_ride_strike_exit_ab.py#compare()`: a coverage-mismatched pair now
forces `clears_auto_ratify_bar=False` and `ship_or_wait="WAIT_COVERAGE_GAP"`
regardless of every other flag (OOS+/WF/sub-window/anchor all passing does not
matter if the underlying populations aren't matched).

These tests pin:
  * check_coverage_parity: equal-coverage cells pass; a >5pp spread fails;
    a zero-attempted cell fails closed (None, not an accidental 0.0% pass);
    fewer than 2 cells fails closed.
  * compare(): a synthetic candidate/control pair that clears EVERY other
    auto-ratify flag (OOS+, WF>=0.70, sub_window_stable, anchor_no_regression,
    stable-on-audit) but has a large n_no_local_bars spread still resolves
    clears_auto_ratify_bar=False and ship_or_wait="WAIT_COVERAGE_GAP" -- proving
    the new gate, not the pre-existing flags, is what blocks it.
  * a non-vacuous BITE: neutering the coverage-parity call (patching it to
    always report parity_ok=True) reproduces the OLD behaviour (SHIP) on the
    exact same inputs, proving the gate is what changes the outcome.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from lib.coverage_parity import check_coverage_parity  # noqa: E402


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------
def test_equal_coverage_passes():
    result = check_coverage_parity([
        {"cell_id": "OTM-2", "n_no_local_bars": 5, "n_total_attempted": 250},
        {"cell_id": "ITM-2", "n_no_local_bars": 6, "n_total_attempted": 250},
    ])
    assert result["parity_ok"] is True
    assert result["observed_delta_pp"] == pytest.approx(0.4, abs=0.01)


def test_large_spread_fails():
    result = check_coverage_parity([
        {"cell_id": "OTM-2", "n_no_local_bars": 0, "n_total_attempted": 250},
        {"cell_id": "ITM-2", "n_no_local_bars": 19, "n_total_attempted": 250},
    ])
    assert result["parity_ok"] is False
    assert result["observed_delta_pp"] == pytest.approx(7.6, abs=0.01)
    assert "spread" in result["reason"]


def test_boundary_exactly_at_max_delta_passes():
    # 5.0pp spread with default max_delta_pp=5.0 -- inclusive boundary.
    result = check_coverage_parity([
        {"cell_id": "A", "n_no_local_bars": 0, "n_total_attempted": 100},
        {"cell_id": "B", "n_no_local_bars": 5, "n_total_attempted": 100},
    ])
    assert result["observed_delta_pp"] == 5.0
    assert result["parity_ok"] is True


def test_zero_attempted_cell_fails_closed_not_silently_zero():
    result = check_coverage_parity([
        {"cell_id": "OTM-2", "n_no_local_bars": 0, "n_total_attempted": 250},
        {"cell_id": "GHOST", "n_no_local_bars": 0, "n_total_attempted": 0},
    ])
    assert result["parity_ok"] is False
    assert result["rates"]["GHOST"] is None
    assert "no-evidence" in result["reason"]


def test_fewer_than_two_cells_fails_closed():
    result = check_coverage_parity([{"cell_id": "OTM-2", "n_no_local_bars": 0, "n_total_attempted": 250}])
    assert result["parity_ok"] is False


def test_custom_max_delta_pp_tightens_the_gate():
    result = check_coverage_parity(
        [
            {"cell_id": "A", "n_no_local_bars": 0, "n_total_attempted": 250},
            {"cell_id": "B", "n_no_local_bars": 3, "n_total_attempted": 250},
        ],
        max_delta_pp=1.0,
    )
    assert result["parity_ok"] is False  # 1.2pp spread > tightened 1.0pp bar


# ---------------------------------------------------------------------------
# Wiring test: ribbon_ride_strike_exit_ab.compare() must respect the gate
# ---------------------------------------------------------------------------
def _make_cell(cell_id: str, n: int, n_no_local_bars: int, expectancy: float, ecr: float) -> dict:
    return {
        "cell_id": cell_id,
        "n_no_local_bars": n_no_local_bars,
        "metrics": {
            "n": n,
            "expectancy": expectancy,
            "oos_total": expectancy * n,
            "oos_positive": True,
            "wf": 0.9,
            "wf_ge_070": True,
            "sub_window_stable": True,
            "edge_capture_rel": ecr,
        },
        "sensitivity_old_fillbar_convention": {"expectancy": expectancy},
    }


@pytest.fixture()
def rrse():
    import ribbon_ride_strike_exit_ab as mod
    return mod


def test_compare_blocks_ship_on_coverage_mismatch_despite_all_other_flags_passing(rrse):
    # Candidate beats control on every OTHER axis (OOS+, WF, sub-window, anchor, stable)
    # but candidate's coverage is far worse (19/250 vs 0/250 missing) -- must NOT ship.
    candidate = _make_cell("ITM-2", n=231, n_no_local_bars=19, expectancy=5.0, ecr=100.0)
    control = _make_cell("OTM-2", n=250, n_no_local_bars=0, expectancy=1.0, ecr=50.0)
    result = rrse.compare(candidate, control, label="strike_axis")
    assert result["candidate_beats_control"] is True  # the OTHER flags really do all clear
    assert result["auto_ratify_flags"]["oos_positive"] is True
    assert result["auto_ratify_flags"]["wf_ge_070"] is True
    assert result["anchor_no_regression_op16"] is True
    assert result["coverage_parity"]["parity_ok"] is False
    assert result["clears_auto_ratify_bar"] is False
    assert result["ship_or_wait"] == "WAIT_COVERAGE_GAP"


def test_compare_ships_when_coverage_matched_and_all_flags_clear(rrse):
    candidate = _make_cell("OTM-1", n=249, n_no_local_bars=1, expectancy=5.0, ecr=100.0)
    control = _make_cell("OTM-2", n=250, n_no_local_bars=0, expectancy=1.0, ecr=50.0)
    result = rrse.compare(candidate, control, label="strike_axis")
    assert result["coverage_parity"]["parity_ok"] is True
    assert result["clears_auto_ratify_bar"] is True
    assert result["ship_or_wait"] == "SHIP"


def test_bite_neutering_the_gate_reproduces_old_behaviour(rrse, monkeypatch):
    """Non-vacuous proof: patch check_coverage_parity to always report parity_ok=True
    (the pre-fix behaviour) and confirm the SAME mismatched-coverage inputs now ship --
    demonstrating the gate itself, not some other flag, is what blocks it above."""
    monkeypatch.setattr(
        rrse, "check_coverage_parity",
        lambda cells, max_delta_pp=5.0: {"parity_ok": True, "observed_delta_pp": 0.0,
                                          "max_delta_pp": max_delta_pp, "rates": {},
                                          "reason": "neutered for BITE test"},
    )
    candidate = _make_cell("ITM-2", n=231, n_no_local_bars=19, expectancy=5.0, ecr=100.0)
    control = _make_cell("OTM-2", n=250, n_no_local_bars=0, expectancy=1.0, ecr=50.0)
    result = rrse.compare(candidate, control, label="strike_axis")
    assert result["clears_auto_ratify_bar"] is True
    assert result["ship_or_wait"] == "SHIP"
