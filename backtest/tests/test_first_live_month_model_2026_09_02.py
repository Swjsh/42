"""Guards for setup/scripts/first_live_month_model.py.

The model produces DOLLAR figures that land in the live-flip runbook, and a dollar figure
invites more trust than a ratio does. So the properties pinned here are the ones that would
make it quietly wrong rather than obviously broken: that max drawdown is measured along an
ORDERED path (it is a path statistic -- resampling an unordered multiset would understate
it), that the -$400 cap is a floor and never an ADD, and that the percentile helper does not
silently index off the end.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "setup" / "scripts" / "first_live_month_model.py"

_spec = importlib.util.spec_from_file_location("first_live_month_model_g", MODULE)
assert _spec and _spec.loader
flm = importlib.util.module_from_spec(_spec)
sys.modules["first_live_month_model_g"] = flm
_spec.loader.exec_module(flm)


# ---------------------------------------------------------------------------------------
# max_drawdown is a PATH statistic -- the whole reason the resample is ordered.
# ---------------------------------------------------------------------------------------

def test_drawdown_is_zero_when_only_gains():
    assert flm.max_drawdown([10.0, 20.0, 5.0]) == 0.0


def test_drawdown_measures_peak_to_trough_not_the_total():
    """+100 then -60 ends at +40 -- a total-only view would report no drawdown at all."""
    assert flm.max_drawdown([100.0, -60.0]) == -60.0


def test_order_changes_the_drawdown_but_not_the_total():
    """THE property that justifies an ordered resample. Same days, same sum, different depth."""
    a = [-100.0, -100.0, 300.0]
    b = [300.0, -100.0, -100.0]
    assert sum(a) == sum(b)
    assert flm.max_drawdown(a) == -200.0
    assert flm.max_drawdown(b) == -200.0   # trough measured from the running peak
    c = [-50.0, 300.0, -100.0, -100.0]
    assert flm.max_drawdown(c) == -200.0
    assert flm.max_drawdown([300.0, -50.0, -100.0, -100.0]) == -250.0


def test_drawdown_never_positive():
    for path in ([1.0], [-1.0], [5.0, -1.0, 5.0], []):
        assert flm.max_drawdown(path) <= 0.0


# ---------------------------------------------------------------------------------------
# The daily cap is a FLOOR. A cap that could raise a day would manufacture edge.
# ---------------------------------------------------------------------------------------

def _rows(*pairs, arm="x"):
    return [{"arm": arm, "date": d, "qty": 0, "exit_px_avg": 0.0, "pnl_dollars": v}
            for d, v in pairs]


def test_cap_floors_a_bad_day_and_leaves_others_alone():
    rows = _rows(("2026-01-02", -1000.0), ("2026-01-05", 250.0))
    capped = flm.daily_pnl(rows, "x", slip_cents=0.0, apply_cap=True)
    assert capped["2026-01-02"] == pytest.approx(flm.DAILY_LOSS_CAP, abs=0.05)
    assert capped["2026-01-05"] > 0


def test_cap_never_improves_a_day_that_was_already_within_it():
    rows = _rows(("2026-01-02", -100.0), ("2026-01-05", 900.0))
    un = flm.daily_pnl(rows, "x", slip_cents=0.0, apply_cap=False)
    cap = flm.daily_pnl(rows, "x", slip_cents=0.0, apply_cap=True)
    for d in un:
        assert cap[d] == pytest.approx(un[d], abs=1e-9), "the cap raised a day it should not touch"


def test_capped_total_is_never_worse_than_uncapped():
    rows = _rows(("2026-01-02", -1000.0), ("2026-01-05", -50.0), ("2026-01-06", 300.0))
    un = sum(flm.daily_pnl(rows, "x", slip_cents=0.0).values())
    cap = sum(flm.daily_pnl(rows, "x", slip_cents=0.0, apply_cap=True).values())
    assert cap >= un


def test_costs_only_ever_reduce_a_day():
    """Fees and slippage are subtractions. A sign error here would invent profit."""
    rows = _rows(("2026-01-02", 100.0))
    rows[0].update(qty=3, exit_px_avg=1.50)
    free = flm.daily_pnl(rows, "x", slip_cents=0.0)["2026-01-02"]
    slipped = flm.daily_pnl(rows, "x", slip_cents=5.0)["2026-01-02"]
    assert slipped < free < 100.0


# ---------------------------------------------------------------------------------------
# Bootstrap shape.
# ---------------------------------------------------------------------------------------

def test_bootstrap_returns_none_on_no_days():
    assert flm.bootstrap_month([]) is None


def test_bootstrap_is_deterministic_for_a_seed():
    days = [10.0, -5.0, 3.0, -20.0, 7.0]
    a = flm.bootstrap_month(days, n_boot=500, seed=7)
    b = flm.bootstrap_month(days, n_boot=500, seed=7)
    assert a == b


def test_all_losing_days_give_p_month_negative_one():
    res = flm.bootstrap_month([-10.0, -20.0, -5.0], n_boot=500, seed=1)
    assert res["P(month<0)"] == 1.0
    assert res["month_p5"] < 0
    assert res["maxDD_p95"] < 0


def test_all_winning_days_give_p_month_negative_zero_and_no_drawdown():
    res = flm.bootstrap_month([10.0, 20.0], n_boot=500, seed=1)
    assert res["P(month<0)"] == 0.0
    assert res["maxDD_worst"] == 0.0


def test_percentiles_do_not_index_off_the_end():
    """A single distinct day value still has to produce every percentile."""
    res = flm.bootstrap_month([5.0], n_boot=50, seed=1)
    for k in ("month_p5", "month_median", "month_p95", "maxDD_p50", "maxDD_p95"):
        assert isinstance(res[k], float)


def test_month_is_twenty_trading_days():
    assert flm.TRADING_DAYS_PER_MONTH == 20
    res = flm.bootstrap_month([1.0], n_boot=10, seed=1)
    assert res["month_median"] == pytest.approx(20.0)


def test_report_carries_its_limits():
    """The tails are lower bounds on a calm-regime history. A report that dropped that
    caveat would read as a forecast."""
    rep = flm.build("safe-3")
    assert rep["limits"]
    joined = " ".join(rep["limits"]).lower()
    assert "calm-regime" in joined and "lower bound" in joined


def test_unknown_arm_reports_an_error_not_a_zero():
    """A silent empty result would render as 'no risk'."""
    rep = flm.build("no-such-arm")
    for s in rep["scenarios"].values():
        assert "error" in s
