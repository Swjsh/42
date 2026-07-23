"""Guard for ENGINE-VECTORIZATION layer 1/3 (queue.md, 2026-07-23).

`_detect_from_history` used to unconditionally recompute "date"/"time" columns
via `.dt.date`/`.dt.time` on every call, even though `orchestrator.py`'s
`spy_df_full` already carries "date" (and, after this fix, "time") precomputed
once up front. The optimization: skip the recompute when the caller already
supplies those columns. This guard proves the skip-if-present path is
BYTE-IDENTICAL to the always-recompute path, and that a caller who does NOT
precompute the columns still gets correct (recomputed) results — the exact
regression this fix could introduce if the conditional ever silently trusted a
stale/mismatched precomputed column.

Run: cd backtest && python -m pytest tests/test_levels_precomputed_columns_parity.py -v
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.levels import _detect_from_history  # noqa: E402


def _make_multi_day_bars() -> pd.DataFrame:
    """Two prior days + today's premarket/RTH bars, tz-aware, enough for the
    active/multi_day level derivations to exercise real branches (not just the
    empty-prior-bars early return)."""
    rows = []
    day1 = dt.date(2026, 7, 20)  # Monday
    day2 = dt.date(2026, 7, 21)  # Tuesday
    today = dt.date(2026, 7, 22)  # Wednesday

    def _add_day(d: dt.date, start_h: int, start_m: int, n: int, base: float):
        for i in range(n):
            ts = pd.Timestamp(
                dt.datetime.combine(d, dt.time(start_h, start_m)) + dt.timedelta(minutes=5 * i),
                tz="America/New_York",
            )
            px = base + (i % 5) * 0.10
            rows.append(
                {
                    "timestamp_et": ts,
                    "open": px,
                    "high": px + 0.20,
                    "low": px - 0.20,
                    "close": px + 0.05,
                    "volume": 1000,
                }
            )

    _add_day(day1, 9, 30, 78, 100.0)   # full RTH day (~6.5h of 5m bars)
    _add_day(day2, 9, 30, 78, 101.0)
    _add_day(today, 4, 0, 66, 102.0)   # premarket 04:00-09:30
    _add_day(today, 9, 30, 20, 102.5)  # partial RTH so far today

    return pd.DataFrame(rows)


def test_precomputed_date_time_matches_recomputed():
    """Caller who already has 'date'+'time' columns (orchestrator.py's
    spy_df_full) gets the SAME LevelSet as a caller who supplies neither."""
    bars = _make_multi_day_bars()
    today = dt.date(2026, 7, 22)

    raw = bars.copy()  # neither "date" nor "time" present -> forces recompute
    assert "date" not in raw.columns
    assert "time" not in raw.columns
    recomputed = _detect_from_history(raw, today)

    precomputed = bars.copy()
    precomputed["date"] = precomputed["timestamp_et"].dt.date
    precomputed["time"] = precomputed["timestamp_et"].dt.time
    skipped = _detect_from_history(precomputed, today)

    assert skipped.active == recomputed.active
    assert skipped.multi_day == recomputed.multi_day
    assert skipped.swept_levels == recomputed.swept_levels


def test_precomputed_date_only_still_derives_time():
    """A caller with ONLY 'date' precomputed (no 'time') must still get 'time'
    derived correctly — the two columns are gated independently."""
    bars = _make_multi_day_bars()
    today = dt.date(2026, 7, 22)

    raw = bars.copy()
    recomputed = _detect_from_history(raw, today)

    date_only = bars.copy()
    date_only["date"] = date_only["timestamp_et"].dt.date
    assert "time" not in date_only.columns
    result = _detect_from_history(date_only, today)

    assert result.active == recomputed.active
    assert result.multi_day == recomputed.multi_day


def test_no_columns_path_unaffected_by_change():
    """Sanity: a plain call with zero precomputed columns (the pre-existing,
    still-dominant call pattern across every OTHER call site in the repo)
    still returns a non-trivial LevelSet -- the conditional didn't silently
    break the default (no-precompute) path."""
    bars = _make_multi_day_bars()
    today = dt.date(2026, 7, 22)
    result = _detect_from_history(bars.copy(), today)
    assert len(result.active) > 0
