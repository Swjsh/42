"""Guard for the BIGGER-WINNERS exit-target matrix (2026-08-19).

Pins the two load-bearing claims of
analysis/deep-research/WINNERS-EXIT-TARGET-MATRIX-2026-08-19.md so a future regeneration
cannot silently flip the verdict without someone noticing:

  1. SIM FIDELITY. The production shape re-walked under the range-realism market fill model
     reconciles to broker truth. If that breaks, every delta in the report is measured
     against a fiction -- which is exactly the failure the report caught in the repo's
     legacy limit-fill convention (+$3,392 of manufactured P&L).
  2. CONCENTRATION. The best cell's advantage is carried by one trading day. The verdict is
     NO EDGE *because* of that number; if a regeneration ever produces a diffuse effect,
     this test must go RED so the verdict gets re-argued rather than inherited.

Reads only the committed scored JSON -- no grid re-run, no network, milliseconds.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCORED = REPO / "analysis" / "deep-research" / "WINNERS-EXIT-TARGET-MATRIX-2026-08-19.json"
ROBUST = REPO / "analysis" / "deep-research" / "WINNERS-EXIT-TARGET-MATRIX-2026-08-19.robust.json"

PRIMARY = "pnl_market_range"
BEST_CELL = "f0.5_t1.0_r99.0_x0.4"
PRODUCTION_CELL = "f0.667_t1.0_r99.0_x0.15"   # ribbon_ride's live shape, as a grid coordinate


@pytest.fixture(scope="module")
def scored() -> dict:
    if not SCORED.exists():
        pytest.skip("scored matrix not built; run winners_exit_target_report_2026_08_19.py")
    return json.loads(SCORED.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def robust() -> dict:
    if not ROBUST.exists():
        pytest.skip("robustness file not built; run winners_exit_target_robustness_2026_08_19.py")
    return json.loads(ROBUST.read_text(encoding="utf-8"))


def test_population_is_the_whole_book_with_nothing_dropped(scored):
    """303 closed round trips, zero silent drops. A shrinking population is a bug, not a filter."""
    assert scored["population"]["n_trades"] == 303
    assert scored["population"]["skipped"] == []
    assert scored["unique_cell_count"] == 246
    assert scored["nominal_cell_count"] == 360


def test_primary_fill_model_reconciles_to_broker_truth(scored):
    """The range-realism model must stay within +/-$500 of the realised gross book.

    Broker truth is -$1,805 gross on 303 trades. At build time the replay landed +$341
    (+$1.13/trade). The legacy limit convention landed +$3,392 -- an order of magnitude
    worse and the reason it is NOT the primary accounting.
    """
    gaps = scored["fidelity"]["gap_vs_real_gross"]
    assert scored["fidelity"]["real_book_gross"] == pytest.approx(-1805.0, abs=0.01)
    assert abs(gaps[PRIMARY]) < 500.0, (
        "primary fill model no longer reconciles to broker truth: gap %.2f" % gaps[PRIMARY])
    assert abs(gaps[PRIMARY]) < abs(gaps["pnl_limit"]), (
        "the legacy limit model now reconciles better than the realistic one -- re-derive "
        "which model is primary before trusting any delta")


def test_cell_ranking_is_not_an_artifact_of_the_fill_model(scored):
    """The top cell under the primary model must also rank top-5 under the flat-2c model.

    Fill price never feeds back into the decision path, so a ranking that flips between
    accountings would mean the effect IS the accounting.
    """
    cells = scored["cells"]
    top_primary = max(cells, key=lambda c: c[PRIMARY + "_delta_net"])["cell_id"]
    by_flat = sorted(cells, key=lambda c: -c["pnl_market_delta_net"])[:5]
    assert top_primary in [c["cell_id"] for c in by_flat]


def test_win_rate_is_not_the_lever(scored):
    """This lever moves avg_win, never win rate. If a cell ever wins by lifting WR while
    lowering net P&L, the report's rule 4 ("that is a FAILURE") has to be applied by hand."""
    cells = {c["cell_id"]: c for c in scored["cells"]}
    prod = scored["production_cell"]["scores"][PRIMARY]
    best = cells[BEST_CELL][PRIMARY]
    assert best["win_rate"] == pytest.approx(prod["win_rate"], abs=0.02)
    assert best["avg_win"] > prod["avg_win"]


def test_best_cell_advantage_is_one_day_and_the_verdict_stays_no_edge(robust):
    """THE verdict pin. Top-day share > 60% and the two-day-out delta is not positive.

    If either of these ever changes, the NO EDGE verdict must be re-argued from scratch --
    do not inherit it.
    """
    cell = next(c for c in robust["cells"] if c["cell_id"] == BEST_CELL)
    top_day_name, _, top_day_share = cell["top_day"]
    assert top_day_name == "2026-08-04"
    assert top_day_share > 0.60, (
        "the best cell's advantage is no longer concentrated in one day (%.1f%%) -- the "
        "NO EDGE verdict rested on this; re-argue it" % (100 * top_day_share))
    assert cell["lodo_min"][1] < 0.25 * cell["total_delta_net"], (
        "leave-one-day-out no longer guts the effect; re-argue the verdict")
    assert cell["boot_ci95"][0] < 0, "day-bootstrap CI no longer straddles zero; re-argue"


def test_no_cell_worsens_the_rule5_picture_without_being_flagged(robust):
    """Production breaches the per-account daily kill switch on exactly one arm-day.
    A cell that breaches MORE is a sizing change wearing an exit-shape label."""
    assert robust["production_rule5_breach_arm_days"] == 1
    worst = max(c["rule5_breach_arm_days"] for c in robust["cells"])
    assert worst <= 1, (
        "an exit-shape cell now breaches Rule 5 more often than production -- that is no "
        "longer a pure exit-target change and must be re-scoped")
