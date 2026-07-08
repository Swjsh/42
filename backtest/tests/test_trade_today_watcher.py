"""Guard: trade_today_watcher classify_orders (OP-33e 'did it trade' instrument, 2026-07-08)."""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def _load():
    for p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(
        "trade_today_watcher", REPO / "setup" / "scripts" / "trade_today_watcher.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["trade_today_watcher"] = m
    spec.loader.exec_module(m)
    return m


def test_classify_filled_vs_unfilled_spy_only():
    w = _load()
    orders = [
        {"id": "1", "symbol": "SPY260708P00745000", "side": "buy", "filled_qty": "3", "filled_avg_price": "1.20", "status": "filled"},
        {"id": "2", "symbol": "SPY260708P00710000", "side": "buy", "filled_qty": "0", "filled_avg_price": None, "status": "canceled"},
        {"id": "3", "symbol": "BTC/USD", "side": "buy", "filled_qty": "0.001", "filled_avg_price": "63000", "status": "filled"},  # crypto -> ignore
        {"id": "4", "symbol": "AAPL", "side": "buy", "filled_qty": "10", "filled_avg_price": "200", "status": "filled"},          # stock -> ignore
    ]
    filled, unfilled = w.classify_orders(orders)
    assert len(filled) == 1 and filled[0]["symbol"] == "SPY260708P00745000" and filled[0]["qty"] == 3.0
    assert len(unfilled) == 1 and unfilled[0]["symbol"] == "SPY260708P00710000"
    syms = [x["symbol"] for x in filled + unfilled]
    assert "BTC/USD" not in syms and "AAPL" not in syms


def test_empty_and_none():
    w = _load()
    assert w.classify_orders([]) == ([], [])
    assert w.classify_orders(None) == ([], [])
