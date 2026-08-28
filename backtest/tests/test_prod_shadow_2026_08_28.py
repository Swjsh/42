"""Guard tests for setup/scripts/prod_shadow.py (TASK C1 PROD-1 SHADOW, built 2026-08-28).

Pins the three properties the task explicitly required: (1) cost application is non-zero
for an executed trade, (2) the daily stop actually binds (synthetic case -- the real safe-2
ledger never breaches the default 6% daily stop at 2% per-trade sizing, so this must be
exercised with a constructed fixture, not the live data), (3) the shadow ledger reconciles
1:1 to its source trades (every source signal produces exactly one ledger row, in order,
whether executed or skipped).
"""
from __future__ import annotations

import importlib.util
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _load(name, rel_path):
    path = os.path.join(ROOT, *rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ps = _load("prod_shadow", ("setup", "scripts", "prod_shadow.py"))

RATES = {
    "commission_per_contract": 0.0,
    "occ_fee_per_contract_both_sides": 0.025,
    "orf_fee_per_contract_both_sides": 0.015,
    "taf_fee_per_contract_sells_only": 0.00329,
    "sec_fee_rate_per_dollar_sells_only": 2.06e-05,
    "cat_fee_per_arm_day": 0.01,
    "exit_spread_adjustment_conservative_per_contract": 0.02,
}


def _trade(date, symbol, entry_ts, entry_px, ret_pct, right="C", setup="TEST",
           exit_reason="tp1", arm="safe-2", qty=3.0):
    return {
        "date": date, "symbol": symbol, "right": right, "setup": setup,
        "exit_reason": exit_reason, "entry_ts_et": entry_ts,
        "exit_ts_et": entry_ts.replace("T09", "T10"), "arm": arm, "qty": qty,
        "entry_px": entry_px, "ret_pct_of_premium": ret_pct,
        "pnl_dollars": qty * 100 * entry_px * (ret_pct / 100.0),
    }


# --------------------------------------------------------------------------- #
# (1) Cost application is non-zero
# --------------------------------------------------------------------------- #

def test_costs_nonzero_for_executed_trade():
    costs = ps.compute_costs(qty=3, entry_px=1.00, ret_pct_of_premium=-20.0, rates=RATES)
    assert costs["fee_total_ex_cat"] > 0.0
    assert costs["slippage_dollars"] > 0.0
    # slippage is exactly qty * rate * 100 (dollar impact per contract, see module docstring)
    assert costs["slippage_dollars"] == pytest.approx(3 * 0.02 * 100, abs=1e-6)


def test_costs_zero_when_qty_zero():
    costs = ps.compute_costs(qty=0, entry_px=1.00, ret_pct_of_premium=-20.0, rates=RATES)
    assert costs["fee_total_ex_cat"] == 0.0
    assert costs["slippage_dollars"] == 0.0


def test_simulate_applies_nonzero_costs_end_to_end():
    trades = [_trade("2026-09-01", "SPY260901C00700000", "2026-09-01T09:35:00", 0.50, 10.0)]
    ledger, daily = ps.simulate(trades, RATES, starting_equity=5000.0, risk_fraction=0.02,
                                 max_contracts=20, daily_stop_pct=0.06)
    row = ledger[0]
    assert row["status"] == "executed"
    total_fees = row["fees"]["fee_total_ex_cat"] + row["fees"]["slippage_dollars"]
    assert total_fees > 0.0
    # pnl_net must be strictly less than pnl_gross once costs are subtracted
    assert row["pnl_net"] < row["pnl_gross"]
    # the CAT fee (once per arm-day with activity) is reflected in day_pnl_net vs the sum
    # of trade-level pnl_net for that day
    day = daily["2026-09-01"]
    assert day["day_pnl_net"] == pytest.approx(row["pnl_net"] - RATES["cat_fee_per_arm_day"], abs=1e-6)


# --------------------------------------------------------------------------- #
# (2) The daily stop actually binds
# --------------------------------------------------------------------------- #

def test_daily_stop_actually_binds():
    """Six same-day trades, each losing 90% of a cheap ($0.20) position (chosen so
    max_afford stays >=4 contracts throughout -- entry_px=1.00 would hit
    skipped_insufficient_capital first, which is a DIFFERENT mechanism and must not be
    confused with the daily stop in this test). The 4th trade's cumulative loss must push
    day P&L past the 6% daily-stop threshold, so the 5th and 6th signals are skipped."""
    trades = [
        _trade("2026-09-02", f"SPY260902C0070{i}000", f"2026-09-02T09:{30+i}:00", 0.20, -90.0)
        for i in range(6)
    ]
    ledger, daily = ps.simulate(trades, RATES, starting_equity=5000.0, risk_fraction=0.02,
                                 max_contracts=20, daily_stop_pct=0.06)
    statuses = [r["status"] for r in ledger]
    assert "skipped_daily_stop" in statuses, f"daily stop never bound: {statuses}"
    # once tripped, stays tripped for the rest of the day (no re-arm mid-day)
    first_stop_idx = statuses.index("skipped_daily_stop")
    assert all(s == "skipped_daily_stop" for s in statuses[first_stop_idx:])
    assert daily["2026-09-02"]["daily_stop_triggered"] is True
    assert daily["2026-09-02"]["day_pnl_net"] <= -0.06 * 5000.0 * 0.999  # small fp slack


def test_daily_stop_does_not_bind_on_winning_day():
    trades = [
        _trade("2026-09-03", f"SPY260903C0070{i}000", f"2026-09-03T09:{30+i}:00", 1.00, 20.0)
        for i in range(5)
    ]
    ledger, daily = ps.simulate(trades, RATES, starting_equity=5000.0, risk_fraction=0.02,
                                 max_contracts=20, daily_stop_pct=0.06)
    assert daily["2026-09-03"]["daily_stop_triggered"] is False
    assert all(r["status"] != "skipped_daily_stop" for r in ledger)


# --------------------------------------------------------------------------- #
# (3) Ledger reconciles to source trades
# --------------------------------------------------------------------------- #

def test_ledger_reconciles_one_row_per_source_signal():
    trades = [
        _trade("2026-09-04", "SPY260904C00700000", "2026-09-04T09:30:00", 0.50, 10.0),
        _trade("2026-09-04", "SPY260904C00701000", "2026-09-04T10:00:00", 5.00, -20.0),  # unaffordable at 2%/$5K
        _trade("2026-09-05", "SPY260905P00699000", "2026-09-05T09:30:00", 0.30, -15.0),
    ]
    ledger, daily = ps.simulate(trades, RATES, starting_equity=5000.0, risk_fraction=0.02,
                                 max_contracts=20, daily_stop_pct=0.06)
    assert len(ledger) == len(trades)
    assert [r["symbol"] for r in ledger] == [t["symbol"] for t in trades]
    assert [r["date"] for r in ledger] == [t["date"] for t in trades]
    # the $5.00-premium signal must be unaffordable at 2% of $5,000 ($100 risk budget)
    assert ledger[1]["status"] == "skipped_insufficient_capital"
    assert set(daily.keys()) == {"2026-09-04", "2026-09-05"}


def test_ledger_reconciles_missing_data_never_dropped():
    trades = [_trade("2026-09-06", "SPY260906C00700000", "2026-09-06T09:30:00", 0.50, 10.0)]
    trades[0]["ret_pct_of_premium"] = None  # simulate a data gap
    ledger, _ = ps.simulate(trades, RATES, starting_equity=5000.0)
    assert len(ledger) == 1
    assert ledger[0]["status"] == "skipped_missing_data"


# --------------------------------------------------------------------------- #
# Sizing unit tests
# --------------------------------------------------------------------------- #

def test_size_position_caps_at_max_contracts():
    qty, risk_dollars = ps.size_position(equity=1_000_000.0, risk_fraction=0.02,
                                          entry_px=0.05, max_contracts=20)
    assert qty == 20  # would otherwise be huge (risk_dollars/5 = 4000) -- capped
    assert risk_dollars == pytest.approx(20000.0)


def test_size_position_zero_when_unaffordable():
    qty, _ = ps.size_position(equity=5000.0, risk_fraction=0.02, entry_px=3.00, max_contracts=20)
    assert qty == 0  # $100 risk budget cannot buy a single $300 contract


def test_size_position_handles_none_entry_px():
    qty, risk_dollars = ps.size_position(equity=5000.0, risk_fraction=0.02, entry_px=None,
                                          max_contracts=20)
    assert qty == 0
    assert risk_dollars == 0.0
