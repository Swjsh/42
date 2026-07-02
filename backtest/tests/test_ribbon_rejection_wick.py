"""Guard tests — RIBBON_REJECTION_WICK detector (research-only, unregistered).

Guards:
  1. Bear side fires on a constructed break->rejection-wick sequence.
  2. No fire without a prior structural break below the ribbon.
  3. No fire when the close is back inside/above the band (no rejection).
  4. wick_frac threshold is respected.
  5. Bull mirror fires on the mirrored sequence.
  6. NO LOOK-AHEAD (C6): the signal at bar i is invariant to future bars.
  7. ANCHOR REGRESSION (J's live read 2026-07-02): bearish fire at 10:30 ET
     on the committed fixture; total fires today <= 5 (not loosened into noise).
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent      # backtest/
sys.path.insert(0, str(REPO))

from lib.ribbon import compute_ribbon  # noqa: E402
from lib.watchers.ribbon_rejection_wick_detector import (  # noqa: E402
    RRWParams,
    detect,
    detect_both,
)

FIXTURE = REPO / "tests" / "fixtures" / "spy_5m_2026-07-02_anchor.csv"

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)


# ── synthetic frame builder ──────────────────────────────────────────────────

def _mk_frame(closes: list[float], start="2026-06-30 09:30:00") -> pd.DataFrame:
    """5m frame from closes; open=prev close, high/low hug the body (overridable)."""
    ts = pd.date_range(start=start, periods=len(closes), freq="5min")
    opens = [closes[0]] + closes[:-1]
    df = pd.DataFrame({
        "timestamp_et": ts,
        "open": opens,
        "close": closes,
        "high": [max(o, c) + 0.02 for o, c in zip(opens, closes)],
        "low": [min(o, c) - 0.02 for o, c in zip(opens, closes)],
        "volume": [100_000] * len(closes),
    })
    return df


def _bear_scenario() -> tuple[pd.DataFrame, int]:
    """60 bars above ribbon -> 4-bar breakdown below -> rejection wick bar.

    Returns (frame, idx_of_rejection_bar). The rejection bar geometry is set
    AFTER computing the ribbon (highs/lows don't feed the EMAs).
    """
    closes = [100 + 0.05 * i for i in range(60)]          # steady rise: above ribbon
    closes += [closes[-1] - 1.2, closes[-1] - 2.2, closes[-1] - 2.6]  # breakdown
    closes += [closes[-1] + 0.1]                           # rejection bar close (still low)
    df = _mk_frame(closes)
    rib = compute_ribbon(df["close"])
    i = len(df) - 1
    band_low = float(rib[["fast", "pivot", "slow"]].min(axis=1).iloc[i])
    # rejection bar: wick up INTO the band, close well below it
    df.loc[i, "high"] = band_low + 0.30
    df.loc[i, "low"] = float(df.loc[i, "close"]) - 0.10
    df.loc[i, "open"] = float(df.loc[i, "close"]) + 0.15
    # give the breakdown-initiating bar a volume spike (day-max)
    df.loc[60, "volume"] = 500_000
    return df, i


def _bull_scenario() -> tuple[pd.DataFrame, int]:
    closes = [100 - 0.05 * i for i in range(60)]          # steady fall: below ribbon
    closes += [closes[-1] + 1.2, closes[-1] + 2.2, closes[-1] + 2.6]  # break up
    closes += [closes[-1] - 0.1]
    df = _mk_frame(closes)
    rib = compute_ribbon(df["close"])
    i = len(df) - 1
    band_high = float(rib[["fast", "pivot", "slow"]].max(axis=1).iloc[i])
    df.loc[i, "low"] = band_high - 0.30
    df.loc[i, "high"] = float(df.loc[i, "close"]) + 0.10
    df.loc[i, "open"] = float(df.loc[i, "close"]) - 0.15
    df.loc[60, "volume"] = 500_000
    return df, i


# ── unit guards ──────────────────────────────────────────────────────────────

def test_bear_fires_on_break_then_rejection_wick():
    df, i = _bear_scenario()
    sig = detect(df, i, RRWParams())
    assert sig is not None, "bear rejection wick must fire"
    assert sig["direction"] == "bearish"
    assert sig["bars_since_break"] <= 12
    assert sig["wick_frac"] >= 0.35
    assert sig["vol_break_ratio"] > 2.0  # spiked break bar vs flat 100k median


def test_no_fire_without_prior_break():
    # price stays above the ribbon the whole time -> a wicky bar must NOT fire bear
    closes = [100 + 0.05 * i for i in range(64)]
    df = _mk_frame(closes)
    i = len(df) - 1
    df.loc[i, "high"] = float(df.loc[i, "close"]) + 1.0  # big top wick, but above ribbon
    sig = detect(df, i, RRWParams())
    assert sig is None


def test_no_fire_when_close_back_inside_band():
    df, i = _bear_scenario()
    rib = compute_ribbon(df["close"])
    band_low = float(rib[["fast", "pivot", "slow"]].min(axis=1).iloc[i])
    # move the close INSIDE the band (no rejection) — rebuild closes so the
    # ribbon reflects it, then re-check
    df.loc[i, "close"] = band_low + 0.05
    sig = detect(df, i, RRWParams())
    assert sig is None


def test_wick_fraction_gate():
    df, i = _bear_scenario()
    # shrink the wick: high barely above close -> tiny wick fraction
    df.loc[i, "high"] = float(df.loc[i, "close"]) + 0.02
    df.loc[i, "low"] = float(df.loc[i, "close"]) - 0.30
    sig = detect(df, i, RRWParams(wick_frac_min=0.35))
    assert sig is None


def test_bull_mirror_fires():
    df, i = _bull_scenario()
    sig = detect(df, i, RRWParams(), direction="bull")
    assert sig is not None, "bull mirror must fire on mirrored sequence"
    assert sig["direction"] == "bullish"


def test_stack_filter_blocks_flipped_stack():
    df, i = _bear_scenario()
    rib = compute_ribbon(df["close"])
    stack = str(rib["stack"].iloc[i])
    sig_any = detect(df, i, RRWParams(require_stack_not_flipped=False))
    assert sig_any is not None
    if stack == "BEAR":  # deep 3-bar breakdown usually flips fast<pivot<slow
        assert detect(df, i, RRWParams(require_stack_not_flipped=True)) is None


def test_no_lookahead_truncation_invariance():
    """C6 guard: signal at bar i must not change when future bars change."""
    df, i = _bear_scenario()
    # extend with 10 wild future bars
    future = _mk_frame([50.0 + j for j in range(10)],
                       start=str(df["timestamp_et"].iloc[-1] + pd.Timedelta(minutes=5)))
    extended = pd.concat([df, future], ignore_index=True)
    sig_trunc = detect(df, i, RRWParams())
    sig_ext = detect(extended, i, RRWParams())
    assert (sig_trunc is None) == (sig_ext is None)
    if sig_trunc:
        for k in ("direction", "wick_frac", "bars_since_break", "vol_break_ratio"):
            assert sig_trunc[k] == sig_ext[k], f"look-ahead leak via {k}"


# ── anchor regression (J's live case, 2026-07-02) ────────────────────────────

@pytest.mark.skipif(not FIXTURE.exists(), reason="anchor fixture not present")
def test_anchor_2026_07_02_bear_fire_at_1030():
    df = pd.read_csv(FIXTURE)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    t = df["timestamp_et"].dt.time
    frame = df[(t >= RTH_OPEN) & (t < RTH_CLOSE)].reset_index(drop=True)
    rib = compute_ribbon(frame["close"])
    session = dt.date(2026, 7, 2)

    fires = []
    for i in frame.index[frame["timestamp_et"].dt.date == session]:
        ts = frame.iloc[i]["timestamp_et"]
        if ts.time() < dt.time(9, 45) or ts.time() > dt.time(15, 0):
            continue
        fires.extend(detect_both(frame, i, RRWParams(), ribbon_df=rib))

    bear_times = {f["trigger_bar_time"][11:16] for f in fires if f["direction"] == "bearish"}
    assert bear_times & {"10:30", "10:35"}, (
        f"J's anchor (bearish fire at 10:30/10:35 ET) missed; bear fires: {sorted(bear_times)}"
    )
    assert len(fires) <= 5, f"too loose: {len(fires)} fires on anchor day (>5 = noise)"
    # every anchor-day fire happened BEFORE the 11:00 confirmatory ribbon flip
    for f in fires:
        assert f["stack_at_signal"] != "BEAR", "anchor fires must be anticipatory (pre-flip)"
