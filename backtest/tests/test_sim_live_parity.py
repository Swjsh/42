"""Guard: sim-live parity ledger (G9, 2026-07-07; T2-rewired 2026-07-08).

T2 REWIRE: the fill (existence + price) now comes from T1's fills-ledger.jsonl (broker-truth),
never from a decision row's own filled_avg_price (which the writer never populates -- that was
the permanent false "0 fills ever" bug). Decision rows are used ONLY to look up setup name +
assumed price via an exact order_id match. These tests exercise the NEW order_id-matching path.
"""
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


def _fill(order_id="oid-1", arm="safe-1", symbol="SPY260708P00741000", price=1.08,
          ts_et="2026-07-08T10:00:00-04:00") -> dict:
    return {"arm": arm, "order_id": order_id, "symbol": symbol, "side": "buy",
            "price": price, "ts_et": ts_et, "is_crypto": False}


def test_parse_fill_computes_slippage_from_matched_order():
    order_index = {"oid-1": {"arm": "safe-1", "setup": "vwap_continuation", "assumed_px": 1.00,
                             "symbol": "SPY260708P00741000"}}
    r = _load().parse_fill(_fill(price=1.08), order_index)
    assert r["filled_avg_price"] == 1.08 and r["assumed_px"] == 1.00
    assert r["slippage"] == 0.08 and abs(r["slippage_pct"] - 0.08) < 1e-9
    assert r["setup"] == "vwap_continuation"
    assert r["matched_decision_row"] is True


def test_parse_fill_unmatched_order_still_logged():
    """A broker-truth fill with no matching decision row is STILL a real fill -- it must be
    logged (setup='unknown', no slippage), never dropped (that was the old bug's failure mode
    in reverse: silently excluding real fills because ledger metadata was missing)."""
    r = _load().parse_fill(_fill(order_id="no-match"), order_index={})
    assert r["filled_avg_price"] == 1.08
    assert r["setup"] == "unknown"
    assert r["assumed_px"] is None
    assert "slippage" not in r
    assert r["matched_decision_row"] is False


def test_aggregate_groups_per_setup():
    fills = [{"setup": "a", "slippage": 0.10, "slippage_pct": 0.1, "matched_decision_row": True},
             {"setup": "a", "slippage": 0.20, "slippage_pct": 0.2, "matched_decision_row": True},
             {"setup": "b", "slippage": 0.05, "slippage_pct": 0.05, "matched_decision_row": True}]
    agg = _load().aggregate(fills)
    assert agg["reconciled_fills"] == 3
    assert agg["n_matched_decision_row"] == 3
    assert agg["setups"]["a"]["n"] == 2 and agg["setups"]["a"]["mean_slippage"] == 0.15
    assert agg["setups"]["b"]["n"] == 1


def test_build_order_index_matches_fleet_arm_placement_broker_id(tmp_path):
    slp = _load()
    p = tmp_path / "decisions.jsonl"
    p.write_text(json.dumps({
        "arm_id": "safe-3", "action": "ENTER_BULL", "symbol": "SPY260708C00745000",
        "setup": "BULLISH_RECLAIM", "premium": 0.17,
        "placement": {"broker": {"id": "order-abc"}},
    }) + "\n", encoding="utf-8")
    index = slp.build_order_index([p])
    assert index["order-abc"]["setup"] == "BULLISH_RECLAIM"
    assert index["order-abc"]["assumed_px"] == 0.17


def test_build_ledger_end_to_end_broker_truth_drives_fill_count(tmp_path):
    """The DEFINITIVE regression guard for the T2 bug: reconciled_fills must equal the number
    of BUY fills in the fills-ledger, NOT the number of decision rows carrying a (never
    populated) filled_avg_price. A decision ledger with ZERO fill evidence must still produce
    reconciled_fills > 0 as long as broker-truth fills exist."""
    slp = _load()
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text(json.dumps({
        "arm_id": "safe-1", "action": "ENTER_BEAR", "symbol": "SPY260708P00741000",
        "setup": "BEARISH_REJECTION", "premium": 0.96,
        "placement": {"broker": {"id": "order-1", "filled_avg_price": None}},  # NEVER populated
    }) + "\n", encoding="utf-8")
    ledger = tmp_path / "fills-ledger.jsonl"
    ledger.write_text("\n".join([
        json.dumps(_fill(order_id="order-1", price=0.96)),   # matched -> slippage computable
        json.dumps(_fill(order_id="order-2", price=0.25)),   # unmatched -> still counted
    ]) + "\n", encoding="utf-8")

    fills, summary = slp.build_ledger(fills_ledger_path=ledger, decision_sources=[decisions])
    assert summary["reconciled_fills"] == 2  # broker-truth count, NOT decisions-row count (0)
    assert summary["n_matched_decision_row"] == 1
