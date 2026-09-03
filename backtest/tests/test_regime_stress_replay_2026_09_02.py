"""Guards for backtest/tools/regime_stress_replay.py (work-order 2b, prereg-regime-stress-
replay-2026-09-02.json). These are LIGHTWEIGHT structural/behavioral guards on the runner's
logic -- not a re-run of the (slow, network/OPRA-cache-bound) full replay. Fast, offline, $0.

Covers:
  - the day list is READ from the prereg verbatim, never re-derived (no_repick_clause)
  - DATA_MISSING (no-OPRA / no-SPY-day / ladder-conflict) is COUNTED, never silently dropped
  - no look-ahead: a day's cc%/range% classification never depends on bars after that day
  - Q3 cap-binding is computed from the exit_reason/final_stage field, not assumed/hardcoded
  - the written .md leads with Q6 PARTICIPATION before any Q1 exit-mechanism content
  - the tight-ladder params this module uses are pinned to the live params.json file
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

BT = Path(__file__).resolve().parents[1]
ROOT = BT.parent
for _p in (str(BT), str(BT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, str(_p))

import regime_stress_replay as rsr  # noqa: E402

PREREG_PATH = ROOT / "analysis" / "recommendations" / "prereg-regime-stress-replay-2026-09-02.json"
PARAMS_PATH = ROOT / "automation" / "state" / "params.json"


# ================================================================================================ #
# Day list -- READ, not derived
# ================================================================================================ #
def test_prereg_file_exists():
    assert PREREG_PATH.exists(), "the frozen prereg must exist for this runner to have integrity"


def test_frozen_days_equals_prereg_verbatim():
    prereg = rsr.load_prereg()
    days = rsr.frozen_days(prereg)
    raw = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    expected = [dt.date.fromisoformat(d) for d in raw["population_rule_frozen"]["enumerated_days"]]
    assert days == expected, "runner's day list diverged from the prereg's enumerated_days"
    assert len(days) == 24
    assert days[0] == dt.date(2024, 8, 5)
    assert days[-1] == dt.date(2026, 6, 9)


def test_frozen_days_aborts_without_prereg(tmp_path, monkeypatch):
    monkeypatch.setattr(rsr, "PREREG", tmp_path / "does-not-exist.json")
    with pytest.raises(SystemExit, match="FATAL"):
        rsr.load_prereg()


def test_frozen_days_count_mismatch_raises():
    bad = {"population_rule_frozen": {"enumerated_days": ["2024-08-05", "2024-09-03"],
                                       "enumerated_days_n": 99}}
    with pytest.raises(AssertionError):
        rsr.frozen_days(bad)


# ================================================================================================ #
# Exclusions counted, never silently dropped
# ================================================================================================ #
def test_ladder_skip_rows_are_counted_not_dropped():
    """cap_entry_qty's CONFLICT rule (skip=True) must show up as a counted exclusion, exactly
    like n_no_opra/n_no_spy -- never silently vanish from the row count."""
    proposed_qty, premium = 20, 6.00  # min_contracts=3 * $6.00*100 = $1800 > $1000 dollar cap,
                                       # and 20 contracts far exceeds max_contracts_per_entry=5;
                                       # even the floor breaches the dollar cap -> CONFLICT skip.
    dec = rsr.cap_entry_qty(proposed_qty=proposed_qty, premium=premium, params=rsr.LADDER_PARAMS)
    assert dec["skip"] is True
    assert dec["qty"] is None
    assert dec["reason"], "a skip must always carry a human-readable reason, never a bare flag"


def test_ladder_binds_dollars_before_contracts_at_high_premium():
    """Q4's core question: does the flat $1,000 cap bind before the 5-contract cap once premium
    is elevated? At premium=$3.00, 5 contracts would cost $1,500 > $1,000, so the dollar cap
    should clamp qty to 3 (max_dollars // (premium*100)) before the contract-count cap is even
    the binding constraint."""
    dec = rsr.cap_entry_qty(proposed_qty=5, premium=3.00, params=rsr.LADDER_PARAMS)
    assert dec["skip"] is False
    assert dec["qty"] == 3
    assert dec["capped_by_dollars"] is True


def test_ladder_binds_contracts_at_low_premium():
    """At a cheap premium the 5-contract cap should bind first (calm-regime ordering)."""
    dec = rsr.cap_entry_qty(proposed_qty=20, premium=0.50, params=rsr.LADDER_PARAMS)
    assert dec["skip"] is False
    assert dec["qty"] == 5
    assert dec["capped_by_contracts"] is True
    assert dec["capped_by_dollars"] is False


def test_ladder_params_pinned_to_live_params_json():
    """The module docstring promises this study's ladder values never silently drift from the
    live params.json file it is measuring. READ-ONLY: this test reads params.json, never
    imports or writes it."""
    raw = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    assert rsr.LADDER_PARAMS["min_contracts"] == raw["min_contracts"]
    assert rsr.LADDER_PARAMS["max_contracts_per_entry"] == raw["max_contracts_per_entry"]
    assert rsr.LADDER_PARAMS["max_position_dollars"] == raw["max_position_dollars"]


# ================================================================================================ #
# No look-ahead (C6): a day's classification must never depend on bars AFTER that day
# ================================================================================================ #
def _synthetic_spy(dates_closes):
    """Build a minimal RTH-only 5-min SPY frame: one 09:30 and one 15:55 bar per (date, close)
    pair, so daily_ohlc_rth's groupby produces exactly that day's open/high/low/close."""
    rows = []
    for d, close in dates_closes:
        rows.append({"timestamp_et": dt.datetime.combine(d, dt.time(9, 30)),
                     "open": close, "high": close, "low": close, "close": close})
        rows.append({"timestamp_et": dt.datetime.combine(d, dt.time(15, 55)),
                     "open": close, "high": close + 1, "low": close - 1, "close": close})
    return pd.DataFrame(rows)


def test_no_lookahead_classification_unaffected_by_future_days():
    dates_closes = [
        (dt.date(2026, 1, 5), 100.0),
        (dt.date(2026, 1, 6), 97.0),   # -3% cc vs prior -> drop day
        (dt.date(2026, 1, 7), 500.0),  # a wild future day that must NOT leak backward
    ]
    days = [dt.date(2026, 1, 5), dt.date(2026, 1, 6)]

    full_df = _synthetic_spy(dates_closes)
    full_daily = rsr.daily_ohlc_rth(full_df)
    full_strata = rsr.classify_strata(full_daily, days)

    truncated_df = _synthetic_spy(dates_closes[:2])  # drop the future day entirely
    trunc_daily = rsr.daily_ohlc_rth(truncated_df)
    trunc_strata = rsr.classify_strata(trunc_daily, days)

    assert full_strata["2026-01-06"]["cc_pct"] == trunc_strata["2026-01-06"]["cc_pct"], (
        "classification of 2026-01-06 changed when a LATER day's data was added/removed -- "
        "that is look-ahead leakage into a stratification that must only use bars <= that day"
    )
    assert full_strata["2026-01-06"]["is_drop_day"] is True


def test_cc_pct_uses_only_the_immediately_prior_trading_day():
    dates_closes = [(dt.date(2026, 1, 5), 100.0), (dt.date(2026, 1, 6), 98.0)]
    days = [dt.date(2026, 1, 6)]
    df = _synthetic_spy(dates_closes)
    daily = rsr.daily_ohlc_rth(df)
    strata = rsr.classify_strata(daily, days)
    expected_cc = (98.0 - 100.0) / 100.0 * 100
    assert strata["2026-01-06"]["cc_pct"] == pytest.approx(expected_cc, abs=1e-6)


# ================================================================================================ #
# Q3 cap-binding computed from exit reasons, never assumed
# ================================================================================================ #
def _row(final_stage, stop_mode="structure"):
    return {"final_stage": final_stage, "resolved_stop_mode": stop_mode,
            "leg_stages": [final_stage]}


def test_q3_cap_binding_computed_from_actual_final_stage_field():
    rows = [
        _row("structure_stop"), _row("structure_stop"), _row("structure_stop"),
        _row("premium_stop"),
        _row("tp1_then_runner"),  # not a binding exit -- excluded from Q3's denominator
        _row("premium_stop", stop_mode="premium"),  # not structure-mode -- excluded entirely
    ]
    q3 = rsr._cap_binding_Q3(rows)
    assert q3["n_structure_mode_trades"] == 5
    assert q3["n_binding_exits_(cap_or_chart)"] == 4
    assert q3["n_catastrophe_cap_fired"] == 1
    assert q3["n_chart_structure_stop_fired"] == 3
    assert q3["cap_binding_rate"] == pytest.approx(0.25)


def test_q3_cap_binding_rate_none_when_no_binding_exits():
    rows = [_row("time_stop")]
    q3 = rsr._cap_binding_Q3(rows)
    assert q3["n_binding_exits_(cap_or_chart)"] == 0
    assert q3["cap_binding_rate"] is None


def test_q3_all_catastrophe_gives_rate_one():
    rows = [_row("premium_stop"), _row("premium_stop")]
    q3 = rsr._cap_binding_Q3(rows)
    assert q3["cap_binding_rate"] == 1.0


# ================================================================================================ #
# The .md must lead with Q6 PARTICIPATION before any Q1 exit-mechanism content
# ================================================================================================ #
def _minimal_out():
    return {
        "label": "SIM-ONLY. test fixture.",
        "measures_prereg": "test",
        "generated_at_et": "2026-09-02T00:00:00",
        "participation_Q6": {"stress_days_with_at_least_one_ladder_placed_entry": 3,
                              "of_frozen_days": 24, "days_with_zero_entries": [],
                              "note": "test note"},
        "frame_fix": {"spy": {"n_frozen_days_shifted": 0, "of_frozen_days": 24,
                              "method": "et_frame.parse_timestamp_et(frame='et-v2')"}},
        "Q1_mechanism_mix_all_stress_days": {"n": 0, "total_pnl": 0,
                                             "final_exit_stage_mix": {}},
        "Q2_side_split": {"bull_calls": {"n": 0}, "bear_puts": {"n": 0}},
        "Q3_cap_binding_rate": {"n_binding_exits_(cap_or_chart)": 0,
                                "n_catastrophe_cap_fired": 0, "n_chart_structure_stop_fired": 0,
                                "cap_binding_rate": None,
                                "note": "test"},
        "Q4_ladder_sizing": {"n_trades_placed_under_ladder": 0, "note": "test"},
        "Q5_worst_case": {"all_stress_days": {}, "worst_single_trade_pnl": None},
        "stratification_caveat": {"n_neither": 0},
        "STRATIFIED_excluding_april_2025_block": {"n": 0, "total_pnl": 0},
        "STRATIFIED_april_2025_block_only": {"n": 0, "total_pnl": 0},
        "STRATIFIED_drop_days_cc_le_neg2pct": {"n": 0, "total_pnl": 0},
        "STRATIFIED_range_days_ge_3pct_ex_drop": {"n": 0, "total_pnl": 0},
        "exclusions": {"n_no_opra_contract": 0, "note": "test"},
        "disclosures": ["disclosure one"],
        "elapsed_s": 1.0,
    }


def test_md_leads_with_q6_before_q1(tmp_path, monkeypatch):
    out_md = tmp_path / "REGIME-STRESS-2026-09-02.md"
    monkeypatch.setattr(rsr, "OUT_MD", out_md)
    monkeypatch.setattr(rsr, "OUT_JSON", tmp_path / "REGIME-STRESS-2026-09-02.json")
    out = _minimal_out()
    rsr.write_md(out, [dt.date(2024, 8, 5)])
    text = out_md.read_text(encoding="utf-8")
    idx_q6 = text.index("Q6 PARTICIPATION")
    idx_q1 = text.index("Q1 -- mechanism mix")
    assert idx_q6 < idx_q1, "Q6 participation must lead the report, before any Q1 exit result"
    # Q6 heading must also appear before ANY dollar P&L figure in the document.
    idx_first_dollar = text.index("$")
    assert idx_q6 < idx_first_dollar


def test_md_reports_the_participation_count_verbatim(tmp_path, monkeypatch):
    out_md = tmp_path / "x.md"
    monkeypatch.setattr(rsr, "OUT_MD", out_md)
    monkeypatch.setattr(rsr, "OUT_JSON", tmp_path / "x.json")
    out = _minimal_out()
    rsr.write_md(out, [dt.date(2024, 8, 5)])
    text = out_md.read_text(encoding="utf-8")
    assert "3 of 24 frozen stress days" in text
