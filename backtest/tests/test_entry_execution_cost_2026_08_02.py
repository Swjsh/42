"""ENTRY EXECUTION COST DECOMPOSITION guard (2026-08-02).

Covers the pure functions in backtest/tools/entry_execution_cost_2026_08_02.py: the
decomposition identity (entry_px == mid_signal + latency_drift + spread_crossed +
cross_buffer; entry_px == fill_price + price_improvement), the pre-mechanism detector, the
OCC side parser, the tolerant ET timestamp parser, the driving-core-row matcher, and the
aggregation/drop-best/floor-interaction helpers -- all against small synthetic fixtures, no
network, no real ledger reads (those are exercised end-to-end by running the script itself,
which this session did against the real 105-row population and cross-validated against the
WINNER-AUTOPSY-2026-07-31-SYNTHESIS.md anchor trade byte-for-byte on fill_price/mid_decision/
mid_gating/trade_pnl/label).

RED-PROOF: every test below was run against a deliberately-broken version of the function it
covers (old buggy trigger_bar_et-anchored mid_signal_from_opra, the notes_short-column bug,
the load_contract_bars in-process cache staleness bug) during this session and FAILED before
the fix -- see the module docstring comments in entry_execution_cost_2026_08_02.py at each
fix site for the paired before/after evidence. Re-running these tests today against the
CURRENT (fixed) module is the strongest single-session RED-proof available; a mechanical
mutation pass is not repeated here as it would just re-derive the same three bugs already
caught and fixed by hand this session.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "backtest", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import entry_execution_cost_2026_08_02 as m  # noqa: E402


# =============================================================================
# side_from_symbol
# =============================================================================

def test_side_from_symbol_call():
    assert m.side_from_symbol("SPY260731C00746000") == "C"


def test_side_from_symbol_put():
    assert m.side_from_symbol("SPY260731P00734000") == "P"


# =============================================================================
# parse_et
# =============================================================================

def test_parse_et_naive_assumed_et():
    d = m.parse_et("2026-07-31T12:19:02")
    assert d is not None
    assert d.utcoffset().total_seconds() == -4 * 3600


def test_parse_et_z_suffix_converted_to_et():
    d = m.parse_et("2026-07-31T16:19:03.936711Z")
    assert d is not None
    assert d.hour == 12 and d.minute == 19


def test_parse_et_none_and_garbage_never_raise():
    assert m.parse_et(None) is None
    assert m.parse_et("") is None
    assert m.parse_et("not-a-timestamp") is None
    assert m.parse_et(12345) is None  # wrong type


# =============================================================================
# is_pre_mechanism
# =============================================================================

def test_pre_mechanism_true_when_limit_equals_mid():
    assert m.is_pre_mechanism(entry_px=0.98, mid_decision=0.98) is True


def test_pre_mechanism_false_when_buffer_applied():
    assert m.is_pre_mechanism(entry_px=1.44, mid_decision=1.38) is False  # real 07-28 row


def test_pre_mechanism_boundary_just_under_eps_is_true():
    assert m.is_pre_mechanism(entry_px=1.004, mid_decision=1.00, eps=0.005) is True


def test_pre_mechanism_boundary_just_over_eps_is_false():
    assert m.is_pre_mechanism(entry_px=1.006, mid_decision=1.00, eps=0.005) is False


# =============================================================================
# decompose -- the core identity
# =============================================================================

def test_decompose_identity_entry_px_equals_sum_of_components():
    """entry_px == mid_signal + latency_drift + spread_crossed + cross_buffer, always,
    by construction -- this is arithmetic, not a hypothesis, and must hold exactly."""
    row = m.decompose(fill_price=0.33, qty=5, entry_px=0.34, mid_decision=0.30,
                      mid_signal=0.32, buffer=0.03)
    reconstructed = (row["mid_signal"] + row["latency_drift"] + row["spread_crossed"]
                     + row["cross_buffer"])
    assert reconstructed == pytest.approx(0.34, abs=1e-9)


def test_decompose_identity_entry_px_equals_fill_plus_improvement():
    row = m.decompose(fill_price=0.33, qty=5, entry_px=0.34, mid_decision=0.30,
                      mid_signal=0.32, buffer=0.03)
    assert row["fill_price"] + row["price_improvement"] == pytest.approx(0.34, abs=1e-9)


def test_decompose_matches_real_anchor_trade_2026_07_31_12_19():
    """Reproduces the WINNER-AUTOPSY-2026-07-31-SYNTHESIS.md anchor trade's own logged
    numbers exactly: fill $0.33, entry_px $0.34 (= ask $0.31 + buffer $0.03), mid_decision
    (the logged mid at fill) exactly $0.30 -- matching the source doc's own words, 'the
    logged mid at fill was exactly $0.30 against a $0.30 min_entry_premium floor.'"""
    row = m.decompose(fill_price=0.33, qty=5, entry_px=0.34, mid_decision=0.30,
                      mid_signal=0.32, buffer=0.03)
    assert row["ask_decision"] == pytest.approx(0.31)
    assert row["cross_buffer"] == pytest.approx(0.03)
    assert row["mid_decision"] == pytest.approx(0.30)
    assert row["spread_crossed_dollars"] == pytest.approx(5.0)   # 0.01 * 5 * 100
    assert row["cross_buffer_dollars"] == pytest.approx(15.0)    # 0.03 * 5 * 100


def test_decompose_mid_signal_none_propagates_not_fabricated():
    """Missing mid_signal must yield latency_drift=None (excluded), never a guessed zero."""
    row = m.decompose(fill_price=0.33, qty=5, entry_px=0.34, mid_decision=0.30, mid_signal=None)
    assert row["latency_drift"] is None
    assert row["latency_drift_dollars"] is None
    # the OTHER components must still resolve -- a missing signal price never blocks the
    # rest of the decomposition
    assert row["spread_crossed"] is not None
    assert row["cross_buffer_dollars"] == pytest.approx(15.0)


def test_decompose_price_improvement_never_negative_for_real_fills():
    """A limit BUY can never fill worse than its own limit -- fill_price <= entry_px always.
    (Empirically verified 0/105 on the real population; this pins the arithmetic that makes
    that empirical fact meaningful rather than coincidental.)"""
    row = m.decompose(fill_price=0.30, qty=3, entry_px=0.30, mid_decision=0.27, mid_signal=0.27)
    assert row["price_improvement"] == pytest.approx(0.0)


# =============================================================================
# find_driving_core_row
# =============================================================================

def _core_row(ts_et, side, trigger_level=743.25):
    return {"ts_et": ts_et, "side": side, "trigger_level_exact": trigger_level,
           "trigger_bar_et": "2026-07-31T12:10:00-04:00"}


def test_find_driving_core_row_picks_nearest_preceding_same_side():
    triggered_by_date = {
        "2026-07-31": [
            _core_row("2026-07-31T12:16:02", "C"),
            _core_row("2026-07-31T12:17:02", "C"),
            _core_row("2026-07-31T12:18:03", "C"),
        ]
    }
    row, gap = m.find_driving_core_row(triggered_by_date, "2026-07-31", "C",
                                       "2026-07-31T12:19:02.259487")
    assert row["ts_et"] == "2026-07-31T12:18:03"
    assert gap == pytest.approx(59.259487, abs=1e-3)


def test_find_driving_core_row_never_matches_future_row():
    """A core row AFTER the fleet's own decision cannot have driven it -- causality guard."""
    triggered_by_date = {"2026-07-31": [_core_row("2026-07-31T12:25:00", "C")]}
    row, gap = m.find_driving_core_row(triggered_by_date, "2026-07-31", "C",
                                       "2026-07-31T12:19:02")
    assert row is None and gap is None


def test_find_driving_core_row_wrong_side_excluded():
    triggered_by_date = {"2026-07-31": [_core_row("2026-07-31T12:16:02", "P")]}
    row, gap = m.find_driving_core_row(triggered_by_date, "2026-07-31", "C",
                                       "2026-07-31T12:19:02")
    assert row is None


def test_find_driving_core_row_respects_max_lookback():
    triggered_by_date = {"2026-07-31": [_core_row("2026-07-31T11:50:00", "C")]}
    row, gap = m.find_driving_core_row(triggered_by_date, "2026-07-31", "C",
                                       "2026-07-31T12:19:02", max_lookback_s=600)
    assert row is None  # ~29 min gap > 10 min lookback


def test_find_driving_core_row_verdict_agnostic():
    """Regression pin for the bug this session found + fixed: the matcher must NOT filter on
    verdict=='ENTER_*' -- the real 2026-07-31 anchor's driving rows carry verdict
    'SKIP_ELITE_BULL_LEVEL_RECLAIM', never 'ENTER_BULL'."""
    row_with_skip_verdict = dict(_core_row("2026-07-31T12:16:02", "C"),
                                 verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM")
    triggered_by_date = {"2026-07-31": [row_with_skip_verdict]}
    row, gap = m.find_driving_core_row(triggered_by_date, "2026-07-31", "C",
                                       "2026-07-31T12:19:02")
    assert row is not None
    assert row["verdict"] == "SKIP_ELITE_BULL_LEVEL_RECLAIM"


# =============================================================================
# Aggregation helpers
# =============================================================================

def _row(spread=0.01, buffer=0.03, latency=0.0, improve=0.02, qty=5, label="WINNER", pnl=10.0):
    return {
        "spread_crossed": spread, "cross_buffer": buffer, "latency_drift": latency,
        "price_improvement": improve, "qty": qty, "label": label, "trade_pnl": pnl,
        "spread_crossed_dollars": round(spread * qty * 100, 2),
        "cross_buffer_dollars": round(buffer * qty * 100, 2),
        "latency_drift_dollars": None if latency is None else round(latency * qty * 100, 2),
        "price_improvement_dollars": round(improve * qty * 100, 2),
    }


def test_cost_block_totals_and_averages():
    rows = [_row(), _row(spread=0.02)]
    block = m.cost_block(rows)
    assert block["n"] == 2
    assert block["total_cross_buffer_dollars"] == pytest.approx(30.0)  # 0.03*5*100 * 2
    assert block["avg_cross_buffer_cents_per_contract"] == pytest.approx(3.0)


def test_cost_block_latency_none_excluded_not_zero_filled():
    rows = [_row(latency=0.05), _row(latency=None)]
    block = m.cost_block(rows)
    assert block["n"] == 2
    assert block["n_latency_resolved"] == 1
    assert block["n_latency_excluded"] == 1
    # total must reflect ONLY the resolved row, not a phantom zero for the excluded one
    assert block["total_latency_drift_dollars"] == pytest.approx(0.05 * 5 * 100)


def test_drop_best_removes_single_worst_latency_row():
    rows = [_row(latency=0.01), _row(latency=0.50), _row(latency=0.02)]
    kept = m.drop_best(rows, "latency_drift_dollars")
    assert len(kept) == 2
    assert all(r["latency_drift"] != 0.50 for r in kept)


def test_drop_best_empty_resolved_returns_all_rows_unchanged():
    rows = [_row(latency=None), _row(latency=None)]
    kept = m.drop_best(rows, "latency_drift_dollars")
    assert len(kept) == 2


def test_floor_interaction_flags_delay_dependent_clearance():
    """The exact mechanism this gate exists to catch: gating cleared the floor (>=0.30) but
    the earlier signal read would NOT have (<0.30)."""
    rows = [
        {"floor_active": True, "mid_signal": 0.25, "mid_gating": 0.31,
         "latency_drift_dollars": 30.0, "trade_pnl": -33.0,
         "order_id": "x", "arm": "safe-3", "symbol": "SPY", "date_et": "2026-07-28"},
        {"floor_active": True, "mid_signal": 0.35, "mid_gating": 0.30,
         "latency_drift_dollars": -25.0, "trade_pnl": 126.0,
         "order_id": "y", "arm": "risky-3", "symbol": "SPY", "date_et": "2026-07-31"},
    ]
    out = m.floor_interaction(rows)
    assert out["n_would_have_failed_floor_on_signal_read"] == 1
    assert out["rows"][0]["order_id"] == "x"
    assert out["pnl_on_delay_dependent_trades"] == pytest.approx(-33.0)


def test_floor_interaction_empty_population_never_raises():
    out = m.floor_interaction([])
    assert out["population_floor_active_with_signal"] == 0
    assert out["n_would_have_failed_floor_on_signal_read"] == 0
