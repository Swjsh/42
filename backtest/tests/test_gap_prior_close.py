"""Guard: gap_and_go prior-close fallback (V2, 2026-07-08). The dispatch reads prior-rth-close.json
when today-bias.json lacks the key -> gap_and_go stops SKIP_NO_FEED (F22/F25)."""
from __future__ import annotations
import importlib, json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def test_dispatch_prior_close_fallback(tmp_path, monkeypatch):
    for p in (REPO / "setup" / "scripts", REPO / "backtest"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import setup_dispatch as sd
    importlib.reload(sd)
    st = tmp_path / "automation" / "state"
    st.mkdir(parents=True)
    (st / "prior-rth-close.json").write_text(json.dumps({"prior_rth_close": 751.31}), encoding="utf-8")
    # NO today-bias.json -> must fall back to prior-rth-close.json
    monkeypatch.setattr(sd, "_REPO", tmp_path)
    import inspect
    gap_cls = next(o for _, o in inspect.getmembers(sd, inspect.isclass) if hasattr(o, "_get_prior_rth_close"))
    inst = gap_cls.__new__(gap_cls)  # method only reads state files
    assert inst._get_prior_rth_close() == 751.31
