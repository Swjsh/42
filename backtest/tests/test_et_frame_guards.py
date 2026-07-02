"""Graduated guards for the DST wall-time frame artifact (2026-07-02).

Root cause: tools/extend_data_v2.py wrote the SPY master with a FIXED -04:00
offset year-round (UTC instant correct, offset label wrong Nov-Mar). Every
naive parse + tz-strip ("wall-v1") therefore reads EST-month sessions as
10:30..16:55 wall — the RTH slice [09:30, 16:00) clips the last true trading
hour and all winter bar labels sit +1h vs true ET. 129 of 365 trading days in
the 2025-01-01..2026-06-18 master are EST days.

These guards pin BOTH conventions on known winter/summer days so that:
  - wall-v1 stays byte-reproducible (comparability with every pre-fix scorecard),
  - et-v2 provably restores the full 78-bar winter session,
  - the SPY<->OPRA join can never silently mix frames,
  - the writer can never regress to a hardcoded offset.

Full audit: markdown/audits/DST-FRAME-AUDIT-2026-07-02.md
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

_BACKTEST = Path(__file__).resolve().parents[1]
if str(_BACKTEST) not in sys.path:
    sys.path.insert(0, str(_BACKTEST))

from lib.et_frame import (  # noqa: E402
    DEFAULT_FRAME,
    FRAME_ET_V2,
    FRAME_WALL_V1,
    parse_timestamp_et,
)

DATA = _BACKTEST / "data"
MASTER = DATA / "spy_5m_2025-01-01_2026-06-18.csv"
VIX_MASTER = DATA / "vix_5m_2025-01-01_2026-06-18.csv"
WINTER_OPRA = DATA / "options" / "SPY250102C00580000.csv"

WINTER_DAY = dt.date(2025, 1, 7)   # EST (offset label -04:00 in master = wrong)
SUMMER_DAY = dt.date(2025, 7, 7)   # EDT (offset label correct)

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)

needs_master = pytest.mark.skipif(not MASTER.exists(), reason=f"master CSV missing: {MASTER}")


def _rth_times(ts: pd.Series, day: dt.date) -> pd.Series:
    mask = (ts.dt.date == day) & (ts.dt.time >= RTH_OPEN) & (ts.dt.time < RTH_CLOSE)
    return ts[mask]


@pytest.fixture(scope="module")
def spy_master() -> pd.DataFrame:
    return pd.read_csv(MASTER)


def test_default_frame_is_wall_v1_until_migration():
    """Phase A of the DST fix: defaults MUST stay legacy until the frame
    re-validation diffs are filed under analysis/frame-migration/ (no silent
    swap). The Phase B commit that flips the default must update this guard
    AND cite the filed diff report."""
    assert DEFAULT_FRAME == FRAME_WALL_V1


@needs_master
def test_wall_v1_pins_legacy_winter_clip(spy_master):
    """wall-v1 must stay byte-reproducible: winter day = 66 RTH bars starting
    10:30 wall (the clipped frame every pre-2026-07-02 scorecard was built on)."""
    ts = parse_timestamp_et(spy_master["timestamp_et"], FRAME_WALL_V1)
    rth = _rth_times(ts, WINTER_DAY)
    assert len(rth) == 66
    assert rth.iloc[0].time() == dt.time(10, 30)
    assert rth.iloc[-1].time() == dt.time(15, 55)


@needs_master
def test_et_v2_restores_full_winter_session(spy_master):
    """et-v2 must recover the true 78-bar 09:30..15:55 winter session."""
    ts = parse_timestamp_et(spy_master["timestamp_et"], FRAME_ET_V2)
    rth = _rth_times(ts, WINTER_DAY)
    assert len(rth) == 78
    assert rth.iloc[0].time() == dt.time(9, 30)
    assert rth.iloc[-1].time() == dt.time(15, 55)


@needs_master
def test_summer_day_identical_across_frames(spy_master):
    """EDT months: the stored -04:00 label is correct, so both frames must
    agree bar-for-bar (this is why summer-only re-verifications were valid)."""
    wall = _rth_times(parse_timestamp_et(spy_master["timestamp_et"], FRAME_WALL_V1), SUMMER_DAY)
    etv2 = _rth_times(parse_timestamp_et(spy_master["timestamp_et"], FRAME_ET_V2), SUMMER_DAY)
    assert len(wall) == len(etv2) > 0
    assert (wall.to_numpy() == etv2.to_numpy()).all()


@needs_master
def test_build_rth_threads_frame(spy_master):
    from autoresearch.family_detectors import build_rth

    day_rows = spy_master[spy_master["timestamp_et"].str.startswith(str(WINTER_DAY))]
    legacy = build_rth(day_rows)                        # default = wall-v1
    fixed = build_rth(day_rows, frame=FRAME_ET_V2)
    assert len(legacy) == 66 and legacy["t"].iloc[0] == dt.time(10, 30)
    assert len(fixed) == 78 and fixed["t"].iloc[0] == dt.time(9, 30)


@needs_master
@pytest.mark.skipif(not WINTER_OPRA.exists(), reason=f"OPRA cache missing: {WINTER_OPRA}")
def test_opra_join_frame_consistent(spy_master):
    """The SPY->OPRA entry-bar lookup must select the SAME option bar (same UTC
    instant / same row) whether the whole pipeline runs wall-v1 or et-v2.
    Mixing frames across the join would misalign EST months by 1h — this guard
    proves same-frame joins are instant-equivalent."""
    from lib.option_pricing_real import bar_at_or_after

    opra_raw = pd.read_csv(WINTER_OPRA)
    day = dt.date(2025, 1, 2)  # the contract's 0DTE session (EST day)

    # Both frames' RTH slices START at the same true bar (true 09:30); wall-v1 is
    # a 66-bar truncation of et-v2's 78. Positional index i < 66 therefore refers
    # to the SAME underlying UTC bar in both frames — compare picks for those.
    picks = {}
    for frame in (FRAME_WALL_V1, FRAME_ET_V2):
        spy_ts = _rth_times(parse_timestamp_et(spy_master["timestamp_et"], frame), day)
        opt = opra_raw.copy()
        opt["timestamp_et"] = parse_timestamp_et(opt["timestamp_et"], frame)
        # entry fills on the next bar after the trigger bar (simulator convention)
        rows = []
        for pos in (0, 30, 65):
            when = spy_ts.iloc[pos].to_pydatetime() + dt.timedelta(minutes=5)
            bar = bar_at_or_after(opt, when)
            # map the picked bar back to its positional row (frame-independent identity)
            rows.append(None if bar is None else
                        int((opt["timestamp_et"] == pd.Timestamp(bar.timestamp_et)).idxmax()))
        picks[frame] = rows

    assert picks[FRAME_WALL_V1] == picks[FRAME_ET_V2], (
        f"frame-inconsistent OPRA join: wall-v1 picked rows {picks[FRAME_WALL_V1]} "
        f"vs et-v2 rows {picks[FRAME_ET_V2]}"
    )


def test_writer_emits_real_dst_offsets():
    """extend_data_v2 must never regress to `utc - 4h` + hardcoded '-04:00'.
    EST instant -> -0500 label; EDT instant -> -0400 label."""
    tools_dir = _BACKTEST / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from extend_data_v2 import utc_iso_to_et_string

    assert utc_iso_to_et_string("2025-01-07T14:30:00Z") == "2025-01-07 09:30:00-0500"
    assert utc_iso_to_et_string("2025-07-07T13:30:00Z") == "2025-07-07 09:30:00-0400"


@pytest.mark.skipif(not VIX_MASTER.exists(), reason=f"VIX master missing: {VIX_MASTER}")
def test_vix_master_offsets_are_dynamic():
    """The VIX master was never affected (its writer always used a real
    tz_convert + %z). Guard the asymmetry the audit documented: VIX winter rows
    carry -0500. If this ever fails, a VIX regeneration used the broken SPY
    writer path — naive SPY<->VIX joins would then silently change meaning."""
    vix = pd.read_csv(VIX_MASTER)
    winter = vix[vix["timestamp_et"].str.startswith("2025-01-07")]
    assert len(winter) > 0
    assert winter["timestamp_et"].str.contains(r"-05:?00$", regex=True).all()
