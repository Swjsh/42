"""Pure-logic guard for t4_exit_matrix.battery (T4). No backtest/network. Locks the WF divide-by-
near-zero guard, drop-top-3, and the downside (maxDD / worst-decile) math against silent regression."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
import t4_exit_matrix as t4  # noqa: E402


def _t(date, pnl, direction="bear"):
    return {"date": date, "direction": direction, "band": "<0.20", "pnl": pnl, "stopped": False}


def test_wf_none_when_is_mean_nonpositive():
    """The control-WF artifact: IS mean <= 0 must yield wf=None (not a blown-up -53), and fail gate."""
    trades = [_t(dt.date(2025, 6, 1), -100), _t(dt.date(2025, 6, 2), 50),   # IS mean = -25
              _t(dt.date(2026, 3, 1), 80)]                                    # OOS positive
    b = t4.battery(trades)
    assert b["wf"] is None and b["wf_ge_070"] is False


def test_wf_valid_when_is_positive():
    trades = [_t(dt.date(2025, 6, 1), 100), _t(dt.date(2026, 3, 1), 90)]   # IS mean 100, OOS 90
    b = t4.battery(trades)
    assert b["wf"] == 0.9 and b["wf_ge_070"] is True


def test_drop_top3_removes_biggest_winners():
    trades = [_t(dt.date(2025, 1, i + 1), p) for i, p in enumerate([1000, 900, 800, 10, -20, -30])]
    b = t4.battery(trades)
    # remaining after dropping top 3 (1000,900,800): [10,-20,-30] mean = -13.33
    assert abs(b["exp_drop_top3"] - round((10 - 20 - 30) / 3, 2)) < 1e-6


def test_downside_metrics():
    trades = [_t(dt.date(2025, 1, i + 1), p) for i, p in enumerate([100, -500, 200, -50, 300, -900, 40, 60, -20, 10])]
    b = t4.battery(trades)
    assert b["worst_trade"] == -900
    assert b["max_dd"] <= 0                    # a real drawdown occurred
    assert b["worst_decile_mean"] == -900      # n=10 -> worst decile is the single worst trade
