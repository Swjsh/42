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
    # NOTE (2026-08-22): do NOT importlib.reload(sd) here. reload() re-executes the
    # module's class statements in place, rebinding setup_dispatch.SetupDispatcher /
    # DispatchResult to BRAND NEW class objects on the shared sys.modules["setup_dispatch"]
    # entry. Any OTHER test file that already did `from setup_dispatch import SetupDispatcher`
    # at collection time (before this test executes) keeps the OLD class object, while
    # `patch("setup_dispatch.SetupDispatcher.<method>", ...)` (a string lookup) patches the
    # NEW post-reload class -- so the mock never intercepts the call the old-class instance
    # makes, and assert_called_once() fails downstream in test_setup_dispatch.py. This test
    # only needs a clean `_REPO` for the duration of the test, which monkeypatch.setattr
    # below already provides without touching the shared module singleton at all.
    st = tmp_path / "automation" / "state"
    st.mkdir(parents=True)
    (st / "prior-rth-close.json").write_text(json.dumps({"prior_rth_close": 751.31}), encoding="utf-8")
    # NO today-bias.json -> must fall back to prior-rth-close.json
    monkeypatch.setattr(sd, "_REPO", tmp_path)
    import inspect
    gap_cls = next(o for _, o in inspect.getmembers(sd, inspect.isclass) if hasattr(o, "_get_prior_rth_close"))
    inst = gap_cls.__new__(gap_cls)  # method only reads state files
    assert inst._get_prior_rth_close() == 751.31
