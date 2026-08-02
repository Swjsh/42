"""Guards for backtest/tools/sizing_scaling_decision_2026_08_03.py -- the SIZING-SCALING
decision-package measurement harness. Tests every new PURE function: reached_tp1,
leg_split_row (delegates to the REAL ExitState.from_entry -- cross-checked, not
reimplemented), daily_kill_switch_walk, equity_curve_stats, classify_elite (delegates to
fleet_executor._is_elite), qty_values_needed (delegates to fleet_executor._qty_for). Also
pins the position_sizing_tiers tables read from both live params files (a vary-and-assert
regression pin -- if either tier table is ever edited, this test tells the reader exactly
what changed rather than silently drifting).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "backtest" / "tools"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (TOOLS, REPO / "backtest", FLEET_DIR, REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

import sizing_scaling_decision_2026_08_03 as ssd  # noqa: E402
import fleet_executor as fx  # noqa: E402
import exit_manager as em  # noqa: E402


# =============================================================================================
# reached_tp1
# =============================================================================================

@pytest.mark.parametrize("reason,expected", [
    ("runner_stop @ 1.23", True),
    ("runner_target @ +250%", True),
    ("structure_stop @ 580.51 (runner)", True),
    ("ribbon_flip_back (runner)", True),
    ("time_stop_15:40 (runner)", True),
    ("premium_stop @ 1.02", False),
    ("structure_stop @ 593.38", False),
    ("profit_lock_floor @ 0.95", False),
    ("time_stop_15:40", False),
    ("ribbon_flip_back", False),
    ("", False),
    (None, False),
])
def test_reached_tp1(reason, expected):
    assert ssd.reached_tp1(reason) is expected


def test_reached_tp1_never_false_positive_on_bare_stop_without_runner_marker():
    """A pre-TP1 premium stop must never be misread as post-TP1 just because the word
    'stop' appears in it -- the classifier keys on the SPECIFIC 'runner_stop'/'runner_target'/
    '(runner)' markers, not a bare substring match on 'stop'."""
    assert ssd.reached_tp1("premium_stop @ 1.50") is False


# =============================================================================================
# leg_split_row -- delegates to the REAL ExitState.from_entry (production code, not reimplemented)
# =============================================================================================

def test_leg_split_row_matches_real_exit_state_directly():
    """Cross-check: leg_split_row's output must match calling em.ExitState.from_entry
    directly with the same inputs -- proves the wrapper adds no independent rounding logic."""
    row = ssd.leg_split_row(qty=7, tp1_qty_fraction=0.667)
    direct = em.ExitState.from_entry(
        symbol="X", side="P", entry_premium=1.0, qty=7,
        exit_shape={"tp1_qty_fraction": 0.667, "premium_stop_pct": -0.2,
                   "tp1_premium_pct": 1.0, "profit_lock_mode": "fixed"},
        strategy="ribbon_ride")
    assert row["tp1_qty"] == direct.tp1_qty
    assert row["runner_qty"] == direct.runner_qty
    assert row["tp1_qty"] + row["runner_qty"] == 7


def test_leg_split_row_no_zero_qty_leg_across_the_real_tier_qty_range():
    """Task's explicit ask: verify no zero-qty leg at any tier qty this study actually uses
    (Safe 3/5/8/10/15, Bold 5/8/12/15/20)."""
    for q in (3, 5, 8, 10, 12, 15, 20):
        row = ssd.leg_split_row(q, 0.667)
        assert not row["zero_qty_leg"], f"qty={q} produced a zero-qty leg: {row}"
        assert row["tp1_qty"] >= 1
        assert row["runner_qty"] >= 1


def test_leg_split_row_realized_fraction_bounded_by_nominal_due_to_floor_rounding():
    """int()-floor rounding (ExitState.from_entry's own math: tp1_qty = int(qty*frac)) can
    only round DOWN -- so realized_tp1_fraction must never EXCEED the nominal fraction."""
    for q in (3, 5, 7, 8, 10, 12, 15, 20, 21):
        row = ssd.leg_split_row(q, 0.667)
        assert row["realized_tp1_fraction"] <= 0.667 + 1e-9


def test_leg_split_row_qty_3_frac_667_matches_hand_computed():
    """qty=3, frac=0.667: int(3*0.667)=int(2.001)=2 tp1, 1 runner -- pinned by hand."""
    row = ssd.leg_split_row(3, 0.667)
    assert row["tp1_qty"] == 2
    assert row["runner_qty"] == 1


# =============================================================================================
# daily_kill_switch_walk
# =============================================================================================

def test_kill_switch_walk_no_breach_includes_everything():
    trades = [{"pnl": 10.0}, {"pnl": -5.0}, {"pnl": 3.0}]
    out = ssd.daily_kill_switch_walk(trades, sod_equity=1000.0, kill_pct=0.30)
    assert out["kill_tripped"] is False
    assert out["n_included"] == 3
    assert out["n_excluded"] == 0
    assert out["day_pnl"] == pytest.approx(8.0)


def test_kill_switch_walk_first_trade_breaches_excludes_the_rest():
    """A single catastrophic first trade that alone breaches -30% of $1000 (-$300) must
    still be INCLUDED itself (it already fired before the breach was known) but every
    trade after it this day is excluded."""
    trades = [{"pnl": -400.0}, {"pnl": 50.0}, {"pnl": 20.0}]
    out = ssd.daily_kill_switch_walk(trades, sod_equity=1000.0, kill_pct=0.30)
    assert out["kill_tripped"] is True
    assert out["trip_after_index"] == 0
    assert out["n_included"] == 1
    assert out["n_excluded"] == 2
    assert out["day_pnl"] == pytest.approx(-400.0)


def test_kill_switch_walk_breach_on_second_trade_keeps_first_two_excludes_third():
    trades = [{"pnl": -150.0}, {"pnl": -160.0}, {"pnl": 999.0}]
    out = ssd.daily_kill_switch_walk(trades, sod_equity=1000.0, kill_pct=0.30)
    # cumulative after trade1=-150 (not yet <= -300), after trade2=-310 (<=-300 -> trip)
    assert out["kill_tripped"] is True
    assert out["trip_after_index"] == 1
    assert out["n_included"] == 2
    assert out["n_excluded"] == 1
    assert out["day_pnl"] == pytest.approx(-310.0)


def test_kill_switch_walk_exact_floor_touch_trips():
    """Rule 5 language is 'at or beyond' the floor -- an EXACT touch must trip, not just a
    strict breach past it (mirrors risk_gate.check_order's own <= convention)."""
    trades = [{"pnl": -300.0}, {"pnl": 5.0}]
    out = ssd.daily_kill_switch_walk(trades, sod_equity=1000.0, kill_pct=0.30)
    assert out["kill_tripped"] is True
    assert out["n_included"] == 1


def test_kill_switch_walk_empty_day():
    out = ssd.daily_kill_switch_walk([], sod_equity=1000.0, kill_pct=0.30)
    assert out["kill_tripped"] is False
    assert out["n_included"] == 0
    assert out["day_pnl"] == 0.0


# =============================================================================================
# equity_curve_stats
# =============================================================================================

def test_equity_curve_stats_empty():
    out = ssd.equity_curve_stats({})
    assert out["n_days"] == 0
    assert out["max_drawdown_dollars"] == 0.0
    assert out["worst_single_day_date"] is None


def test_equity_curve_stats_monotonic_up_has_zero_drawdown():
    out = ssd.equity_curve_stats({"2026-01-01": 10.0, "2026-01-02": 20.0, "2026-01-03": 5.0})
    assert out["max_drawdown_dollars"] == 0.0  # never dips below a prior peak
    assert out["final_cumulative_pnl"] == pytest.approx(35.0)


def test_equity_curve_stats_drawdown_peak_to_trough():
    # cum: day1=100 (peak 100), day2=100-150=-50 (dd=150), day3=-50+30=-20 (dd=120, not new max)
    out = ssd.equity_curve_stats({"2026-01-01": 100.0, "2026-01-02": -150.0, "2026-01-03": 30.0})
    assert out["max_drawdown_dollars"] == pytest.approx(150.0)
    assert out["worst_single_day_date"] == "2026-01-02"
    assert out["worst_single_day_pnl"] == pytest.approx(-150.0)
    assert out["final_cumulative_pnl"] == pytest.approx(-20.0)


# =============================================================================================
# classify_elite -- delegates to fleet_executor._is_elite
# =============================================================================================

def test_classify_elite_confluence():
    assert ssd.classify_elite(["confluence", "level_rejection"]) is True


def test_classify_elite_sequence_trigger():
    assert ssd.classify_elite(["sequence_rejection"]) is True


def test_classify_elite_plain_trendline_is_base():
    assert ssd.classify_elite(["trendline_rejection"]) is False


def test_classify_elite_empty():
    assert ssd.classify_elite([]) is False


# =============================================================================================
# qty_values_needed -- delegates to fleet_executor._qty_for; ALSO pins the live tier tables
# =============================================================================================

def test_qty_values_needed_safe_tier_table_pinned():
    safe_params = json.loads((REPO / "automation" / "state" / "params.json")
                             .read_text(encoding="utf-8"))
    tiers = safe_params["position_sizing_tiers"]
    qtys = ssd.qty_values_needed(tiers, min_contracts=3, equity_grid=(2000.0, 5000.0,
                                                                       10000.0, 25000.0))
    # base@[2000,10000)=5, elite@same=8, base@[10000,inf)=10, elite@same=15, plus min=3
    assert qtys == [3, 5, 8, 10, 15]


def test_qty_values_needed_bold_tier_table_pinned():
    bold_params = json.loads((REPO / "automation" / "state" / "aggressive" / "params.json")
                             .read_text(encoding="utf-8"))
    tiers = bold_params["position_sizing_tiers"]
    qtys = ssd.qty_values_needed(tiers, min_contracts=5, equity_grid=(2000.0, 5000.0,
                                                                       10000.0, 25000.0))
    assert qtys == [5, 8, 12, 15, 20]


def test_qty_for_boundary_at_2000_is_inclusive_to_the_upper_tier():
    """CLAUDE.md-load-bearing boundary: at EXACTLY $2,000 equity, Safe's tier lookup must
    already be in the [2000,10000) band (base=5), not the [0,2000) band (base=3) --
    fleet_executor._qty_for uses `lo <= equity < hi`, confirmed here directly against the
    live table."""
    safe_params = json.loads((REPO / "automation" / "state" / "params.json")
                             .read_text(encoding="utf-8"))
    tiers = safe_params["position_sizing_tiers"]
    assert fx._qty_for(tiers, 1999.99, elite=False) == 3
    assert fx._qty_for(tiers, 2000.00, elite=False) == 5


def test_todays_real_balances_all_fall_in_the_unscaled_band():
    """Task-supplied real-balance range ($1,160-$2,122): every point at/under $2,000 must
    resolve to the SAME qty as today's min_contracts (Safe 3, Bold 5) -- pins the
    'the lever does nothing yet' finding structurally, independent of any simulation."""
    safe_params = json.loads((REPO / "automation" / "state" / "params.json")
                             .read_text(encoding="utf-8"))
    bold_params = json.loads((REPO / "automation" / "state" / "aggressive" / "params.json")
                             .read_text(encoding="utf-8"))
    for e in (1160.42, 1746.75, 1999.99):
        assert fx._qty_for(safe_params["position_sizing_tiers"], e, elite=False) == 3
        assert fx._qty_for(safe_params["position_sizing_tiers"], e, elite=True) == 3
    assert fx._qty_for(bold_params["position_sizing_tiers"], 1197.52, elite=False) == 5
    assert fx._qty_for(bold_params["position_sizing_tiers"], 1197.52, elite=True) == 5
    # the $2,122 upper end of the task's stated range IS past the boundary -- must scale:
    assert fx._qty_for(safe_params["position_sizing_tiers"], 2122.0, elite=False) == 5


# =============================================================================================
# capital_curve -- integration-shape test on synthetic records (no real OPRA needed)
# =============================================================================================

def _fake_record(date, entry_time_et, elite, entry_premium, pnl_by_qty):
    return {"account": "safe", "date": date, "entry_time_et": entry_time_et, "side": "P",
            "symbol": "FAKE", "entry_premium": entry_premium, "triggers": [],
            "elite": elite, "pnl_by_qty": pnl_by_qty, "exit_reason_by_qty": {},
            "legs_by_qty": {}}


def test_capital_curve_scaled_arm_uses_tiered_qty_and_baseline_uses_min_contracts():
    tiers = [{"equity_min": 0, "equity_max": 2000, "base_qty": 3, "elite_qty": 3},
             {"equity_min": 2000, "equity_max": 999999999, "base_qty": 5, "elite_qty": 8}]
    params = {"per_trade_risk_cap_pct": 0.30, "min_contracts": 3}
    records = [_fake_record("2026-01-01", "2026-01-01T10:00:00", False, 1.00,
                            {3: 60.0, 5: 100.0})]
    base = ssd.capital_curve(records, account="safe", equity=5000.0, arm="baseline",
                             params=params, tiers=tiers, min_contracts=3, kill_pct=0.30)
    scaled = ssd.capital_curve(records, account="safe", equity=5000.0, arm="scaled",
                               params=params, tiers=tiers, min_contracts=3, kill_pct=0.30)
    assert base["total_pnl"] == pytest.approx(60.0)
    assert scaled["total_pnl"] == pytest.approx(100.0)


def test_capital_curve_denies_when_tiered_qty_breaches_risk_cap():
    """Fleet's real deny-not-shrink behavior: a tiered qty priced too high for the cap
    excludes the trade entirely (never silently downsized)."""
    tiers = [{"equity_min": 0, "equity_max": 999999999, "base_qty": 50, "elite_qty": 50}]
    params = {"per_trade_risk_cap_pct": 0.30, "min_contracts": 3}
    records = [_fake_record("2026-01-01", "2026-01-01T10:00:00", False, 5.00,
                            {3: 60.0, 50: 1000.0})]
    scaled = ssd.capital_curve(records, account="safe", equity=1000.0, arm="scaled",
                               params=params, tiers=tiers, min_contracts=3, kill_pct=0.30)
    # 50 contracts @ $5.00 = $25,000 notional vs cap $300 -- must be denied, not shrunk
    assert scaled["n_denied_risk_cap"] == 1
    assert scaled["n_included_trades"] == 0
    assert scaled["total_pnl"] == 0.0


def test_capital_curve_applies_kill_switch_across_two_same_day_trades():
    tiers = [{"equity_min": 0, "equity_max": 999999999, "base_qty": 3, "elite_qty": 3}]
    params = {"per_trade_risk_cap_pct": 0.99, "min_contracts": 3}
    records = [
        _fake_record("2026-01-01", "2026-01-01T10:00:00", False, 0.50, {3: -400.0}),
        _fake_record("2026-01-01", "2026-01-01T11:00:00", False, 0.50, {3: 999.0}),
    ]
    out = ssd.capital_curve(records, account="safe", equity=1000.0, arm="baseline",
                            params=params, tiers=tiers, min_contracts=3, kill_pct=0.30)
    assert out["n_days_kill_switch_breached"] == 1
    assert out["n_included_trades"] == 1
    assert out["n_excluded_by_kill_switch"] == 1
    assert out["total_pnl"] == pytest.approx(-400.0)
