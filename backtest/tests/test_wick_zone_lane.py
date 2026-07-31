"""Guards for the WICK-ENTRY-LANE detector (shelf_wick_hold_closed_bar_v1).

Pre-reg: analysis/recommendations/prereg-wick-lane-2026-07-31.json (frozen 2026-07-31
16:47:56 ET). Fixtures below are the REAL SIP 5m bars quoted verbatim in the pre-reg's
incident_capture_check (fetched live 2026-07-31 via the levels-compiler-v2 feed) -- the
two motivating incidents J called, both OUTSIDE the study's P&L population.

RED-proof design: every clause F1-F4 has a test that flips exactly that clause on the
firing fixture and asserts NO fire -- so a regression that drops any clause (e.g. someone
"simplifies" the predicate into the graveyard ZONE-WIDTH widened-cross shape, which the
12:40 bar test would catch) turns this suite RED.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from wick_zone_lane import (  # noqa: E402
    classify_persistent,
    detect_shelf_wick_hold_bear,
    detect_shelf_wick_hold_bull,
    shelf_zones_for_session,
    zones_overlap,
)

# The shelf in force on 2026-07-30 AND 2026-07-31 (recomputed from daily SIP bars through
# the production pipeline; live key-levels.json carried the same shelf as 737.05-738.65
# from a slightly different fetch window -- 2c apart, same zone).
SHELF = {"band_low": 737.03, "band_high": 738.63}
OVERHEAD = {"band_low": 738.93, "band_high": 740.53}

# REAL SIP bars (see module docstring).
BAR_0731_1015 = {"open": 738.47, "high": 739.50, "low": 737.68, "close": 738.61}  # fires
BAR_0730_1240 = {"open": 738.51, "high": 738.54, "low": 737.75, "close": 738.03}  # F3 fails
BAR_0730_1245 = {"open": 738.04, "high": 738.75, "low": 738.00, "close": 738.56}  # fires


# ------------------------------------------------------------------ incident capture (G6)

def test_bull_fires_on_0731_1015_incident():
    z = detect_shelf_wick_hold_bull(BAR_0731_1015, [SHELF])
    assert z is not None and z["band_low"] == 737.03


def test_bull_does_not_fire_on_0730_1240_close_in_zone():
    # close 738.03 sits mid-zone. This real bar fails BOTH F3 (close < 738.53 recovery
    # line) AND F4 (wick 0.28 < 0.395 threshold) -- documented as-is; the single-clause
    # F3 discriminator lives in test_f3_close_not_recovered_pure below.
    assert detect_shelf_wick_hold_bull(BAR_0730_1240, [SHELF]) is None


def test_bull_fires_on_0730_1245_recovery_bar():
    z = detect_shelf_wick_hold_bull(BAR_0730_1245, [SHELF])
    assert z is not None and z["band_low"] == 737.03


# ------------------------------------------------------------------ clause RED-proofs

def test_f1_open_below_zone_is_breakout_not_test():
    bar = dict(BAR_0731_1015, open=736.90)  # opens below band_low 737.03
    assert detect_shelf_wick_hold_bull(bar, [SHELF]) is None


def test_f2_low_never_reaches_zone():
    bar = dict(BAR_0731_1015, low=738.70)  # low above band_high 738.63, wick kept large
    bar["close"] = 739.45                   # keep F3/F4 satisfiable (wick 0.75, range 0.80)
    assert detect_shelf_wick_hold_bull(bar, [SHELF]) is None


def test_f3_close_not_recovered_pure():
    # SINGLE-CLAUSE discriminator (first RED-proof pass caught the original fixture being
    # masked by F4): big wick so F4 passes (1.30 >= 0.85), F1/F2 pass, ONLY F3 fails
    # (close 738.30 < 738.53). A regression that drops F3 -- the graveyard widened-cross
    # shape, which admits bars that never recovered the zone top -- turns THIS test red.
    bar = {"open": 738.60, "high": 738.70, "low": 737.00, "close": 738.30}
    assert detect_shelf_wick_hold_bull(bar, [SHELF]) is None


def test_f4_wick_not_significant():
    # close recovered but wick tiny relative to range: low barely under band_high
    bar = {"open": 739.00, "high": 740.40, "low": 738.60, "close": 738.63}
    # wick = 0.03 < max(0.15, 0.5*1.80) -> no fire
    assert detect_shelf_wick_hold_bull(bar, [SHELF]) is None


def test_zero_range_bar_no_fire():
    bar = {"open": 738.60, "high": 738.60, "low": 738.60, "close": 738.60}
    assert detect_shelf_wick_hold_bull(bar, [SHELF]) is None


def test_tiebreak_highest_band_high():
    lower = {"band_low": 735.03, "band_high": 736.63}
    bar = {"open": 738.47, "high": 739.50, "low": 736.50, "close": 739.30}
    # wick 2.80 >= 0.5*3.00; both zones touched (low 736.50 <= 736.63 and <= 738.63),
    # close 739.30 recovers both tops; open above both band_lows
    z = detect_shelf_wick_hold_bull(bar, [SHELF, lower])
    assert z is not None and z["band_high"] == 738.63


# ------------------------------------------------------------------ bear mirror

def test_bear_fires_on_mirrored_incident():
    # mirror of the 10:15 bar around the overhead shelf: wick UP into [738.93, 740.53],
    # close back under band_low + 0.10
    bar = {"open": 739.10, "high": 739.90, "low": 738.10, "close": 738.97}
    z = detect_shelf_wick_hold_bear(bar, [OVERHEAD])
    assert z is not None and z["band_high"] == 740.53


def test_bear_close_in_zone_no_fire():
    bar = {"open": 739.10, "high": 740.40, "low": 739.05, "close": 739.60}  # close mid-zone
    assert detect_shelf_wick_hold_bear(bar, [OVERHEAD]) is None


def test_real_1015_bar_does_not_fire_bear_on_overhead():
    # the real incident bar ALSO poked the overhead shelf (H 739.50 >= 738.93) but its
    # upper wick 0.89 misses the 0.91 threshold -- locks the observed near-collision fact
    assert detect_shelf_wick_hold_bear(BAR_0731_1015, [OVERHEAD]) is None


# ------------------------------------------------------------------ persistence + zones

def test_classify_persistent_keeps_overlap_drops_fresh():
    today = [{"band_low": 734.30, "band_high": 735.90}, {"band_low": 720.00, "band_high": 721.60}]
    prior = [{"band_low": 735.03, "band_high": 736.63}]
    kept = classify_persistent(today, prior)
    assert kept == [today[0]]
    assert zones_overlap(today[0], prior[0]) and not zones_overlap(today[1], prior[0])


def _mk_daily(dates_prices):
    return [{"date": d, "o": p, "h": p + 0.5, "l": p - 0.5, "c": p, "v": 1e6}
            for d, p in dates_prices]


def test_shelf_zones_for_session_excludes_same_day_bar():
    # 12 sessions clustering at 700 strictly before D, plus a SAME-DAY bar at a distant
    # price that would seed a spurious extra candidate if leaked in (C6 look-ahead guard)
    base = dt.date(2026, 6, 1)
    rows = [((base + dt.timedelta(days=i)).isoformat(), 700.0 + (i % 3) * 0.3) for i in range(14)]
    bars = _mk_daily(rows)
    session = dt.date(2026, 7, 1)
    with_leak = bars + _mk_daily([(session.isoformat(), 900.0)])
    zs_clean = shelf_zones_for_session(bars, session)
    zs_leak = shelf_zones_for_session(with_leak, session)
    assert zs_clean == zs_leak                      # same-day bar must be invisible
    assert all(z["band_high"] < 800 for z in zs_clean)


def test_shelf_zones_for_session_60d_window():
    # bars older than 60 calendar days before the session must not contribute
    old = _mk_daily([((dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat(), 650.0) for i in range(14)])
    recent = _mk_daily([((dt.date(2026, 6, 1) + dt.timedelta(days=i)).isoformat(), 700.0) for i in range(14)])
    zs = shelf_zones_for_session(old + recent, dt.date(2026, 7, 1))
    assert zs and all(z["band_low"] > 690 for z in zs)
