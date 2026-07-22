"""Guard tests for backtest/tools/pullback_hold_bull_v2.py -- PULLBACK-HOLD-BULL-TRIGGER
ITERATION 2.

Pre-reg: analysis/recommendations/pullback-hold-bull-prereg-v2-2026-07-22.json

RED-proofs:
  - impulse-leg math against hand-computed synthetic fixtures (M/R/undercut gates each
    isolated).
  - no-look-ahead (C6): truncating the extended-bar frame right after a candidate bar
    reproduces the identical ImpulseLegBar; the candidate's own low is the only "current"
    information ever consulted.
  - both of J's named 2026-07-21/07-22 exhibits fire from REAL cached SPY 5m bars (not
    synthetic) inside their pre-registered anchor windows, on the shipping-candidate
    impulse_leg_mode (K24_M1.00_R0.786) -- and do NOT fire on the deliberately-too-tight
    R=0.618 variant at anchor_1 (the pre-registered asymmetry).
  - selectivity qualifiers (PRIOR_INTERACTION, LEG_ORIGIN) unit-tested in isolation.
  - frequency disclosure (entries/day) helper is present and correct.
"""
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools.pullback_hold_bull_v2 import (  # noqa: E402
    ImpulseLegParams,
    PullbackHoldV2Params,
    detect_pullback_hold_bull_v2,
    impulse_leg_series,
    leg_origin_match_ok,
    prior_same_day_touch_ok,
)

ET = timezone(timedelta(hours=-4))
REPO_ROOT = Path(__file__).resolve().parents[2]
SPY_CSV = REPO_ROOT / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-22.csv"


def _bars(rows: list[tuple], start=datetime(2026, 1, 5, 9, 30, tzinfo=ET), step_min=5) -> pd.DataFrame:
    """rows: list of (open, high, low, close[, volume]) tuples, one per bar."""
    out = []
    for i, row in enumerate(rows):
        o, h, l, c = row[0], row[1], row[2], row[3]
        v = row[4] if len(row) > 4 else 1000.0
        out.append({
            "timestamp_et": start + timedelta(minutes=step_min * i),
            "open": o, "high": h, "low": l, "close": c, "volume": v,
        })
    return pd.DataFrame(out)


def _leg_params(**kw) -> ImpulseLegParams:
    base = dict(k_bars=4, min_leg_dollars=1.0, max_retrace_pct=0.786)
    base.update(kw)
    return ImpulseLegParams(**base)


# =====================================================================================
# Impulse-leg math -- synthetic, hand-computed
# =====================================================================================
def test_impulse_leg_basic_math_matches_hand_calc():
    # 4 bars of premarket "extension" context, then the RTH candidate bar.
    # Window (K=4) closes: 100.0, 100.5, 101.0, 102.0 -> leg_high = max(close) = 102.0
    # leg_origin_low = low of window's FIRST bar = 99.8
    # leg_dollars = 102.0 - 99.8 = 2.2
    # candidate bar low = 100.5 -> retrace = (102.0-100.5)/2.2 = 0.6818
    ext = _bars([
        (99.9, 100.1, 99.8, 100.0),
        (100.0, 100.6, 99.95, 100.5),
        (100.5, 101.1, 100.4, 101.0),
        (101.0, 102.1, 100.9, 102.0),
        (102.0, 102.2, 100.5, 101.8),   # candidate bar: low=100.5
    ], start=datetime(2026, 1, 5, 9, 10, tzinfo=ET))
    rth = ext.iloc[[4]].reset_index(drop=True)

    out = impulse_leg_series(ext, rth, _leg_params(k_bars=4, min_leg_dollars=1.0, max_retrace_pct=0.786))
    assert len(out) == 1
    b = out[0]
    assert b.leg_high == pytest.approx(102.0)
    assert b.leg_origin_low == pytest.approx(99.8)
    assert b.leg_dollars == pytest.approx(2.2)
    assert b.retrace_pct == pytest.approx(0.6818, abs=1e-3)
    assert b.ok is True


def test_impulse_leg_rejects_leg_too_small_M():
    ext = _bars([
        (99.9, 100.1, 99.8, 100.0),
        (100.0, 100.4, 99.95, 100.3),
        (100.3, 100.6, 100.2, 100.5),
        (100.5, 100.7, 100.4, 100.6),   # leg only ~0.9 dollars
        (100.6, 100.7, 100.3, 100.4),
    ], start=datetime(2026, 1, 5, 9, 10, tzinfo=ET))
    rth = ext.iloc[[4]].reset_index(drop=True)
    out = impulse_leg_series(ext, rth, _leg_params(k_bars=4, min_leg_dollars=1.0, max_retrace_pct=0.99))
    assert out[0].ok is False
    assert out[0].leg_dollars < 1.0


def test_impulse_leg_rejects_deep_retrace_R():
    # leg_dollars big enough, but pullback retraces almost the whole leg (>R).
    ext = _bars([
        (99.9, 100.1, 99.8, 100.0),
        (100.0, 100.6, 99.95, 100.5),
        (100.5, 101.1, 100.4, 101.0),
        (101.0, 102.1, 100.9, 102.0),
        (102.0, 102.2, 99.95, 100.0),   # candidate bar: low=99.95, almost fully retraced
    ], start=datetime(2026, 1, 5, 9, 10, tzinfo=ET))
    rth = ext.iloc[[4]].reset_index(drop=True)
    out = impulse_leg_series(ext, rth, _leg_params(k_bars=4, min_leg_dollars=1.0, max_retrace_pct=0.786))
    assert out[0].ok is False
    assert out[0].retrace_pct > 0.786


def test_impulse_leg_rejects_undercut_of_origin():
    # pullback low DROPS BELOW the leg's own origin low -- not a higher low, must fail
    # regardless of R.
    ext = _bars([
        (99.9, 100.1, 99.8, 100.0),
        (100.0, 100.6, 99.95, 100.5),
        (100.5, 101.1, 100.4, 101.0),
        (101.0, 102.1, 100.9, 102.0),
        (102.0, 102.2, 99.5, 99.8),   # candidate low 99.5 < origin 99.8 -- undercut
    ], start=datetime(2026, 1, 5, 9, 10, tzinfo=ET))
    rth = ext.iloc[[4]].reset_index(drop=True)
    out = impulse_leg_series(ext, rth, _leg_params(k_bars=4, min_leg_dollars=1.0, max_retrace_pct=0.99))
    assert out[0].ok is False


def test_impulse_leg_insufficient_history_reads_false():
    ext = _bars([
        (100.0, 100.2, 99.9, 100.1),
        (100.1, 100.3, 100.0, 100.2),
    ], start=datetime(2026, 1, 5, 9, 25, tzinfo=ET))
    rth = ext.iloc[[1]].reset_index(drop=True)  # only 1 bar of history available, K=4 needed
    out = impulse_leg_series(ext, rth, _leg_params(k_bars=4))
    assert out[0].ok is False
    assert out[0].leg_high is None


def test_impulse_leg_R_asymmetry_matches_prereg_grid():
    """The exact asymmetry named in the mission: at a fixed leg, R=0.786 passes a ~75%
    retrace while R=0.618 does not."""
    ext = _bars([
        (99.9, 100.1, 99.8, 100.0),
        (100.0, 100.6, 99.95, 100.5),
        (100.5, 101.1, 100.4, 101.0),
        (101.0, 102.1, 100.9, 102.0),
        (102.0, 102.2, 100.55, 100.9),  # retrace = (102.0-100.55)/2.2 = 0.659
    ], start=datetime(2026, 1, 5, 9, 10, tzinfo=ET))
    rth = ext.iloc[[4]].reset_index(drop=True)
    loose = impulse_leg_series(ext, rth, _leg_params(k_bars=4, max_retrace_pct=0.786))
    tight = impulse_leg_series(ext, rth, _leg_params(k_bars=4, max_retrace_pct=0.618))
    assert loose[0].retrace_pct == pytest.approx(0.659, abs=1e-3)
    assert loose[0].ok is True
    assert tight[0].ok is False


# =====================================================================================
# No-look-ahead (C6)
# =====================================================================================
def test_impulse_leg_no_look_ahead_truncation():
    ext_full = _bars([
        (99.9, 100.1, 99.8, 100.0),
        (100.0, 100.6, 99.95, 100.5),
        (100.5, 101.1, 100.4, 101.0),
        (101.0, 102.1, 100.9, 102.0),
        (102.0, 102.2, 100.5, 101.8),    # candidate bar (idx4)
        (101.8, 108.0, 101.5, 107.0),    # FUTURE bar -- must never affect idx4's read
        (107.0, 109.0, 106.0, 108.0),    # another future bar
    ], start=datetime(2026, 1, 5, 9, 10, tzinfo=ET))
    rth_full = ext_full.iloc[[4]].reset_index(drop=True)
    params = _leg_params(k_bars=4)

    full = impulse_leg_series(ext_full, rth_full, params)
    truncated = impulse_leg_series(ext_full.iloc[:5].reset_index(drop=True), rth_full, params)
    assert full[0].leg_high == truncated[0].leg_high
    assert full[0].leg_origin_low == truncated[0].leg_origin_low
    assert full[0].retrace_pct == truncated[0].retrace_pct
    assert full[0].ok == truncated[0].ok is True


# =====================================================================================
# Selectivity qualifiers
# =====================================================================================
def test_prior_same_day_touch_ok_requires_earlier_bar():
    day = _bars([
        (100.5, 100.6, 100.4, 100.5),   # bar0: nowhere near the level
        (100.3, 100.4, 99.98, 100.1),   # bar1: touches level 100.0 (low 99.98, within 0.20)
        (100.1, 100.2, 100.0, 100.15),  # bar2: candidate -- prior touch at bar1 exists
    ])
    assert prior_same_day_touch_ok(day, 100.0, before_idx=2) is True
    # Same level, but checked BEFORE any touch happened (before_idx=1 -> only bar0 inspected)
    assert prior_same_day_touch_ok(day, 100.0, before_idx=1) is False


def test_leg_origin_match_ok_band_tolerance():
    assert leg_origin_match_ok(100.10, leg_origin_low=100.00, tol=0.15) is True
    assert leg_origin_match_ok(100.30, leg_origin_low=100.00, tol=0.15) is False
    assert leg_origin_match_ok(100.10, leg_origin_low=None, tol=0.15) is False


# =====================================================================================
# Full detector walk
#
# All "full walk" fixtures share ONE antecedent leg shape: 8 flat-base (low=90.0) bars
# with closes ramping 91->102 (a clean $12 leg), used with k_bars=8 so the leg window
# never slides into the RTH candidate bars themselves across a short RTH sequence (a
# window that DID slide into recent RTH bars would keep raising leg_origin_low bar by
# bar and spuriously undercut a flat/consolidating pullback -- an artifact of a too-short
# K relative to the fixture's length, not a real detector bug; k_bars=8 sidesteps it).
# =====================================================================================
_ANTECEDENT_LEG = [
    (90.0, 91.2, 90.0, 91.0),
    (91.0, 93.2, 90.0, 93.0),
    (93.0, 95.2, 90.0, 95.0),
    (95.0, 97.2, 90.0, 97.0),
    (97.0, 99.2, 90.0, 99.0),
    (99.0, 100.2, 90.0, 100.0),
    (100.0, 101.2, 90.0, 101.0),
    (101.0, 102.2, 90.0, 102.0),
]  # closes ramp 91..102, every bar's own low pinned at 90.0 -- leg_dollars == 12.0 always


def _v2_params(**kw) -> PullbackHoldV2Params:
    base = dict(impulse_leg_mode="K8_M1.00_R0.786", k_bars=8, min_leg_dollars=1.0,
                max_retrace_pct=0.786, selectivity_mode="PRIOR_INTERACTION",
                zone_band_cents=0.25, hold_bars_n=1)
    base.update(kw)
    return PullbackHoldV2Params(**base)


def _leg_series_for(ext: pd.DataFrame, rth: pd.DataFrame, **leg_kw):
    p = _leg_params(k_bars=8, max_retrace_pct=0.99)
    if leg_kw:
        p = ImpulseLegParams(k_bars=leg_kw.get("k_bars", p.k_bars),
                              min_leg_dollars=leg_kw.get("min_leg_dollars", p.min_leg_dollars),
                              max_retrace_pct=leg_kw.get("max_retrace_pct", p.max_retrace_pct))
    return impulse_leg_series(ext, rth, p)


def test_detect_basic_fire_with_prior_interaction():
    # rth0: FIRST touch of level 100.0 (low 99.85) -- selectivity rejects it (no prior touch
    # exists yet, before_idx=0 is always empty). rth1: a FRESH candidate, prior-touch now
    # satisfied by rth0 -> reclaims at rth1 itself (close 100.30 > zone_top 100.25).
    ext = _bars(_ANTECEDENT_LEG + [
        (100.3, 100.4, 99.85, 99.95),    # rth0: seed touch, rejected by selectivity (no prior)
        (99.95, 100.35, 99.90, 100.30),  # rth1: candidate + same-bar reclaim
    ], start=datetime(2026, 1, 5, 9, 10, tzinfo=ET))
    rth = ext.iloc[8:].reset_index(drop=True)
    leg_out = _leg_series_for(ext, rth)

    sigs = detect_pullback_hold_bull_v2(
        rth, up_structure_ok=[b.ok for b in leg_out],
        leg_origin_lows=[b.leg_origin_low for b in leg_out], leg_highs=[b.leg_high for b in leg_out],
        retrace_pcts=[b.retrace_pct for b in leg_out], levels_at=lambda i: [100.0],
        params=_v2_params(zone_band_cents=0.25, hold_bars_n=1), day_label="2026-01-05")
    assert len(sigs) == 1
    assert sigs[0].pullback_bar_idx == 1
    assert sigs[0].entry_bar_idx == 1


def test_detect_no_fire_without_prior_interaction():
    """Only ONE rth bar total -- it is the first-ever touch of the level, so there is no
    prior same-day interaction yet -> selectivity blocks it even though it reclaims."""
    ext = _bars(_ANTECEDENT_LEG + [
        (99.95, 100.35, 99.90, 100.30),  # rth0: first-ever touch AND reclaim -- still blocked
    ], start=datetime(2026, 1, 5, 9, 10, tzinfo=ET))
    rth = ext.iloc[8:].reset_index(drop=True)
    leg_out = _leg_series_for(ext, rth)

    sigs = detect_pullback_hold_bull_v2(
        rth, up_structure_ok=[b.ok for b in leg_out],
        leg_origin_lows=[b.leg_origin_low for b in leg_out], leg_highs=[b.leg_high for b in leg_out],
        retrace_pcts=[b.retrace_pct for b in leg_out], levels_at=lambda i: [100.0],
        params=_v2_params(zone_band_cents=0.25, hold_bars_n=1), day_label="2026-01-05")
    assert sigs == []


def test_detect_leg_origin_selectivity_matches_own_leg():
    # level == leg origin low (within band) -> should fire under LEG_ORIGIN even with
    # zero prior same-day touches. Pullback low (90.08) sits just above the leg origin
    # (90.0, the antecedent's own flat base) and inside a tight 0.10 zone band.
    ext = _bars(_ANTECEDENT_LEG + [
        (90.08, 90.20, 90.08, 90.05),   # rth bar0: pullback low 90.08, right at the origin
        (90.05, 101.7, 90.02, 101.6),   # rth bar1: reclaim
    ], start=datetime(2026, 1, 5, 9, 10, tzinfo=ET))
    rth = ext.iloc[8:].reset_index(drop=True)
    leg_out = _leg_series_for(ext, rth, max_retrace_pct=0.995)

    level = 90.00  # == leg_origin_low (every antecedent bar's low, by construction)
    sigs = detect_pullback_hold_bull_v2(
        rth, up_structure_ok=[b.ok for b in leg_out],
        leg_origin_lows=[b.leg_origin_low for b in leg_out], leg_highs=[b.leg_high for b in leg_out],
        retrace_pcts=[b.retrace_pct for b in leg_out], levels_at=lambda i: [level],
        params=_v2_params(max_retrace_pct=0.995, selectivity_mode="LEG_ORIGIN",
                           zone_band_cents=0.10, hold_bars_n=1),
        day_label="2026-01-05")
    assert len(sigs) == 1
    assert sigs[0].level_price == pytest.approx(90.00)
    assert sigs[0].pullback_bar_idx == 0
    assert sigs[0].entry_bar_idx == 1


def test_detect_no_candidate_reuse_after_consumed():
    # rth0: seed touch (selectivity always rejects the very first bar -- no prior touch can
    # exist yet). rth1: a FRESH candidate (prior touch now satisfied by rth0), but its own
    # window [1,2] never reclaims -> dropped WITHOUT consuming rth2 (entry_idx stays None,
    # j just advances by 1, not by a false "window"). rth2: a SECOND fresh candidate, whose
    # own window [2,3] DOES reclaim at rth3.
    ext = _bars(_ANTECEDENT_LEG + [
        (100.3, 100.4, 99.85, 99.95),    # rth0: seed, rejected (no prior touch yet)
        (99.95, 100.05, 99.80, 100.00),  # rth1: candidate, fails to reclaim within N=1
        (100.00, 100.10, 99.90, 100.05), # rth2: still in zone, candidate again
        (100.05, 100.90, 100.00, 100.80),# rth3: reclaim (close 100.80 > zone_top 100.25)
    ], start=datetime(2026, 1, 5, 9, 10, tzinfo=ET))
    rth = ext.iloc[8:].reset_index(drop=True)
    leg_out = _leg_series_for(ext, rth)

    sigs = detect_pullback_hold_bull_v2(
        rth, up_structure_ok=[b.ok for b in leg_out],
        leg_origin_lows=[b.leg_origin_low for b in leg_out], leg_highs=[b.leg_high for b in leg_out],
        retrace_pcts=[b.retrace_pct for b in leg_out], levels_at=lambda i: [100.0],
        params=_v2_params(zone_band_cents=0.25, hold_bars_n=1), day_label="2026-01-05")
    assert len(sigs) == 1
    assert sigs[0].pullback_bar_idx == 2
    assert sigs[0].entry_bar_idx == 3


def test_detect_no_look_ahead_truncation():
    ext = _bars(_ANTECEDENT_LEG + [
        (100.3, 100.4, 99.85, 99.95),     # rth0: seed touch
        (99.95, 100.05, 99.80, 100.00),   # rth1: candidate, window [1,2] reclaims at rth2
        (100.00, 100.90, 99.95, 100.80),  # rth2: reclaim
        (100.80, 100.90, 100.60, 100.70), # rth3: irrelevant future bar
    ], start=datetime(2026, 1, 5, 9, 10, tzinfo=ET))
    rth_full = ext.iloc[8:].reset_index(drop=True)
    v2p = _v2_params(zone_band_cents=0.25, hold_bars_n=1)

    def run(ext_frame, rth_frame):
        leg_out = _leg_series_for(ext_frame, rth_frame)
        return detect_pullback_hold_bull_v2(
            rth_frame, up_structure_ok=[b.ok for b in leg_out],
            leg_origin_lows=[b.leg_origin_low for b in leg_out],
            leg_highs=[b.leg_high for b in leg_out],
            retrace_pcts=[b.retrace_pct for b in leg_out],
            levels_at=lambda i: [100.0], params=v2p, day_label="d")

    full = run(ext, rth_full)
    # Truncating right after the entry bar (rth-local index 2 = ext row 10) reproduces the
    # SAME signal -- drop the irrelevant future bar (rth3) from both frames.
    truncated = run(ext.iloc[:11].reset_index(drop=True), rth_full.iloc[:3].reset_index(drop=True))
    assert len(full) == 1 and len(truncated) == 1
    assert full[0].entry_bar_idx == truncated[0].entry_bar_idx == 2

    # Truncating BEFORE the entry bar (only the seed + candidate bars available) drops the
    # signal entirely -- proves the detector needed the reclaim bar's own close to fire.
    truncated_before = run(ext.iloc[:10].reset_index(drop=True), rth_full.iloc[:2].reset_index(drop=True))
    assert truncated_before == []


def test_cell_id_is_stable_and_readable():
    p = PullbackHoldV2Params(impulse_leg_mode="K24_M1.00_R0.786", k_bars=24, min_leg_dollars=1.0,
                              max_retrace_pct=0.786, selectivity_mode="LEG_ORIGIN",
                              zone_band_cents=0.25, hold_bars_n=2)
    assert p.cell_id() == "K24_M1.00_R0.786_LEG_ORIGIN_band25c_N2"


# =====================================================================================
# J's two named exhibits -- REAL cached SPY 5m bars (not synthetic), K24_M1.00_R0.786
# (the shipping-candidate impulse_leg_mode). Skips gracefully if the data cache is
# unavailable so this file doesn't break CI environments without the cache checked out.
# =====================================================================================
def _load_ext_and_rth(day: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    from datetime import time as dtime
    df = pd.read_csv(SPY_CSV)
    ts = pd.to_datetime(df["timestamp_et"])
    ts = ts.dt.tz_localize("America/New_York") if ts.dt.tz is None else ts.dt.tz_convert("America/New_York")
    df["timestamp_et"] = ts
    day_mask = ts.dt.date == day
    ext_day = df[day_mask & (ts.dt.time >= dtime(4, 0)) & (ts.dt.time < dtime(16, 0))].reset_index(drop=True)
    rth_day = df[day_mask & (ts.dt.time >= dtime(9, 30)) & (ts.dt.time < dtime(16, 0))].reset_index(drop=True)
    return ext_day, rth_day


@pytest.mark.skipif(not SPY_CSV.exists(), reason="SPY 5m data cache not present")
def test_exhibit_2026_07_22_higher_low_fires_in_anchor_window_R786_not_R618():
    from datetime import time as dtime
    ext_day, rth_day = _load_ext_and_rth(date(2026, 7, 22))
    assert not ext_day.empty and not rth_day.empty

    def leg_bools(params):
        leg_out = impulse_leg_series(ext_day, rth_day, params)
        return leg_out

    leg786 = leg_bools(ImpulseLegParams(k_bars=24, min_leg_dollars=1.0, max_retrace_pct=0.786))
    leg618 = leg_bools(ImpulseLegParams(k_bars=24, min_leg_dollars=1.0, max_retrace_pct=0.618))

    idx_1040 = int(rth_day.index[rth_day["timestamp_et"].dt.time == dtime(10, 40)][0])
    assert leg786[idx_1040].ok is True, (
        f"K24 R0.786 must read True at the 07-22 10:40 pullback-low bar "
        f"(retrace={leg786[idx_1040].retrace_pct})")
    assert leg618[idx_1040].ok is False, (
        "K24 R0.618 must read False at the SAME bar -- this asymmetry is the whole point "
        "of the R grid axis")

    from lib.watchers.level_memory import LevelMemory  # noqa: E402
    # Build a continuous RTH-only frame across the whole cache for LevelMemory (needs
    # multi-day history), matching the replay tool's own convention.
    full_df = pd.read_csv(SPY_CSV)
    fts = pd.to_datetime(full_df["timestamp_et"])
    fts = fts.dt.tz_localize("America/New_York") if fts.dt.tz is None else fts.dt.tz_convert("America/New_York")
    full_df["timestamp_et"] = fts
    rth_full = full_df[(fts.dt.time >= dtime(9, 30)) & (fts.dt.time < dtime(16, 0))].reset_index(drop=True)
    lm = LevelMemory(rth_full)
    day_mask = rth_full["timestamp_et"].dt.date == date(2026, 7, 22)
    global_idx_of = {i: int(orig) for i, orig in enumerate(rth_full[day_mask].index)}

    def levels_at(i):
        return [lv.price for lv in lm.levels_at(global_idx_of[i])]

    leg_out = leg786
    v2p = PullbackHoldV2Params(impulse_leg_mode="K24_M1.00_R0.786", k_bars=24, min_leg_dollars=1.0,
                                max_retrace_pct=0.786, selectivity_mode="PRIOR_INTERACTION",
                                zone_band_cents=0.40, hold_bars_n=2)
    sigs = detect_pullback_hold_bull_v2(
        rth_day, up_structure_ok=[b.ok for b in leg_out],
        leg_origin_lows=[b.leg_origin_low for b in leg_out], leg_highs=[b.leg_high for b in leg_out],
        retrace_pcts=[b.retrace_pct for b in leg_out], levels_at=levels_at, params=v2p,
        day_label="2026-07-22")
    hits = [s for s in sigs if dtime(10, 44) <= s.entry_ts.time() <= dtime(10, 53)]
    assert hits, (f"anchor_1 requires an entry in [10:44,10:53] ET on 2026-07-22 -- got "
                   f"signals at {[str(s.entry_ts.time()) for s in sigs]}")


@pytest.mark.skipif(not SPY_CSV.exists(), reason="SPY 5m data cache not present")
def test_exhibit_2026_07_21_shelf_impulse_leg_reads_true_at_all_three_taps():
    from datetime import time as dtime
    ext_day, rth_day = _load_ext_and_rth(date(2026, 7, 21))
    assert not ext_day.empty and not rth_day.empty
    leg_out = impulse_leg_series(
        ext_day, rth_day, ImpulseLegParams(k_bars=24, min_leg_dollars=1.0, max_retrace_pct=0.786))
    for t in (dtime(10, 40), dtime(11, 0), dtime(11, 5)):
        idx = int(rth_day.index[rth_day["timestamp_et"].dt.time == t][0])
        assert leg_out[idx].ok is True, (
            f"anchor_2 shelf tap at {t} must read True on the shipping impulse_leg_mode "
            f"(retrace={leg_out[idx].retrace_pct})")


# =====================================================================================
# Frequency disclosure helper
# =====================================================================================
def test_entries_per_day_helper():
    from tools.pullback_hold_bull_v2_replay import entries_per_day
    assert entries_per_day(n_signals=44, n_days=44) == pytest.approx(1.0)
    assert entries_per_day(n_signals=0, n_days=44) == pytest.approx(0.0)
    assert entries_per_day(n_signals=10, n_days=0) == pytest.approx(0.0)
