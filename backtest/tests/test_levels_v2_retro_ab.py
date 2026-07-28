"""Guard tests for backtest/tools/levels_v2_retro_ab.py (LEVELS-V2 retro A/B harness,
analysis-only -- no orders, no live config).

Three guards:
  1. NO LOOK-AHEAD (C6): shelf_zones_asof for session D must be computable from daily
     bars strictly before D -- a shelf cluster that only forms ON/AFTER D must NOT
     appear in D's zones. RED-proofed: the same cluster IS found once the sessions that
     formed it are in the past.
  2. STRICTLY ADDITIVE merge: augment_level_set never moves/removes a base level, drops
     candidates within $0.05 of a base active level, and mirrors every added point into
     both active and multi_day.
  3. build_daily_bars aggregates the RTH 5m frame to correct per-session OHLC.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "backtest"), str(REPO / "backtest" / "tools"),
           str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import datetime as dt  # noqa: E402

import pandas as pd  # noqa: E402

from backtest.lib.levels import LevelSet  # noqa: E402
from backtest.tools.levels_v2_retro_ab import (  # noqa: E402
    augment_level_set,
    build_daily_bars,
    shelf_zones_asof,
    zone_points,
)


def _daily(date: str, o: float, h: float, lo: float, c: float) -> dict:
    return {"date": date, "o": o, "h": h, "l": lo, "c": c, "v": 1000.0}


def _bars_dispersed_then_clustered() -> list[dict]:
    """Sessions 01-02..01-17 dispersed (no shelf possible), 01-20..02-06 clustered
    tightly around 100.0 (a clean >=10-session-span shelf ONCE they are history)."""
    bars = []
    # 12 dispersed sessions, each ~$5 apart -- can never co-cluster in a $1.60 band
    # with >=3 touches.
    base = dt.date(2026, 1, 2)
    px = 50.0
    d = base
    n = 0
    while n < 12:
        if d.isoweekday() <= 5:
            bars.append(_daily(d.isoformat(), px, px + 0.3, px - 0.3, px))
            px += 5.0
            n += 1
        d += dt.timedelta(days=1)
    # 14 clustered sessions at ~100.0
    n = 0
    while n < 14:
        if d.isoweekday() <= 5:
            bars.append(_daily(d.isoformat(), 100.0, 100.4, 99.6, 100.1))
            n += 1
        d += dt.timedelta(days=1)
    return bars


# --------------------------------------------------------------- 1. no look-ahead (C6)
def test_shelf_zones_asof_no_lookahead():
    bars = _bars_dispersed_then_clustered()
    cluster_dates = [b["date"] for b in bars if abs(b["c"] - 100.1) < 0.001]
    first_cluster_day = dt.date.fromisoformat(cluster_dates[0])

    # As of the FIRST clustered session, all prior history is dispersed -- the
    # 100.0 cluster lies on/after D and MUST NOT be visible.
    zones_before = shelf_zones_asof(bars, first_cluster_day)
    assert all(not (z["band_low"] <= 100.0 <= z["band_high"]) for z in zones_before), (
        f"look-ahead: 100.0-cluster visible as of {first_cluster_day}: {zones_before}")

    # RED-proof (assertion is sensitive, not tautological): one session AFTER the last
    # clustered session, the same cluster IS in the past and MUST be found.
    after_day = dt.date.fromisoformat(cluster_dates[-1]) + dt.timedelta(days=1)
    zones_after = shelf_zones_asof(bars, after_day)
    assert any(z["band_low"] <= 100.0 <= z["band_high"] for z in zones_after), (
        f"detector never finds the cluster at all as of {after_day} -- test would be blind")


def test_shelf_zones_asof_ignores_bars_on_or_after_session():
    """Byte-level check: zones for D computed from the full bar list equal zones
    computed from a list PRE-TRUNCATED to dates < D (i.e. the function itself does
    the truncation and nothing of day D leaks in)."""
    bars = _bars_dispersed_then_clustered()
    mid = dt.date.fromisoformat(bars[18]["date"])  # inside the clustered run
    truncated = [b for b in bars if b["date"] < mid.isoformat()]
    assert shelf_zones_asof(bars, mid) == shelf_zones_asof(truncated, mid)


# --------------------------------------------------------------- 2. strictly additive
def test_augment_level_set_strictly_additive():
    base = LevelSet(active=[100.0, 105.0, 110.0], multi_day=[105.0], swept_levels=[110.0])
    zones = [{"band_low": 104.98, "band_high": 106.58, "touches": 4},
             {"band_low": 120.0, "band_high": 121.6, "touches": 3}]
    pts = zone_points(zones)
    # lo=104.98 within $0.05 of base 105.0 -> dropped; mid=105.78, hi=106.58 added;
    # 120.0 / 120.8 / 121.6 added.
    aug, added = augment_level_set(base, pts)
    assert added == [105.78, 106.58, 120.0, 120.8, 121.6]
    # base levels all still present, unmoved
    for b in base.active:
        assert b in aug.active
    assert 104.98 not in aug.active
    # every added point mirrored into multi_day
    for p in added:
        assert p in aug.active and p in aug.multi_day
    # base multi_day preserved; swept untouched; inputs not mutated
    assert 105.0 in aug.multi_day
    assert aug.swept_levels == [110.0]
    assert base.active == [100.0, 105.0, 110.0]


def test_augment_level_set_no_zones_returns_base_object_unchanged():
    base = LevelSet(active=[100.0], multi_day=[], swept_levels=[])
    aug, added = augment_level_set(base, [])
    assert added == [] and aug is base


# --------------------------------------------------------------- 3. daily aggregation
def test_build_daily_bars_aggregates_rth_frame():
    rows = []
    for i, (o, h, lo, c) in enumerate([(10, 12, 9, 11), (11, 15, 10, 14)]):
        rows.append({"timestamp_et": pd.Timestamp(f"2026-01-05 09:{30+5*i}:00"),
                     "open": o, "high": h, "low": lo, "close": c, "volume": 100})
    rows.append({"timestamp_et": pd.Timestamp("2026-01-06 09:30:00"),
                 "open": 20, "high": 21, "low": 19, "close": 20.5, "volume": 50})
    df = pd.DataFrame(rows)
    bars = build_daily_bars(df)
    assert [b["date"] for b in bars] == ["2026-01-05", "2026-01-06"]
    d1 = bars[0]
    assert (d1["o"], d1["h"], d1["l"], d1["c"], d1["v"]) == (10.0, 15.0, 9.0, 14.0, 200.0)
    d2 = bars[1]
    assert (d2["o"], d2["h"], d2["l"], d2["c"], d2["v"]) == (20.0, 21.0, 19.0, 20.5, 50.0)
