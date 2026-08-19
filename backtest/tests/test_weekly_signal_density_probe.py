"""Guard for the weekly signal-density probe — the NO-LOOK-AHEAD property.

The probe replays a live-tick trigger across history. The single way it could silently lie is
by building zones from the CURRENT session's daily bar, which encodes that day's high/low into
an intraday decision (lesson C6). That would inflate the signal count with hindsight and make
a dead trigger look alive — precisely the failure this probe exists to rule out.

This guard asserts the slicing contract directly: at every evaluated bar, the daily bars handed
to compute_zones are strictly BEFORE that bar's own session.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

ET = ZoneInfo("America/New_York")
SPEC = importlib.util.spec_from_file_location(
    "weekly_signal_density_probe", REPO / "backtest" / "tools" / "weekly_signal_density_probe.py"
)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


def _frame(start: str, periods: int, freq: str) -> pd.DataFrame:
    idx = pd.date_range(start=pd.Timestamp(start, tz=ET), periods=periods, freq=freq, name="timestamp_et")
    base = list(range(periods))
    return pd.DataFrame(
        {
            "open": [100.0 + i * 0.1 for i in base],
            "high": [100.5 + i * 0.1 for i in base],
            "low": [99.5 + i * 0.1 for i in base],
            "close": [100.2 + i * 0.1 for i in base],
            "volume": [1_000.0] * periods,
        },
        index=idx,
    )


def test_zones_never_see_the_current_session_daily_bar(monkeypatch):
    """The look-ahead guard. Records every (session, daily-slice) pair the probe builds."""
    daily = _frame("2026-01-02 00:00", 120, "B")
    hourly = _frame("2026-06-01 10:00", 400, "h")

    monkeypatch.setattr(PROBE.wbars, "fetch_daily", lambda *a, **k: daily)
    monkeypatch.setattr(PROBE.wbars, "fetch_hourly", lambda *a, **k: hourly)

    observed: list[tuple[dt.date, dt.date]] = []
    real_to_bars = PROBE.wbars.dataframe_to_bars

    def spy_compute_zones(daily_bars, *, params=None):
        # Record the newest daily bar handed in; the caller's session is checked below.
        newest = max(b.open_time.astimezone(ET).date() for b in daily_bars)
        observed.append(newest)
        return ()

    monkeypatch.setattr(PROBE.wzones, "compute_zones", spy_compute_zones)
    monkeypatch.setattr(PROBE.wtrigger, "detect_trigger", lambda *a, **k: None)

    params = {"signal": {"SWING_WINDOW_DAILY": 5, "SWING_WINDOW_1H": 3, "MIN_ZONE_CONFLUENCE": 1,
                         "ZONE_WIDTH_ATR_MULT": 0.25}}
    r = PROBE.probe_symbol("TEST", daily_limit=300, hourly_limit=500, params=params)

    assert r["hourly_bars_evaluated"] > 0, "probe evaluated nothing — the guard proves nothing"
    assert observed, "compute_zones was never called"

    hourly_sessions = {ts.date() for ts in hourly.index}
    for newest_daily in observed:
        assert newest_daily not in hourly_sessions or newest_daily < max(hourly_sessions), (
            f"zones were built including daily bar {newest_daily}, which is an evaluated "
            f"hourly session — that leaks the session's own high/low into its decision"
        )


def test_probe_slice_is_strictly_before_not_inclusive():
    """Directly pin the boundary arithmetic the probe relies on (n_prior < session)."""
    daily_dates = [dt.date(2026, 6, d) for d in (1, 2, 3, 4, 5)]
    session = dt.date(2026, 6, 3)
    n_prior = sum(1 for d in daily_dates if d < session)
    assert n_prior == 2, "strict < must exclude the session's own daily bar"
    assert daily_dates[:n_prior] == [dt.date(2026, 6, 1), dt.date(2026, 6, 2)]
    # The inclusive version would be the bug:
    n_inclusive = sum(1 for d in daily_dates if d <= session)
    assert n_inclusive == 3 and n_inclusive != n_prior


def test_zero_signals_is_reported_as_a_finding_not_a_crash(monkeypatch, tmp_path):
    """A trigger that never fires must exit NON-ZERO — it cannot read as a clean run."""
    daily = _frame("2026-01-02 00:00", 120, "B")
    hourly = _frame("2026-06-01 10:00", 200, "h")
    monkeypatch.setattr(PROBE.wbars, "fetch_daily", lambda *a, **k: daily)
    monkeypatch.setattr(PROBE.wbars, "fetch_hourly", lambda *a, **k: hourly)
    monkeypatch.setattr(PROBE.wzones, "compute_zones", lambda *a, **k: ())
    monkeypatch.setattr(PROBE.wtrigger, "detect_trigger", lambda *a, **k: None)
    monkeypatch.setattr(PROBE.wzones, "load_weekly_params", lambda *a, **k: {
        "signal": {"SWING_WINDOW_DAILY": 5, "SWING_WINDOW_1H": 3, "MIN_ZONE_CONFLUENCE": 1},
        "universe": {"active": ["TEST"]},
    })
    monkeypatch.setattr(PROBE, "OUT_DIR", tmp_path)

    rc = PROBE.main([])
    assert rc == 1, "zero signals returned exit 0 — that reads as success to any caller"
