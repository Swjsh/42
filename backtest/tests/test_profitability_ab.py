"""Guard for backtest/tools/profitability_ab_2026_08_08.py (Runner execution of
prereg-profitability-2026-08-08.json, BOLD2-QTY-NORMALIZE-V1).

Pins the CELL MATH on synthetic fixtures (no network/live data) so the rescale mechanism
never silently regresses:

  1. A single-leg position (pre-TP1 stop, SELL_ALL) rescales PURELY LINEARLY -- no rounding.
  2. A two-leg position (TP1 partial + runner) rescales via the PRODUCTION
     `tp1_qty = int(target_qty * tp1_qty_fraction)` split -- NOT linearly. This is the entire
     point of this tool over the prereg's own flagged linear-rescale approximation, so a
     regression back to linear-for-everything must fail loudly here.
  3. The real bold-2 population (fills-ledger.jsonl) reproduces the prereg's own frozen
     baseline numbers EXACTLY (-476.00 post-ship, +406.00 pre-ship) -- if fills-ledger.jsonl
     content or reconstruct_positions' grouping ever drifts, this is the tripwire.
  4. G3 (safe-2 untouched) and the mechanical verdict rule (power floor gates SHIP) are pinned.

Run: cd backtest && ../backtest/.venv/Scripts/python.exe -m pytest tests/test_profitability_ab.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "backtest" / "futures"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import profitability_ab_2026_08_08 as pab  # noqa: E402

TP1_FRAC = 0.667  # pin the value observed live -- a params.json drift should be a KNOWN event,
                   # not silently absorbed by this guard (this test hardcodes it deliberately)


def _single_leg_position(entry_price: float, exit_price: float, qty: int = 5) -> dict:
    return {
        "arm": "bold-2", "symbol": "SPY_TEST_SINGLE", "date_et": "2026-07-23",
        "entry_price": entry_price, "entry_qty": qty,
        "exit_fills": [{"ts_utc": "2026-07-23T15:36:00Z", "price": exit_price, "qty": qty}],
        "actual_exit_pnl": round((exit_price - entry_price) * qty * 100, 2),
    }


def _two_leg_position(entry_price: float, tp1_price: float, runner_price: float,
                       qty: int = 5) -> dict:
    tp1_qty = int(qty * TP1_FRAC)
    runner_qty = qty - tp1_qty
    pnl = (tp1_price - entry_price) * tp1_qty * 100 + (runner_price - entry_price) * runner_qty * 100
    return {
        "arm": "bold-2", "symbol": "SPY_TEST_TWOLEG", "date_et": "2026-08-04",
        "entry_price": entry_price, "entry_qty": qty,
        "exit_fills": [
            {"ts_utc": "2026-08-04T14:16:00Z", "price": tp1_price, "qty": tp1_qty},
            {"ts_utc": "2026-08-04T14:21:00Z", "price": runner_price, "qty": runner_qty},
        ],
        "actual_exit_pnl": round(pnl, 2),
    }


def test_single_leg_rescale_is_pure_linear():
    pos = _single_leg_position(entry_price=1.28, exit_price=0.67, qty=5)
    assert pos["actual_exit_pnl"] == -305.00
    # qty=3: (0.67-1.28)*3*100
    assert pab.rescale_position_pnl(pos, 3, TP1_FRAC) == -183.00
    # qty=4: (0.67-1.28)*4*100
    assert pab.rescale_position_pnl(pos, 4, TP1_FRAC) == -244.00
    # qty=5 (identity): must reproduce the real fill exactly
    assert pab.rescale_position_pnl(pos, 5, TP1_FRAC) == pos["actual_exit_pnl"]


def test_two_leg_rescale_uses_production_rounding_not_linear():
    # entry 1.38, tp1 fill 2.68, runner fill 2.50, qty=5 -> tp1_qty=int(5*.667)=3, runner=2
    pos = _two_leg_position(entry_price=1.38, tp1_price=2.68, runner_price=2.50, qty=5)
    assert pos["actual_exit_pnl"] == 614.00  # (2.68-1.38)*3*100 + (2.50-1.38)*2*100

    # qty=3: tp1_qty=int(3*.667)=2, runner_qty=1 -> (1.30)*2*100 + (1.12)*1*100 = 260+112=372.00
    got_q3 = pab.rescale_position_pnl(pos, 3, TP1_FRAC)
    assert got_q3 == 372.00
    # a NAIVE linear rescale (614*3/5=368.40) must NOT equal the production-rounding result --
    # this is the load-bearing difference this tool exists to capture.
    naive_linear_q3 = round(pos["actual_exit_pnl"] * 3 / 5, 2)
    assert naive_linear_q3 == 368.40
    assert got_q3 != naive_linear_q3

    # qty=4: tp1_qty=int(4*.667)=2, runner_qty=2 -> 260 + 224 = 484.00
    got_q4 = pab.rescale_position_pnl(pos, 4, TP1_FRAC)
    assert got_q4 == 484.00


def test_bootstrap_delta_pvalue_all_positive_deltas_is_low():
    p = pab.bootstrap_delta_pvalue([50.0, 60.0, 40.0, 70.0, 55.0, 45.0], B=500, seed=1)
    assert p < 0.05  # every position improved -> resampled means should rarely be <=0


def test_bootstrap_delta_pvalue_empty_is_nan():
    import math
    assert math.isnan(pab.bootstrap_delta_pvalue([]))



# ANCHOR AS-OF DATE (added 2026-08-15). These pins reproduce what
# prereg-profitability-2026-08-08.json independently measured ON 2026-08-08. They pinned the
# WHOLE bold-2 ledger, so every trade the arm has taken since moved them: post_ship had grown
# n=6 -> 20 and -$476.00 -> -$1,338.00, and both tests had been RED (and therefore blind) ever
# since. L292 -- a monitor whose own coverage scope rots exactly like the thing it monitors.
#
# Bounding to the anchor's own window keeps the tripwire doing its ONE job (detect a change in
# fills-ledger parsing or reconstruct_positions' grouping) while ledger GROWTH, which is not a
# defect, stops masquerading as drift.
#
# NOT A PIN, BUT WORTH A HUMAN'S EYE: unbounded, bold-2's post-ship window now reads n=20 /
# -$1,338.00 (was n=6 / -$476.00 on 2026-08-08). That is live arm performance, not a test
# artifact, and it belongs in a P&L review rather than in this tripwire's expectations.
ANCHOR_ASOF_ET = "2026-08-08"


def _asof(positions: list) -> list:
    """Positions on or before the date these anchors were frozen against."""
    return [p for p in positions
            if str(p.get("date_et") or p.get("entry_ts_utc", ""))[:10] <= ANCHOR_ASOF_ET]

def test_real_bold2_population_reproduces_prereg_frozen_baselines():
    """Tripwire: if fills-ledger.jsonl or reconstruct_positions' grouping ever drifts, this
    fails loudly instead of silently shipping a wrong baseline. Pins the EXACT numbers the
    frozen prereg independently measured (population.regime_scope_primary /
    cell_results_computed_this_session in prereg-profitability-2026-08-08.json)."""
    positions = _asof(pab.load_bold2_positions())
    post_ship = pab.scope_positions(positions, "post_ship_only")
    pre_ship = [p for p in positions if p not in post_ship]

    assert len(post_ship) == 6
    assert round(sum(p["actual_exit_pnl"] for p in post_ship), 2) == -476.00

    assert len(pre_ship) == 4
    assert round(sum(p["actual_exit_pnl"] for p in pre_ship), 2) == 406.00


def test_primary_cell_matches_prereg_ratio_within_rounding_tolerance():
    """The prereg's own linear-approximation primary cell (qty3, post_ship_only) is
    delta=+190.40. This tool's rounding-aware recomputation must be CLOSE (same mechanism,
    same sign, same order of magnitude) but is EXPECTED to differ slightly (+194.00, see
    module docstring's TP1-rounding worked example) -- pin the tolerance so a real regression
    (wrong sign, wrong order of magnitude) fails loudly while the known +3.60 rounding
    correction does not."""
    tp1_frac = pab.current_tp1_qty_fraction()
    positions = _asof(pab.load_bold2_positions())
    cell = pab.run_cell(positions, 3, "post_ship_only", tp1_frac)
    assert cell["baseline_net"] == -476.00
    assert cell["delta_net"] > 0
    assert abs(cell["delta_net"] - 190.40) < 10.00  # rounding correction is a few dollars, not a sign flip
    assert cell["gates"]["G1_aggregate_positive_delta"] is True
    assert cell["gates"]["power_floor_n_ge_15"] is False  # n=6 < 15, MUST stay False


def test_g3_safe2_always_zero_bold2_gates_on_its_own_delta_sign():
    """safe-2 is untouched by construction in EVERY cell (bold-2-only rule). G3 also requires
    bold-2's OWN delta to be non-negative (per prereg: 'every touched account's cut must be
    non-negative') -- this correctly FAILS for the diagnostic-only qty4/all_time cell, whose
    delta is negative (-98.00, the real sign-flip this tool found vs the prereg's own linear
    estimate of +14.00 -- see module docstring). A guard that asserted G3=True unconditionally
    would be hiding that finding, not pinning it."""
    tp1_frac = pab.current_tp1_qty_fraction()
    positions = pab.load_bold2_positions()
    for target_qty in (3, 4):
        for scope in ("post_ship_only", "all_time_robustness_diagnostic_only"):
            cell = pab.run_cell(positions, target_qty, scope, tp1_frac)
            assert cell["per_account_cuts"]["safe-2"]["delta"] == 0.0
            expected_g3 = cell["delta_net"] >= 0
            assert cell["gates"]["G3_per_account_non_negative"] is expected_g3

    # both SHIP-ELIGIBLE cells (post_ship_only) must clear G3 -- that's load-bearing for the
    # verdict; only the diagnostic all_time qty4 cell is expected to fail it.
    for target_qty in (3, 4):
        cell = pab.run_cell(positions, target_qty, "post_ship_only", tp1_frac)
        assert cell["gates"]["G3_per_account_non_negative"] is True


def test_verdict_is_mechanical_freeze_with_clock_at_current_n():
    """n_changed=6 < power floor 15 -> verdict MUST be FREEZE-WITH-CLOCK, never SHIP, no
    matter how good the other gates look (mirrors the frozen prereg's own verdict)."""
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = pab.main()
    assert rc == 0
    assert "FREEZE-WITH-CLOCK" in buf.getvalue()
    assert "verdict=SHIP" not in buf.getvalue()
