"""_option_bars_1min_cache.py -- shared helper: live-REST 1-minute OPRA option bars, disk-
cached under backtest/data/highres/ (existing, already-populated naming convention -- see
GOAL-REPLAY-TODAY-GREEN.md iteration 3 / level_target_exit_study.py). Built for the
OPTION-BAR-RESOLUTION-BIAS-2026-08-02 investigation; reused UNCHANGED by every script in that
investigation (option_bar_resolution_bias_2026_08_02.py,
structure_stop_study_1min_2026_08_02.py, ribbon_ride_strike_exit_ab_1min_2026_08_02.py) so the
fetch/cache/normalize logic exists in exactly ONE place (OP-22 -- no copy-paste drift risk
across the three scripts).

Wraps exit_shape_parity_study.fetch_option_bars (the SAME REST path the level-target-exit lane
proved out on the real-fills population tonight, 2026-08-02) -- does not reimplement the
network call. Read-only market data; no trading-path file touched.
"""
from __future__ import annotations

import datetime as dt
import sys
import time as _time_mod
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts",
           REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp   # noqa: E402

HIGHRES_DIR = REPO / "backtest" / "data" / "highres"
ET_OFFSET = dt.timezone(dt.timedelta(hours=-4))  # EDT -- this rig trades only in EDT months
RATE_LIMIT_SLEEP_S = 0.12                          # matches structure_stop_study.py's own convention


def fetch_1min_cached(symbol: str, date_et: str) -> tuple[Optional[pd.DataFrame], str]:
    """Returns (df_or_None, source) where source in {"cache_hit", "rest_fetch", "no_data"}.
    df columns: timestamp_et (tz-naive ET), open, high, low, close, volume.

    Cache-first: a symbol/date already fetched by ANY of the three investigation scripts is
    never re-fetched by another -- backtest/data/highres/{symbol}_1m_{date}.csv is shared,
    disk-persisted state, not a per-process memo.
    """
    cache_path = HIGHRES_DIR / f"{symbol}_1m_{date_et}.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path)
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize(None)
        return df, "cache_hit"
    bars = esp.fetch_option_bars(symbol, date_et)
    _time_mod.sleep(RATE_LIMIT_SLEEP_S)
    if not bars:
        return None, "no_data"
    rows = []
    for b in bars:
        ts = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        ts_et = ts.astimezone(ET_OFFSET).replace(tzinfo=None)
        rows.append({"timestamp_et": ts_et, "open": b["o"], "high": b["h"],
                     "low": b["l"], "close": b["c"], "volume": b.get("v", 0)})
    df = pd.DataFrame(rows).sort_values("timestamp_et").reset_index(drop=True)
    HIGHRES_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    return df, "rest_fetch"
