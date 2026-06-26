"""Regression: heartbeat_core must normalize entry_no_trade_window_et before it
reaches the engine_cli payload.

Bug (2026-06-25): the BOLD account params (automation/state/aggressive/params.json)
set ``entry_no_trade_window_et: []`` (empty list = "no blackout window"). The old
``_build_payload`` passed that empty list straight through to
``score_params.{bear,bull}_kwargs.no_trade_window``. engine_cli._coerce_score_kwargs
(engine_cli.py:283-290) rejects ANY non-2-element list with
``BadPayload: ...no_trade_window: expected ['HH:MM','HH:MM']`` — which _engine_verdict
swallows into SKIP_BAD_INPUT, silently degrading the Bold heartbeat. The orchestrator
already reads a falsy window as None (orchestrator.py:386-395); heartbeat_core now does
the same via ``_norm_no_trade_window``.

These tests prove:
  1. ``_norm_no_trade_window`` maps []/None/malformed -> None and keeps a real 2-list.
  2. The REAL Safe (null) AND Bold ([]) params produce a payload whose score kwargs pass
     ``_coerce_score_kwargs`` with NO BadPayload (the end-to-end "valid payload" assertion).
  3. The un-normalized empty list IS what engine_cli rejects (the bug the fix prevents),
     while a genuine 2-element window still parses to a (time, time) pair.

Run:  cd backtest && .venv/Scripts/python.exe -m pytest tests/test_heartbeat_core_no_trade_window.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
for _p in (str(BACKTEST), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.engine.engine_cli import BadPayload, _coerce_score_kwargs  # noqa: E402

# heartbeat_core lives in setup/scripts (not a package); load it by path. Its module-level
# sys.path inserts pull in pandas + the backtest ribbon, so plain exec is enough.
_MOD = ROOT / "setup" / "scripts" / "heartbeat_core.py"
_spec = importlib.util.spec_from_file_location("heartbeat_core", _MOD)
hc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hc)

SAFE_PARAMS = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
BOLD_PARAMS = json.loads((ROOT / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8"))


# --- 1. the normalization helper -------------------------------------------
@pytest.mark.parametrize("value,expected", [
    ([], None),                                  # Bold on disk -> "no window"
    (None, None),                                # Safe on disk (null) -> "no window"
    (["14:00"], None),                           # malformed 1-element -> None (never crashes)
    (["14:00", "15:00", "16:00"], None),         # malformed 3-element -> None
    ("14:00-15:00", None),                       # wrong type entirely -> None
    (["14:00", "15:00"], ["14:00", "15:00"]),    # genuine window passes through
    (("14:00", "15:00"), ["14:00", "15:00"]),    # 2-tuple normalized to list
])
def test_norm_no_trade_window(value, expected):
    assert hc._norm_no_trade_window(value) == expected


def test_bold_params_on_disk_are_the_empty_list():
    """Guards the premise: if someone fills in a real Bold window this test stays honest."""
    assert BOLD_PARAMS.get("entry_no_trade_window_et") == [], \
        "Bold params no longer carry [] — update this regression's premise"


# --- 2. real params -> a VALID engine_cli payload (no BadPayload) -----------
def _synth_rth_bars() -> pd.DataFrame:
    """~300 RTH 5m bars on a gentle uptrend (deterministic, no network, no RNG) — enough to
    seed the 48-EMA ribbon and yield a non-UNKNOWN stack so _build_payload returns a payload."""
    rows = []
    price = 600.0
    prev = price - 0.06
    for d in range(4):  # 4 calendar days x 78 RTH bars = 312 (>= the 80-bar floor + 150 window)
        day = pd.Timestamp(f"2026-06-0{d + 1} 00:00", tz="America/New_York")
        t = day + pd.Timedelta(hours=9, minutes=30)
        end = day + pd.Timedelta(hours=16)
        while t < end:
            price = round(price + 0.06, 2)  # steady climb -> fast>pivot>slow -> BULL stack
            rows.append({"timestamp": t, "open": prev, "high": max(prev, price) + 0.05,
                         "low": min(prev, price) - 0.05, "close": price, "volume": 1_000_000})
            prev = price
            t = t + pd.Timedelta(minutes=5)
    return pd.DataFrame(rows)


@pytest.mark.parametrize("params,label", [(SAFE_PARAMS, "safe"), (BOLD_PARAMS, "bold")])
def test_real_params_build_payload_passes_engine_coercion(params, label):
    df = _synth_rth_bars()
    payload = hc._build_payload(df, params, vix=(18.0, 17.9), levels=([], []), vix_ma=(17.0, 16.5))
    assert payload is not None, f"{label}: synthetic bars should yield a payload"
    sp = payload["score_params"]
    # the fix: no_trade_window normalized to None for both arms
    assert sp["bear_kwargs"]["no_trade_window"] is None
    assert sp["bull_kwargs"]["no_trade_window"] is None
    # the real proof: engine_cli accepts the score kwargs without BadPayload (the exact gate
    # that produced SKIP_BAD_INPUT on the Bold path before the fix)
    _coerce_score_kwargs(sp["bear_kwargs"], f"{label}.bear_kwargs")
    _coerce_score_kwargs(sp["bull_kwargs"], f"{label}.bull_kwargs")


# --- 3. document the bug the fix prevents ----------------------------------
def test_unnormalized_empty_list_is_what_engine_rejects():
    """Without _norm_no_trade_window, the empty list reaches the engine and is rejected —
    this is the latent BadPayload -> SKIP_BAD_INPUT degradation on the Bold account."""
    with pytest.raises(BadPayload, match=r"no_trade_window: expected"):
        _coerce_score_kwargs({"no_trade_window": []}, "bear_kwargs")


def test_genuine_window_still_parses_to_time_pair():
    """The fix must not break a real blackout window: a 2-element list still decodes."""
    import datetime as dt
    out = _coerce_score_kwargs(
        {"no_trade_window": hc._norm_no_trade_window(["14:00", "15:00"])}, "bear_kwargs")
    assert out["no_trade_window"] == (dt.time(14, 0), dt.time(15, 0))
