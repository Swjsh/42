"""Guard: trendline_engine.write_live_state shadow schema (V3, 2026-07-08)."""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def _load():
    if str(REPO / "backtest") not in sys.path:
        sys.path.insert(0, str(REPO / "backtest"))
    spec = importlib.util.spec_from_file_location(
        "trendline_engine", REPO / "backtest" / "autoresearch" / "trendline_engine.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["trendline_engine"] = m
    spec.loader.exec_module(m)
    return m


def _tl(te, kind, current_value, status):
    return te.Trendline(kind=kind, a_et="09:35", a_price=746.0, b_et="10:05", b_price=747.0,
                        slope_per_bar=0.1, current_et="10:30", current_value=current_value,
                        last_close=747.5, break_level=746.5, respect_count=11, violations=0,
                        status=status, a_unix=1, b_unix=2, proj_unix=3, proj_price=748.0)


def test_write_live_state_schema(tmp_path):
    te = _load()
    te.LIVE_STATE = tmp_path / "trendlines-live.json"
    te.write_live_state([_tl(te, "support", 746.8, "INTACT"),
                         _tl(te, "resistance", 749.0, "TESTING")], "2026-07-08")
    d = json.loads(te.LIVE_STATE.read_text(encoding="utf-8"))
    assert d["count"] == 2
    kinds = [t["kind"] for t in d["trendlines"]]
    assert "support" in kinds and "resistance" in kinds
    sup = next(t for t in d["trendlines"] if t["kind"] == "support")
    assert sup["current_value"] == 746.8 and sup["status"] == "INTACT" and sup["break_level"] == 746.5
    assert "summary" in sup
