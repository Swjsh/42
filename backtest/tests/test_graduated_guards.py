"""Graduated guards — repeat-violated lessons turned into assertions.

Each test corresponds to a lesson family that recurred AFTER it was written down
(prose failed as a control). Converting them to tests means CI catches the
regression instead of a human re-discovering it weeks later.

  test_no_lookahead_*         -> L14/L34/L57 (look-ahead / future leakage)
  test_params_override_binds  -> L38/L72     (dead/translated-but-unapplied knob;
                                              the class of both 2026-06-14 bugs:
                                              the v15.3 ribbon gates AND the
                                              premium_stop_pct_bear mapping)
  test_exit_knobs_synced_*    -> L72         (j_edge_tracker base drifting from
                                              params.json — the C3 drift)
  test_no_pythonw_*           -> L41         (venv-stub pythonw re-exec, recurred 5x)

Run:  cd backtest && python -m pytest tests/test_graduated_guards.py -v
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.orchestrator import run_backtest  # noqa: E402

DATA = BACKTEST / "data"
MASTER_SPY = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
MASTER_VIX = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
PARAMS = REPO / "automation" / "state" / "params.json"
_HAS_DATA = MASTER_SPY.exists() and MASTER_VIX.exists()
_needs_data = pytest.mark.skipif(not _HAS_DATA, reason="master SPY/VIX CSV not present")


def _load(start: str, end: str):
    import pandas as pd

    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    spy = spy[(spy["timestamp_et"] >= start) & (spy["timestamp_et"] < f"{end}T23:59:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= start) & (vix["timestamp_et"] < f"{end}T23:59:59")].reset_index(drop=True)
    return spy, vix


def _result(spy, vix, start: str, end: str, **kw):
    trades = run_backtest(
        spy, vix,
        start_date=dt.date.fromisoformat(start),
        end_date=dt.date.fromisoformat(end),
        use_real_fills=False,
        **kw,
    ).trades
    return len(trades), round(sum(t.dollar_pnl for t in trades), 2)


def _signature(trades) -> list:
    return sorted((str(t.entry_time_et), round(t.dollar_pnl, 2)) for t in trades)


@_needs_data
def test_no_lookahead_future_bars_dont_change_past_trades() -> None:
    """L14/L34/L57: trades over [start, mid] must be identical whether or not the
    dataframe also contains future bars [mid, end]. If a predicate reads past the
    current bar, appending the future changes past decisions and this fails."""
    start, mid, end = "2026-02-01", "2026-04-01", "2026-05-07"
    spy_short, vix_short = _load(start, mid)
    spy_long, vix_long = _load(start, end)
    short = run_backtest(spy_short, vix_short, start_date=dt.date.fromisoformat(start),
                         end_date=dt.date.fromisoformat(mid), use_real_fills=False).trades
    long_ = run_backtest(spy_long, vix_long, start_date=dt.date.fromisoformat(start),
                         end_date=dt.date.fromisoformat(mid), use_real_fills=False).trades
    assert _signature(short) == _signature(long_), "future bars changed past trades -> look-ahead leak"


@_needs_data
@pytest.mark.parametrize(
    "key,value",
    [
        ("min_ribbon_momentum_cents", 50.0),  # entry gate -> changes trade count
        ("max_ribbon_duration_bars", 3),      # entry gate -> changes trade count
        ("midday_trendline_gate", True),      # entry gate -> changes trade count
        ("premium_stop_pct_bear", -0.50),     # exit knob  -> changes P&L (was unmapped, 2026-06-14)
    ],
)
def test_params_override_binds(key, value) -> None:
    """L38/L72: a key that _params_to_kwargs claims to map MUST change engine
    output (count or P&L) when overridden. Guards the 'translated but never
    applied' bug class — both the v15.3 ribbon gates and premium_stop_pct_bear
    were silently dropped before 2026-06-14."""
    start, end = "2026-03-01", "2026-05-07"
    spy, vix = _load(start, end)
    base = _result(spy, vix, start, end)
    overridden = _result(spy, vix, start, end, params_overrides={key: value})
    assert overridden != base, f"override {key}={value} did not change output (dead knob)"


def test_exit_knobs_synced_with_jedge_tracker() -> None:
    """L72: j_edge_tracker.V15_J_EDGE_OVERRIDES exit knobs must mirror production
    params.json. Drift here made grinders search a stale base for weeks. Parsed via
    ast (no import) so the test stays cheap and dependency-free."""
    jet = (BACKTEST / "autoresearch" / "j_edge_tracker.py").read_text(encoding="utf-8")
    overrides = None
    for node in ast.walk(ast.parse(jet)):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "V15_J_EDGE_OVERRIDES" for t in node.targets
        ):
            overrides = ast.literal_eval(node.value)
    assert overrides is not None, "V15_J_EDGE_OVERRIDES not found in j_edge_tracker.py"
    params = json.loads(PARAMS.read_text(encoding="utf-8-sig"))
    assert overrides["tp1_premium_pct"] == params["tp1_premium_pct"]
    assert overrides["tp1_qty_fraction"] == params["tp1_qty_fraction"]
    assert overrides["runner_target_premium_pct"] == params["runner_max_premium_pct"]
    assert overrides["premium_stop_pct_bear"] == params["premium_stop_pct_bear"]


def test_no_pythonw_relative_executable_path() -> None:
    """L41: never resolve pythonw via Path(sys.executable).parent — under an old
    daemon that resolves to the venv stub that re-execs a visible console window.
    Recurred 5x. Hardcode the system Python path instead."""
    pattern = re.compile(r"sys\.executable\)\.parent\s*/\s*[\"']pythonw")
    offenders = []
    for path in REPO.rglob("*.py"):
        s = str(path)
        if any(skip in s for skip in ("_local_backups", ".venv", "site-packages", "__pycache__")):
            continue
        try:
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(s)
        except OSError:
            continue
    assert not offenders, f"L41 regression: relative pythonw resolution in {offenders}"
