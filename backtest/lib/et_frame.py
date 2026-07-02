"""Canonical timestamp_et frame conventions — the DST wall-time artifact fix.

BACKGROUND (found 2026-07-02 during WIRE-BOLLINGER; see
markdown/audits/DST-FRAME-AUDIT-2026-07-02.md):

The SPY master CSVs (backtest/data/spy_5m_*.csv) and the OPRA option cache
(backtest/data/options/*.csv) store timestamps with a FIXED ``-04:00`` offset
year-round (writer bug: tools/extend_data_v2.py subtracted a constant 4h from
UTC and stamped a hardcoded suffix). The UTC INSTANT of every row is correct;
the offset LABEL is wrong for EST months (Nov-Mar). The VIX master is NOT
affected (its writer uses a real tz_convert + %z).

Consequently there are two parse conventions in the wild:

  wall-v1  pd.to_datetime(col) then tz-strip -> KEEPS WALL TIME.
           EST-month sessions read 10:30..16:55 wall (= true 09:30..15:55 ET),
           so an RTH slice [09:30, 16:00) CLIPS THE LAST TRUE TRADING HOUR
           and every winter bar label is +1h vs true ET. 129 of the 365
           trading days in the 2025-01-01..2026-06-18 master are EST days.
           This is the convention every wall-v1-era scorecard was built on.

  et-v2    pd.to_datetime(col, utc=True).tz_convert("America/New_York") then
           tz-strip -> TRUE ET wall time, DST-correct. Full 78-bar RTH
           sessions year-round.

Joins MUST be frame-consistent: SPY bars and OPRA option bars share the fixed
-04:00 storage, so a wall-v1 SPY frame joined to a wall-v1 option frame hits
the SAME UTC instants (prices were never misaligned — only mislabeled and
clipped). Mixing frames across a join misaligns winter data by 1 hour.
NEVER join a naive et-v2 series against a naive wall-v1 series.

MIGRATION DISCIPLINE (no silent swap): defaults everywhere stay ``wall-v1``
until the frame re-validation diffs are filed under analysis/frame-migration/
(runner: autoresearch/frame_migration_revalidate.py). Pipelines opt in to
``et-v2`` explicitly; guard tests pin BOTH conventions' behavior on a known
winter day (backtest/tests/test_et_frame_guards.py).
"""

from __future__ import annotations

import pandas as pd

FRAME_WALL_V1 = "wall-v1"
FRAME_ET_V2 = "et-v2"

# Default for every consumer until the re-validation plan flips it (Phase B).
DEFAULT_FRAME = FRAME_WALL_V1

_VALID_FRAMES = (FRAME_WALL_V1, FRAME_ET_V2)

ET_TZ = "America/New_York"


def parse_timestamp_et(series: pd.Series, frame: str = DEFAULT_FRAME) -> pd.Series:
    """Parse a timestamp_et string column to a TZ-NAIVE datetime series.

    frame="wall-v1": legacy — parse the stored offset, strip tz, keep wall time
                     (byte-identical to the historical build_rth behavior).
    frame="et-v2":   DST-correct — parse to UTC, convert to America/New_York,
                     strip tz. True ET wall time year-round.

    Already-parsed datetime input passes through (naive input is returned
    as-is under BOTH frames — the frame distinction only exists while the
    stored offset string is still attached).
    """
    if frame not in _VALID_FRAMES:
        raise ValueError(f"unknown timestamp frame {frame!r}; expected one of {_VALID_FRAMES}")
    if frame == FRAME_ET_V2:
        ts = pd.to_datetime(series, utc=True)
        return ts.dt.tz_convert(ET_TZ).dt.tz_localize(None)
    ts = pd.to_datetime(series)
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    return ts
