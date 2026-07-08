"""Guard: sim-live parity ledger (G9, 2026-07-07). Proves the slippage math + the
fill-existence filter on fixtures (live data is currently empty -- 0 reconciled fills)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("sim_live_parity", SCRIPTS / "sim_live_parity.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["sim_live_parity"] = m
    spec.loader.exec_module(m)
    return m


def test_parse_fill_computes_slippage():
    row = {"ts_et": "2026-07-08T10:00:00", "setup": "vwap_continuation", "symbol": "SPY..P",
           "exec": {"entry_px": 1.00, "premium": 0.95, "broker": {"filled_avg_price": "1.08"}}}
    r = _load().parse_fill(row, "safe-2")
    assert r["filled_avg_price"] == 1.08 and r["assumed_px"] == 1.00
    assert r["slippage"] == 0.08 and r["slippage_pct"] == 0.08


def test_unfilled_row_is_none():
    slp = _load()
    assert slp.parse_fill({"exec": {"entry_px": 1.0, "broker": {"filled_avg_price": None}}}, "core") is None
    assert slp.parse_fill({"exec": {"entry_px": 1.0, "broker": {"filled_avg_price": "0"}}}, "core") is None  # 0 != fill


def test_aggregate_groups_per_setup():
    fills = [{"setup": "a", "slippage": 0.10, "slippage_pct": 0.1},
             {"setup": "a", "slippage": 0.20, "slippage_pct": 0.2},
             {"setup": "b", "slippage": 0.05, "slippage_pct": 0.05}]
    agg = _load().aggregate(fills)
    assert agg["reconciled_fills"] == 3
    assert agg["setups"]["a"]["n"] == 2 and agg["setups"]["a"]["mean_slippage"] == 0.15
    assert agg["setups"]["b"]["n"] == 1


def test_build_ledger_counts_only_real_fills(tmp_path):
    slp = _load()
    p = tmp_path / "decisions.jsonl"
    p.write_text("\n".join([
        json.dumps({"setup": "s1", "exec": {"entry_px": 1.0, "broker": {"filled_avg_price": "1.1"}}}),
        json.dumps({"setup": "s1", "exec": {"entry_px": 1.0, "broker": {"filled_avg_price": None}}}),
    ]), encoding="utf-8")
    fills, summary = slp.build_ledger([p])
    assert summary["reconciled_fills"] == 1  # the null-fill row is excluded
    assert fills[0]["slippage"] == 0.1
