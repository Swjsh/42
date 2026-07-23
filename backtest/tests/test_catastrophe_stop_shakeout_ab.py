"""Guard for catastrophe_stop_shakeout_ab.py (Q1 forensic, 2026-07-23): candidate-shape
construction (build_shapes isolates ONLY catastrophe_stop_pct), the ship-gate math
(evaluate_gates -- aggregate/majority-of-days/drop-best-1/OOS-last-25%), the
shakeout_descriptive classification logic, and the frozen pre-registration's population
hash. The shared replay core (exit_manager.plan_exit_actions via walk_exit_manager) is
covered elsewhere in this codebase -- this file does not re-test that, only the logic this
module adds on top.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import pandas as pd  # noqa: E402

import catastrophe_stop_shakeout_ab as cs  # noqa: E402


CONTROL_SHAPE = {
    "premium_stop_pct": -0.20, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
    "profit_lock_mode": "trailing", "runner_target_pct": 99.0, "trail_pct": 0.15,
    "profit_lock_arm_pct": 0.05, "stop_mode": "structure", "catastrophe_stop_pct": -0.50,
    "profit_lock_arm_scope": "post_tp1",
}


# ---------------------------------------------------------------------------------------------
# build_shapes -- isolates ONLY catastrophe_stop_pct, every other field byte-identical
# ---------------------------------------------------------------------------------------------
def test_build_shapes_control_passthrough_and_copied():
    shapes = cs.build_shapes(CONTROL_SHAPE)
    assert shapes["CONTROL"] == CONTROL_SHAPE
    assert shapes["CONTROL"] is not CONTROL_SHAPE


def test_build_shapes_wide70_isolates_catastrophe_axis():
    shapes = cs.build_shapes(CONTROL_SHAPE)
    s = shapes["CAND-WIDE70"]
    assert s["catastrophe_stop_pct"] == -0.70
    for k in ("premium_stop_pct", "tp1_premium_pct", "tp1_qty_fraction", "profit_lock_mode",
              "runner_target_pct", "trail_pct", "profit_lock_arm_pct", "stop_mode",
              "profit_lock_arm_scope"):
        assert s[k] == CONTROL_SHAPE[k], f"{k} must stay byte-identical to control"


def test_build_shapes_nocat_isolates_catastrophe_axis():
    shapes = cs.build_shapes(CONTROL_SHAPE)
    s = shapes["CAND-NOCAT"]
    assert s["catastrophe_stop_pct"] == -0.99
    assert s["stop_mode"] == "structure"  # never touches WHETHER structure mode applies


def test_both_candidate_ids_present():
    shapes = cs.build_shapes(CONTROL_SHAPE)
    for cid in cs.CANDIDATE_IDS:
        assert cid in shapes
    assert len(cs.CANDIDATE_IDS) == 2


# ---------------------------------------------------------------------------------------------
# evaluate_gates
# ---------------------------------------------------------------------------------------------
def _row(date, symbol, control_pnl, candidate_pnl):
    return {"date": date, "symbol": symbol, "control_pnl": control_pnl, "candidate_pnl": candidate_pnl}


def test_gate1_fails_when_aggregate_worse():
    rows = [_row("2026-07-01", "A", 10.0, 5.0), _row("2026-07-02", "B", -10.0, -20.0)]
    v = cs.evaluate_gates(rows, oos_dates=set())
    assert v["aggregate_delta"] == -15.0
    assert v["gate1_aggregate_beats_control"] is False
    assert v["overall_ship_decision"] == "CONTROL_HOLDS"


def test_gate2_ties_count_for_control_not_candidate():
    rows = [_row("2026-07-01", "A", 0.0, 10.0), _row("2026-07-02", "B", 5.0, 5.0)]
    v = cs.evaluate_gates(rows, oos_dates=set())
    g2 = v["gate2_majority_of_days"]
    assert g2["candidate_wins_days"] == 1
    assert g2["control_wins_or_ties_days"] == 1
    assert g2["result"] is False, "1-vs-1 is not a majority for the candidate"


def test_gate3_drop_best1_removes_exactly_one():
    rows = [_row("2026-07-01", "A", 0.0, 100.0), _row("2026-07-02", "B", 0.0, -5.0),
            _row("2026-07-03", "C", 0.0, -5.0)]
    v = cs.evaluate_gates(rows, oos_dates=set())
    assert v["gate1_aggregate_beats_control"] is True
    g3 = v["gate3_survives_drop_best1"]
    assert g3["delta_ex_best1"] == -10.0
    assert g3["result"] is False


def test_gate4_oos_zero_delta_fails_strictly_not_negative():
    """Real-world case found in the actual 2026-07-23 run: the OOS window can have ZERO
    catastrophe-fire events (delta exactly 0.0) -- must fail the strict >0 gate but the
    caller must be able to tell this apart from a genuinely negative OOS outcome."""
    rows = [_row("2026-07-01", "A", 0.0, 50.0), _row("2026-07-10", "B", 0.0, 0.0)]
    v = cs.evaluate_gates(rows, oos_dates={"2026-07-10"})
    g4 = v["gate4_oos_last25_holds"]
    assert g4["oos_delta"] == 0.0
    assert g4["result"] is False
    assert g4["sign_flip"] is False, "zero is not a sign flip vs a positive IS delta"


def test_gate4_oos_positive_holds():
    rows = [_row("2026-07-01", "A", 0.0, 50.0), _row("2026-07-10", "B", 0.0, 10.0)]
    v = cs.evaluate_gates(rows, oos_dates={"2026-07-10"})
    assert v["gate4_oos_last25_holds"]["result"] is True


def test_give_back_accounting_reconciles_to_aggregate_delta():
    rows = [_row("2026-07-01", "A", 0.0, 30.0), _row("2026-07-02", "B", 0.0, -12.0),
            _row("2026-07-03", "C", 0.0, 7.0)]
    v = cs.evaluate_gates(rows, oos_dates=set())
    g = v["give_back_accounting"]
    assert round(g["net"], 2) == v["aggregate_delta"]
    assert g["extra_captured_on_beats"] == 37.0
    assert g["n_beats"] == 2
    assert g["extra_given_back_on_losses"] == -12.0
    assert g["n_losses"] == 1


def test_all_zero_delta_rows_never_ship():
    """The 124 premium-mode trades this axis can't touch contribute exactly $0 delta each --
    a population of all-zero deltas must never spuriously ship."""
    rows = [_row(f"2026-07-{i:02d}", f"S{i}", 10.0, 10.0) for i in range(1, 5)]
    v = cs.evaluate_gates(rows, oos_dates=set())
    assert v["aggregate_delta"] == 0.0
    assert v["gate1_aggregate_beats_control"] is False
    assert v["overall_ship_decision"] == "CONTROL_HOLDS"


# ---------------------------------------------------------------------------------------------
# shakeout_descriptive -- structure-confirmation + option-recovery classification
# ---------------------------------------------------------------------------------------------
def _mk_spy_day(rows):
    df = pd.DataFrame(rows, columns=["timestamp_et", "open", "high", "low", "close"])
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


def test_shakeout_descriptive_no_applicable_when_not_resolved():
    trade = {"symbol": "SPY260101P00600000", "side": "P", "trigger_level": 600.0,
              "entry_premium": 1.0}
    ctl_res = {"exit_time_et": None, "exit_reason": "data_exhausted_force_close"}
    out = cs.shakeout_descriptive(trade, ctl_res, day_spy=_mk_spy_day([]))
    assert out["applicable"] is False


def test_shakeout_descriptive_structure_never_confirmed(monkeypatch, tmp_path):
    """Structure never closes beyond trigger_level for the rest of the day -> False."""
    trade = {"symbol": "SPY260101P00600000", "side": "P", "trigger_level": 602.0,
              "entry_premium": 1.0}
    ctl_res = {"exit_time_et": "2026-01-01T12:00:00", "exit_reason": "premium_stop @ 0.5"}
    day_spy = _mk_spy_day([
        ("2026-01-01 12:05:00", 599.0, 599.5, 598.5, 599.0),  # closed bar at 12:10, close < 602
        ("2026-01-01 12:10:00", 599.0, 600.0, 598.0, 599.5),
    ])

    def _fake_load(symbol):
        opt = pd.DataFrame({
            "timestamp_et": pd.to_datetime(["2026-01-01 12:05:00", "2026-01-01 12:10:00"]),
            "open": [0.5, 0.4], "high": [0.55, 0.45], "low": [0.45, 0.35], "close": [0.5, 0.4],
        })
        return opt

    monkeypatch.setattr(cs, "load_contract_bars", _fake_load)
    out = cs.shakeout_descriptive(trade, ctl_res, day_spy)
    assert out["applicable"] is True
    assert out["structure_confirmed_by_eod"] is False


def test_shakeout_descriptive_structure_confirmed_later(monkeypatch):
    """SPY closes above trigger_level (602.0) on a bar closing strictly after exit -> True
    (side=P: structure hit when close > trigger_level)."""
    trade = {"symbol": "SPY260101P00600000", "side": "P", "trigger_level": 602.0,
              "entry_premium": 1.0}
    ctl_res = {"exit_time_et": "2026-01-01T12:00:00", "exit_reason": "premium_stop @ 0.5"}
    day_spy = _mk_spy_day([
        ("2026-01-01 12:05:00", 603.0, 603.5, 602.5, 603.0),  # closes at 12:10, close=603 > 602
    ])

    def _fake_load(symbol):
        return pd.DataFrame({
            "timestamp_et": pd.to_datetime(["2026-01-01 12:05:00"]),
            "open": [0.4], "high": [0.42], "low": [0.38], "close": [0.4],
        })

    monkeypatch.setattr(cs, "load_contract_bars", _fake_load)
    out = cs.shakeout_descriptive(trade, ctl_res, day_spy)
    assert out["structure_confirmed_by_eod"] is True


def test_shakeout_descriptive_premium_recovery_and_tp1(monkeypatch):
    trade = {"symbol": "SPY260101P00600000", "side": "P", "trigger_level": None,
              "entry_premium": 1.0}
    ctl_res = {"exit_time_et": "2026-01-01T12:00:00", "exit_reason": "premium_stop @ 0.5"}
    day_spy = _mk_spy_day([("2026-01-01 12:05:00", 599.0, 599.5, 598.5, 599.0)])

    def _fake_load(symbol):
        return pd.DataFrame({
            "timestamp_et": pd.to_datetime(["2026-01-01 12:05:00", "2026-01-01 12:10:00"]),
            "open": [0.6, 2.5], "high": [0.65, 2.6], "low": [0.55, 2.4], "close": [0.6, 2.5],
        })

    monkeypatch.setattr(cs, "load_contract_bars", _fake_load)
    out = cs.shakeout_descriptive(trade, ctl_res, day_spy)
    assert out["exit_fill_price"] == 0.5
    assert out["max_option_premium_after_stop"] == 2.6
    assert out["premium_recovered_past_exit_by_eod"] is True
    assert out["tp1_level"] == 2.0  # entry_premium * 2.0
    assert out["premium_reached_tp1_by_eod"] is True


# ---------------------------------------------------------------------------------------------
# compute_today_counterfactual -- today's actual Bold trade, real 1-min OPRA bars
# ---------------------------------------------------------------------------------------------
def test_today_counterfactual_computed_from_cached_bars():
    if not cs.TODAY_CONTRACT_1MIN_CSV.exists():
        return  # cache populated once this session via tools/_fetch_todays_bold_735p_2026_07_23.py
    tc = cs.compute_today_counterfactual()
    assert tc is not None
    assert tc["actual_realized_pnl"] == -305.0, "must reproduce the real fills-ledger.jsonl P&L"
    # every counterfactual (best-case-after-stop, held-to-time-stop, held-to-EOD) must be
    # computed, never silently None, once the cache exists
    assert tc["best_case_counterfactual_pnl_if_sold_at_max_favorable"] is not None
    assert tc["held_to_time_stop_counterfactual_pnl"] is not None
    assert tc["held_to_eod_counterfactual_pnl"] is not None
    # the actual finding: holding longer was WORSE, not better, than the real stop-out
    assert tc["held_to_time_stop_counterfactual_pnl"] < tc["actual_realized_pnl"]
    assert tc["held_to_eod_counterfactual_pnl"] < tc["actual_realized_pnl"]


def test_today_counterfactual_none_when_cache_absent(monkeypatch, tmp_path):
    fake_path = tmp_path / "does_not_exist.csv"
    monkeypatch.setattr(cs, "TODAY_CONTRACT_1MIN_CSV", fake_path)
    assert cs.compute_today_counterfactual() is None


# ---------------------------------------------------------------------------------------------
# LIVE-VALUE GUARDS -- this study's "control" assumption depends on these staying put
# ---------------------------------------------------------------------------------------------
def test_live_catastrophe_stop_pct_is_still_the_control_baseline():
    """If this ever drifts, every 'CONTROL' number in the shipped scorecard is stale --
    RED here, not a silent divergence."""
    sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
    import strategies as fleet_strategies
    shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    assert shape["catastrophe_stop_pct"] == -0.50
    assert shape["stop_mode"] == "structure"


def test_time_stop_et_matches_baseline_population_convention():
    """Regression guard for the exact bug this study's own build caught: this module's
    TIME_STOP_ET must be 15:40 (matching engine-fullhist-replay-2026-07-23.json's baseline
    and live params.json time_stop_et), NEVER exit_manager.py's own 15:50 default."""
    assert cs.TIME_STOP_ET == dt.time(15, 40)


# ---------------------------------------------------------------------------------------------
# FROZEN pre-registration -- population hash must still match what's on disk
# ---------------------------------------------------------------------------------------------
def test_prereg_file_exists_and_pins_expected_shape():
    prereg_path = REPO / "analysis" / "recommendations" / "catastrophe-stop-shakeout-prereg-2026-07-23.json"
    assert prereg_path.exists()
    preg = json.loads(prereg_path.read_text(encoding="utf-8"))
    assert preg["version"] == 1
    assert set(preg["candidates"]) == set(cs.CANDIDATE_IDS)
    assert preg["population"]["n_bear_trades_total"] == 151
    assert preg["population"]["n_structure_mode_recoverable_trigger_level"] == 27


def test_real_run_output_matches_disclosed_verdict_shape():
    out_path = REPO / "analysis" / "recommendations" / "catastrophe-stop-shakeout-2026-07-23.json"
    if not out_path.exists():
        return
    d = json.loads(out_path.read_text(encoding="utf-8"))
    assert d["sanity_mismatches_vs_baseline"] == [], (
        "control re-walk must reproduce the baseline population's persisted dollar_pnl exactly "
        "(within the $0.02 tolerance) -- any mismatch means this study's TIME_STOP_ET/shape "
        "drifted from the baseline it claims to extend")
    for cid, v in d["verdicts"].items():
        assert v["overall_ship_decision"] in ("SHIP", "CONTROL_HOLDS")
        g = v["give_back_accounting"]
        assert round(g["extra_captured_on_beats"] + g["extra_given_back_on_losses"], 2) == \
            v["aggregate_delta"], f"{cid}: give-back ledger must reconcile to aggregate_delta"
    ds = d["descriptive_shakeout_stat"]
    assert ds["n_premium_stop_fires_under_control"] == len(ds["detail"])
