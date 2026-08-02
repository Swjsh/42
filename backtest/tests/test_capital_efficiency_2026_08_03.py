"""Guards for capital_efficiency_2026_08_03.py (analysis/deep-research/
CAPITAL-EFFICIENCY-2026-08-03.md). MEASUREMENT + ARITHMETIC ONLY -- these tests cover the
NEW pure functions this session wrote (pct-return math, linear qty rescaling, distribution
stats, the capital-curve affordability sweep, frequency arithmetic, recency windowing).
`order_clears_gate` / `capital_curve_row` delegate to the ALREADY-TESTED `risk_gate.py`
(test_risk_gate.py) for the actual cap arithmetic -- these guards prove the DELEGATION is
correct (right equity/premium/qty/params reach risk_gate, inclusion/exclusion + rescaling
follow correctly), not the cap math itself, per this repo's own "reuse, don't re-test
someone else's already-guarded logic" convention (see regime_participation_study's own test
suite for the same pattern with day_report_card.py).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_capital_efficiency_2026_08_03.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
CRYPTO_LIB = REPO / "crypto" / "lib"
SCRIPTS = REPO / "setup" / "scripts"
for _p in (BACKTEST / "tools", BACKTEST, SCRIPTS, FLEET_DIR, CRYPTO_LIB, REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import capital_efficiency_2026_08_03 as ce  # noqa: E402


# --------------------------------------------------------------------------------------
# pct_return_on_capital
# --------------------------------------------------------------------------------------
class TestPctReturnOnCapital:
    def test_basic_return(self):
        # $180.25 pnl on 3 contracts @ $0.57 = $171 capital deployed.
        got = ce.pct_return_on_capital(180.25, 0.57, 3)
        assert got == pytest.approx(180.25 / 171.0)

    def test_none_on_zero_premium(self):
        assert ce.pct_return_on_capital(10.0, 0.0, 3) is None

    def test_none_on_negative_premium(self):
        assert ce.pct_return_on_capital(10.0, -0.5, 3) is None

    def test_none_on_zero_qty(self):
        assert ce.pct_return_on_capital(10.0, 1.0, 0) is None

    def test_none_on_missing_inputs(self):
        assert ce.pct_return_on_capital(10.0, None, 3) is None
        assert ce.pct_return_on_capital(10.0, 1.0, None) is None

    def test_loss_is_negative(self):
        got = ce.pct_return_on_capital(-50.0, 1.0, 3)
        assert got == pytest.approx(-50.0 / 300.0)

    def test_qty_invariance(self):
        """THE load-bearing invariant this whole script relies on: when P&L scales
        linearly with qty (rescale_pnl_linear), pct_return_on_capital is UNCHANGED --
        proving % return is a valid qty-independent edge measure regardless of which
        historical qty a trade happened to use (module docstring FINDING #0)."""
        base_pnl, premium, qty_hist = 90.0, 1.20, 5
        pct_at_hist = ce.pct_return_on_capital(base_pnl, premium, qty_hist)
        for qty_target in (1, 3, 7, 13):
            rescaled = ce.rescale_pnl_linear(base_pnl, qty_hist, qty_target)
            pct_at_target = ce.pct_return_on_capital(rescaled, premium, qty_target)
            assert pct_at_target == pytest.approx(pct_at_hist)


# --------------------------------------------------------------------------------------
# rescale_pnl_linear
# --------------------------------------------------------------------------------------
class TestRescalePnlLinear:
    def test_scale_down(self):
        assert ce.rescale_pnl_linear(300.0, 6, 3) == pytest.approx(150.0)

    def test_scale_up(self):
        assert ce.rescale_pnl_linear(100.0, 3, 6) == pytest.approx(200.0)

    def test_identity_when_same_qty(self):
        assert ce.rescale_pnl_linear(77.5, 3, 3) == pytest.approx(77.5)

    def test_negative_pnl_scales_correctly(self):
        assert ce.rescale_pnl_linear(-90.0, 3, 1) == pytest.approx(-30.0)

    def test_zero_or_none_qty_from_yields_zero(self):
        assert ce.rescale_pnl_linear(100.0, 0, 3) == 0.0
        assert ce.rescale_pnl_linear(100.0, None, 3) == 0.0


# --------------------------------------------------------------------------------------
# percentile / distribution_stats
# --------------------------------------------------------------------------------------
class TestPercentile:
    def test_median_of_five(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert ce.percentile(vals, 50) == pytest.approx(3.0)

    def test_min_and_max(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert ce.percentile(vals, 0) == pytest.approx(1.0)
        assert ce.percentile(vals, 100) == pytest.approx(5.0)

    def test_empty_is_none(self):
        assert ce.percentile([], 50) is None

    def test_single_value(self):
        assert ce.percentile([42.0], 50) == pytest.approx(42.0)

    def test_interpolation(self):
        # p25 of [1,2,3,4] -> rank=0.25*3=0.75 -> 1 + 0.75*(2-1) = 1.75
        assert ce.percentile([1.0, 2.0, 3.0, 4.0], 25) == pytest.approx(1.75)


class TestDistributionStats:
    def test_empty_returns_n_zero_all_none(self):
        out = ce.distribution_stats([])
        assert out["n"] == 0
        assert all(out[k] is None for k in ("mean", "median", "p10", "p25", "p75", "p90", "min", "max"))

    def test_none_values_dropped_not_zeroed(self):
        out = ce.distribution_stats([1.0, None, 3.0, None])
        assert out["n"] == 2
        assert out["mean"] == pytest.approx(2.0)

    def test_basic_stats(self):
        out = ce.distribution_stats([10.0, 20.0, 30.0])
        assert out["n"] == 3
        assert out["mean"] == pytest.approx(20.0)
        assert out["median"] == pytest.approx(20.0)
        assert out["min"] == pytest.approx(10.0)
        assert out["max"] == pytest.approx(30.0)


# --------------------------------------------------------------------------------------
# split_by_outcome
# --------------------------------------------------------------------------------------
class TestSplitByOutcome:
    def test_partitions_correctly(self):
        trades = [{"dollar_pnl": 10.0}, {"dollar_pnl": -5.0}, {"dollar_pnl": 0.0}, {"dollar_pnl": 3.0}]
        winners, losers, flat = ce.split_by_outcome(trades)
        assert len(winners) == 2
        assert len(losers) == 1
        assert len(flat) == 1

    def test_empty_input(self):
        winners, losers, flat = ce.split_by_outcome([])
        assert winners == [] and losers == [] and flat == []


# --------------------------------------------------------------------------------------
# liquidity: qty_fraction_of_bar_volume / liquidity_knee_table
# --------------------------------------------------------------------------------------
class TestLiquidityProxy:
    def test_basic_ratio(self):
        assert ce.qty_fraction_of_bar_volume(3, 100) == pytest.approx(0.03)

    def test_none_on_zero_or_none_volume(self):
        assert ce.qty_fraction_of_bar_volume(3, 0) is None
        assert ce.qty_fraction_of_bar_volume(3, None) is None

    def test_knee_table_thresholds(self):
        # ratios: 0.01, 0.06, 0.30, 0.60 -- exceeds gt_5pct for 3/4, gt_25pct for 2/4
        ratios = [0.01, 0.06, 0.30, 0.60]
        out = ce.liquidity_knee_table(ratios, thresholds=(0.05, 0.25))
        assert out["n_assessable"] == 4
        assert out["by_threshold"]["gt_5pct"] == pytest.approx(75.0)
        assert out["by_threshold"]["gt_25pct"] == pytest.approx(50.0)

    def test_knee_table_empty(self):
        out = ce.liquidity_knee_table([])
        assert out["n_assessable"] == 0
        assert out["by_threshold"] == {}


# --------------------------------------------------------------------------------------
# order_clears_gate / capital_curve_row -- delegation to risk_gate.py
# --------------------------------------------------------------------------------------
def _tiny_params(min_contracts=3, risk_cap_pct=0.30):
    return {
        "min_contracts": min_contracts,
        "per_trade_risk_cap_pct": risk_cap_pct,
        "daily_loss_kill_switch_pct": 0.30,
    }


class TestOrderClearsGate:
    def test_affordable_order_clears(self):
        # equity 2000, cap=600, 3 contracts @ $1.00 = $300 notional -> clears.
        assert ce.order_clears_gate(equity=2000.0, entry_premium=1.00, min_contracts=3,
                                    params=_tiny_params()) is True

    def test_unaffordable_order_denied(self):
        # 3 contracts @ $5.00 = $1500 notional > $600 cap -> denied.
        assert ce.order_clears_gate(equity=2000.0, entry_premium=5.00, min_contracts=3,
                                    params=_tiny_params()) is False

    def test_boundary_exactly_at_cap_clears(self):
        # 3 * 2.00 * 100 = 600 == cap exactly -> notional <= cap -> clears.
        assert ce.order_clears_gate(equity=2000.0, entry_premium=2.00, min_contracts=3,
                                    params=_tiny_params()) is True


class TestCapitalCurveRow:
    def _trades(self):
        return [
            {"date": "2026-01-01", "entry_premium": 1.00, "qty": 3, "dollar_pnl": 60.0},   # affordable, cheap
            {"date": "2026-01-02", "entry_premium": 1.00, "qty": 6, "dollar_pnl": 120.0},  # affordable, historical qty=6
            {"date": "2026-01-02", "entry_premium": 5.00, "qty": 3, "dollar_pnl": -150.0}, # unaffordable at $2000 equity
        ]

    def test_includes_affordable_excludes_deadlocked(self):
        row = ce.capital_curve_row(self._trades(), equity=2000.0, min_contracts=3,
                                   params=_tiny_params())
        assert row["n_total_priced_candidates"] == 3
        assert row["n_included"] == 2
        assert row["n_blocked_deadlock"] == 1

    def test_rescales_historical_qty_to_min_contracts(self):
        # trade 2 had historical qty=6, dollar_pnl=120 -> rescaled to qty=3 => 60.0
        row = ce.capital_curve_row(self._trades(), equity=2000.0, min_contracts=3,
                                   params=_tiny_params())
        # both included trades rescaled to qty=3: 60.0 (already qty3) + 60.0 (rescaled from qty6) = 120.0
        assert row["total_pnl"] == pytest.approx(120.0)
        assert row["avg_pnl_per_trade"] == pytest.approx(60.0)

    def test_higher_equity_unblocks_more_trades(self):
        # at $10,000 equity ($3000 cap under 30%), the $5.00-premium trade now clears.
        row_low = ce.capital_curve_row(self._trades(), equity=2000.0, min_contracts=3,
                                       params=_tiny_params())
        row_high = ce.capital_curve_row(self._trades(), equity=10000.0, min_contracts=3,
                                        params=_tiny_params())
        assert row_high["n_included"] >= row_low["n_included"]
        assert row_high["n_blocked_deadlock"] == 0

    def test_distinct_days_counted_not_trades(self):
        row = ce.capital_curve_row(self._trades(), equity=2000.0, min_contracts=3,
                                   params=_tiny_params())
        # trades 1 (2026-01-01) and 2 (2026-01-02) both included -> 2 distinct days
        assert row["n_distinct_days_included"] == 2

    def test_empty_population(self):
        row = ce.capital_curve_row([], equity=2000.0, min_contracts=3, params=_tiny_params())
        assert row["n_included"] == 0
        assert row["total_pnl"] == 0.0
        assert row["avg_pnl_per_trade"] is None
        assert row["pct_blocked"] is None


# --------------------------------------------------------------------------------------
# trades_per_day_for_target
# --------------------------------------------------------------------------------------
class TestTradesPerDayForTarget:
    def test_basic(self):
        assert ce.trades_per_day_for_target(100.0, 25.0) == pytest.approx(4.0)

    def test_none_on_zero_avg(self):
        assert ce.trades_per_day_for_target(100.0, 0.0) is None

    def test_none_on_negative_avg(self):
        assert ce.trades_per_day_for_target(100.0, -5.0) is None

    def test_none_on_none_avg(self):
        assert ce.trades_per_day_for_target(100.0, None) is None


# --------------------------------------------------------------------------------------
# recent_n_trades -- delegates to regime_participation_study.recent_n_trading_days
# --------------------------------------------------------------------------------------
class TestRecentNTrades:
    def _trades(self):
        return [
            {"date": "2026-01-01", "id": "a"},
            {"date": "2026-01-02", "id": "b"},
            {"date": "2026-01-02", "id": "c"},  # same day, two trades
            {"date": "2026-01-03", "id": "d"},
        ]

    def test_recent_2_days_selects_newest_two_dates(self):
        out = ce.recent_n_trades(self._trades(), 2)
        dates = {t["date"] for t in out}
        assert dates == {"2026-01-02", "2026-01-03"}
        assert len(out) == 3  # two trades on 01-02 + one on 01-03

    def test_n_zero_means_unlimited(self):
        out = ce.recent_n_trades(self._trades(), 0)
        assert len(out) == 4

    def test_n_larger_than_population_returns_everything(self):
        out = ce.recent_n_trades(self._trades(), 999)
        assert len(out) == 4

    def test_empty_population(self):
        assert ce.recent_n_trades([], 25) == []
