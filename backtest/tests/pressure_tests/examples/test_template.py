"""Template pressure test — copy this for each new R-NNNN fingerprint.

Replace R0000 with the actual R-NNNN id from weekly-review Section 3.5.
The numbering is sequential within `analysis/recommendations/r_ids.jsonl`.

Workflow:
    1. Copy to pending/test_R{NNNN}.py
    2. Fill in window_start/window_end from the loss-walk markdown
    3. Fill in expected_loss_pnl_dollars (the actual loss to reproduce)
    4. Run RED: pytest pending/test_R{NNNN}.py::test_red_loss_reproduces
       (should PASS — confirming the loss reproduces under v14)
    5. Implement the candidate filter in lib/filters.py
    6. Run GREEN: pytest pending/test_R{NNNN}.py::test_green_filter_blocks_loss
       (should PASS — filter blocks the trade)
    7. Run regression: pytest pending/test_R{NNNN}.py::test_regression_no_pnl_loss
       (must PASS — full validate window doesn't regress > 5%)
    8. Move file to ratified/, ratify v{NNN.M} per pressure_tests/README.md
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

# Make backtest/ importable.
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backtest"))

from autoresearch import runner  # noqa: E402

# ---------------------------------------------------------------------------
# Constants for this R-NNNN -- EDIT THESE
# ---------------------------------------------------------------------------
R_ID = "R0000"
WINDOW_START = "2026-04-15 09:30"
WINDOW_END = "2026-04-15 16:00"
EXPECTED_LOSS_PNL_DOLLARS = -150.0  # The loss to reproduce (negative)
SETUP_NAME = "BEARISH_REJECTION_RIDE_THE_RIBBON"
LOSS_DESCRIPTION = "Post-event chop entry that stopped within 15 min"

# Validate window for the regression check (matches autoresearch defaults).
VALIDATE_START = dt.date(2026, 2, 14)
VALIDATE_END = dt.date(2026, 5, 7)
PNL_REGRESSION_TOLERANCE = 0.05  # 5%
NTRADES_REGRESSION_TOLERANCE = 0.25  # 25%
SHARPE_REGRESSION_TOLERANCE = 0.30  # absolute Sharpe drop


@pytest.mark.pressure
@pytest.mark.r_id(R_ID)
def test_red_loss_reproduces(bars_at_window, production_v14_params):
    """RED phase: confirm the loss reproduces under production v14.

    If this FAILS (loss does NOT reproduce), the fingerprint is wrong. Revisit
    journal/losses/{date}-{HHMM}-{setup}.md and recompute the bar window.
    """
    spy, vix = bars_at_window(WINDOW_START, WINDOW_END)
    start_d = pd.Timestamp(WINDOW_START).date()
    end_d = pd.Timestamp(WINDOW_END).date()

    result, metrics = runner.run_with_params(production_v14_params, start_d, end_d, spy, vix)

    # Loss must show up in the trade list (not just be in metrics aggregate).
    matching_losses = [
        t for t in result.trades
        if t.setup == SETUP_NAME and t.pnl_dollars < 0
    ]
    assert len(matching_losses) >= 1, (
        f"RED FAILED: expected to reproduce a {SETUP_NAME} loss in window "
        f"{WINDOW_START} to {WINDOW_END}, got {len(matching_losses)}. "
        f"Either the fingerprint is wrong or the engine no longer produces this loss."
    )


@pytest.mark.pressure
@pytest.mark.r_id(R_ID)
def test_green_filter_blocks_loss(bars_at_window, production_v14_params, fresh_filters_module):
    """GREEN phase: with the candidate filter active, the loss is blocked.

    Implement the filter in lib/filters.py BEFORE running this. The filter
    must be wired into the appropriate filter-family check (entry-bull, entry-bear,
    or exit gate).
    """
    spy, vix = bars_at_window(WINDOW_START, WINDOW_END)
    start_d = pd.Timestamp(WINDOW_START).date()
    end_d = pd.Timestamp(WINDOW_END).date()

    # Apply candidate filter via params override -- example: vix-spread filter
    # candidate_params = dict(production_v14_params)
    # candidate_params["vix_spread_max_cents"] = 40  # NEW filter knob
    candidate_params = dict(production_v14_params)
    # TODO: set the candidate filter knob(s) here

    result, metrics = runner.run_with_params(candidate_params, start_d, end_d, spy, vix)

    matching_losses = [
        t for t in result.trades
        if t.setup == SETUP_NAME and t.pnl_dollars < 0
    ]
    assert len(matching_losses) == 0, (
        f"GREEN FAILED: filter did not block the {SETUP_NAME} loss in window "
        f"{WINDOW_START} to {WINDOW_END}. Filter logic incorrect or scope too narrow."
    )


@pytest.mark.pressure
@pytest.mark.r_id(R_ID)
@pytest.mark.slow
def test_regression_no_pnl_loss(spy_vix_bars, production_v14_params, fresh_filters_module):
    """REGRESSION phase: full validate window backtest, with vs without filter.

    With the filter active, net P&L must not regress more than PNL_REGRESSION_TOLERANCE,
    n_trades must not drop more than NTRADES_REGRESSION_TOLERANCE, and Sharpe must not
    drop more than SHARPE_REGRESSION_TOLERANCE.

    If ANY of these fail: the filter is over-fitted to one loss; abandon or rescope.
    """
    spy, vix = spy_vix_bars

    _, baseline = runner.run_with_params(
        production_v14_params, VALIDATE_START, VALIDATE_END, spy, vix
    )

    candidate_params = dict(production_v14_params)
    # TODO: same override as test_green_filter_blocks_loss
    _, with_filter = runner.run_with_params(
        candidate_params, VALIDATE_START, VALIDATE_END, spy, vix
    )

    pnl_loss = (baseline.total_pnl - with_filter.total_pnl) / max(abs(baseline.total_pnl), 1e-6)
    ntrades_loss = (baseline.n_trades - with_filter.n_trades) / max(baseline.n_trades, 1)
    sharpe_drop = baseline.sharpe_daily - with_filter.sharpe_daily

    assert pnl_loss <= PNL_REGRESSION_TOLERANCE, (
        f"PNL regressed {pnl_loss:.1%} > tolerance {PNL_REGRESSION_TOLERANCE:.1%}"
    )
    assert ntrades_loss <= NTRADES_REGRESSION_TOLERANCE, (
        f"n_trades regressed {ntrades_loss:.1%} > tolerance {NTRADES_REGRESSION_TOLERANCE:.1%}"
    )
    assert sharpe_drop <= SHARPE_REGRESSION_TOLERANCE, (
        f"Sharpe dropped {sharpe_drop:.2f} > tolerance {SHARPE_REGRESSION_TOLERANCE:.2f}"
    )


# Required for the pytest fixtures above.
import pandas as pd  # noqa: E402
