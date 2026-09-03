"""Guard for PROD-SHADOW-NAME-COLLISION (queue.md, filed 2026-09-03 04:47 ET).

Two unrelated instruments shared the name 'prod-shadow': (1) the go-live gate's criterion-5
designation (automation/state/prod-shadow-designation.json, arm safe-3, read by
go_live_gate.prod_shadow_criterion) and (2) setup/scripts/prod_shadow.py's safe-2
equity-rescale sim (analysis/prod-shadow/{ledger.jsonl,summary.json}). This pins that (2)'s
summary.json self-identifies and points readers at (1) instead of being mistaken for it --
no behaviour change, labeling only.
"""
from __future__ import annotations

import importlib.util
import os

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


def _trade(date, entry_ts, entry_px=2.0, ret_pct=10.0, qty=3.0):
    return {
        "date": date, "symbol": "SPY", "right": "C", "setup": "TEST",
        "exit_reason": "tp1", "entry_ts_et": entry_ts,
        "exit_ts_et": entry_ts.replace("T09", "T10"), "arm": "safe-2", "qty": qty,
        "entry_px": entry_px, "ret_pct_of_premium": ret_pct,
        "pnl_dollars": qty * 100 * entry_px * (ret_pct / 100.0),
    }


def _summary():
    trades = [_trade("2026-08-01", "2026-08-01T09:40:00")]
    ledger, daily = ps.simulate(trades, RATES, starting_equity=5000.0, risk_fraction=0.02,
                                 max_contracts=20, daily_stop_pct=0.06)
    config = {"base_arm": "safe-2", "starting_equity": 5000.0, "risk_fraction_per_trade": 0.02,
              "max_contracts": 20, "daily_stop_pct": 0.06, "daily_target_dollars": 2000}
    return ps.build_summary(ledger, daily, config, rates_meta="test", base_arm="safe-2")


def test_summary_carries_instrument_disambiguation_keys():
    summary = _summary()
    assert summary["instrument"] == "equity-rescale-sim"
    assert summary["not_criterion_5"] is True
    assert summary["see_instead"] == (
        "automation/state/prod-shadow-designation.json + go_live_gate.prod_shadow_criterion"
    )


def test_module_docstring_warns_of_the_collision():
    assert "NAME COLLISION" in ps.__doc__
    assert "not criterion 5" in ps.__doc__.lower() or "not_criterion_5" in ps.__doc__
    assert "safe-3" in ps.__doc__
