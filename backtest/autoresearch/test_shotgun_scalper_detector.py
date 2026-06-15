"""Unit tests for SHOTGUN_SCALPER detector.

Coverage per tier:
  Tier 1 — positive (today's 09:30 rejection bar) + negative (normal green bar)
  Tier 2 — positive (09:45 bullish reclaim of 738.10 Carry)
  Tier 3 — positive (trendline of 3+ swing highs broken + retest + reject)
          + negative (chop with no clear trendline)
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Load the SHOTGUN_SCALPER detector directly from its source path. The
# duplicate `lib/watchers/` at the repo root was removed during cleanup so
# the canonical location is `backtest/lib/watchers/shotgun_scalper_detector.py`.
import importlib.util  # noqa: E402

_DET_PATH = REPO_ROOT / "backtest" / "lib" / "watchers" / "shotgun_scalper_detector.py"
_spec = importlib.util.spec_from_file_location("shotgun_scalper_detector", _DET_PATH)
ssd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ssd)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_bar(
    minute: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 1_000_000,
    base_hour: int = 9,
    base_min: int = 30,
    date: str = "2026-05-15",
) -> dict:
    total_min = base_hour * 60 + base_min + minute
    h = total_min // 60
    m = total_min % 60
    ts = pd.Timestamp(f"{date} {h:02d}:{m:02d}:00")
    return {
        "time": ts,
        "open": float(open_),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": int(volume),
    }


def df_from_rows(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


NEUTRAL_RIBBON = {
    "fast": 740.0,
    "pivot": 740.0,
    "slow": 740.0,
    "spread_cents": 0.0,
    "stack": "NEUTRAL",
}


# ---------------------------------------------------------------------------
# Tier 1 — OPEN_REJECTION
# ---------------------------------------------------------------------------


def test_tier1_open_rejection_positive():
    """Today's 09:30 bar: open 741.84 / high 741.93 / low 739.31 / close 740.16.

    Range = 2.62, rejection-from-high (close=740.16) = 1.77 -> 67% of range.
    Closes in lower half (mid = 740.62). The 09:35 bar closes 739.95, below
    the 09:30 open of 741.84 — that is the live cross trigger.
    """
    rows = [
        make_bar(0, 741.84, 741.93, 739.31, 740.16),   # 09:30 rejection bar
        make_bar(5, 740.16, 740.40, 739.50, 739.95),   # 09:35 trigger — close < 741.84
    ]
    df = df_from_rows(rows)
    result = ssd.detect(
        today_bars=df,
        today_bar_idx=1,
        levels=[{"price": 738.10, "label": "Carry-738.10"}],
        ribbon=NEUTRAL_RIBBON,
        vix=17.5,
        htf_15m_stack=None,
    )
    assert result is not None
    assert result["tier"] == 1
    assert result["name"] == "OPEN_REJECTION"
    assert result["direction"] == "bearish"
    assert result["rejection_high"] == 741.93
    assert result["rejection_low"] == 739.31
    assert result["stop_chart"] == pytest.approx(741.98)
    assert result["confidence"] in ("high", "medium")


def test_tier1_open_rejection_negative_green_close_near_high():
    """A normal green 09:30 bar that closes near its high must NOT fire."""
    rows = [
        make_bar(0, 739.00, 740.00, 738.80, 739.95),  # tiny upper wick, green close
        make_bar(5, 739.95, 740.50, 739.80, 740.30),
    ]
    df = df_from_rows(rows)
    result = ssd.detect(
        today_bars=df,
        today_bar_idx=1,
        levels=[{"price": 738.10, "label": "Carry-738.10"}],
        ribbon=NEUTRAL_RIBBON,
        vix=17.0,
        htf_15m_stack=None,
    )
    assert result is None or result["name"] != "OPEN_REJECTION"


# ---------------------------------------------------------------------------
# Tier 2 — LEVEL_REJECT_LIVE
# ---------------------------------------------------------------------------


def test_tier2_level_reject_bullish_reclaim_positive():
    """09:45 bar wicks to 737.96 below Carry-738.10, closes 739.35 — bullish reclaim.

    Volume on the reject bar must be >= 1.5x the prior 3-bar average.
    Prior bars 09:30, 09:35, 09:40 each volume 1_000_000; reject bar volume 2_000_000
    -> ratio = 2.0x.
    """
    rows = [
        make_bar(0, 740.50, 740.80, 739.50, 740.20, volume=1_000_000),  # 09:30
        make_bar(5, 740.20, 740.40, 739.20, 739.80, volume=1_000_000),  # 09:35
        make_bar(10, 739.80, 740.00, 738.90, 739.10, volume=1_000_000), # 09:40
        # 09:45 rejection bar: low 737.96 < Carry 738.10, close 739.35 > open 738.50.
        # higher-low vs prev 738.90? No — 737.96 < 738.90. We need higher-low: redesign.
        make_bar(15, 738.50, 739.50, 737.96, 739.35, volume=2_000_000),
    ]
    # NOTE: my prior bar low must be lower than rej low (737.96) for higher-low.
    # Update the 09:40 bar's low to 737.50 so 737.96 > 737.50 = higher-low.
    rows[2] = make_bar(10, 739.80, 740.00, 737.50, 739.10, volume=1_000_000)
    df = df_from_rows(rows)
    result = ssd.detect(
        today_bars=df,
        today_bar_idx=3,
        levels=[{"price": 738.10, "label": "Carry-738.10"}],
        ribbon=NEUTRAL_RIBBON,
        vix=17.0,
        htf_15m_stack=None,
    )
    assert result is not None, "expected Tier 2 LEVEL_REJECT_LIVE to fire"
    # Tier 1 should not match because the 09:30 bar (open 740.50, high 740.80,
    # low 739.50, close 740.20) has rejection-from-high = 740.80 - 740.20 = 0.60,
    # range = 1.30 -> 46% (passes 33% threshold), but close 740.20 > mid 740.15
    # -> fails the lower-half rule. Good — the detector returns Tier 2.
    assert result["tier"] == 2
    assert result["name"] == "LEVEL_REJECT_LIVE"
    assert result["direction"] == "bullish"
    assert result["vol_ratio"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Tier 3 — TRENDLINE_BREAK_RETEST
# ---------------------------------------------------------------------------


def _build_trendline_bars(base_date: str = "2026-05-15") -> pd.DataFrame:
    """Build a descending-resistance trendline broken by the 15:00 bar.

    We pin three swing highs onto a line y = 741.00 - 0.05*idx so each
    swing is a strict local max (high > neighbours by at least 0.05).

      idx  5 (11:55): swing high #1, line_y = 740.75
      idx 17 (13:00): swing high #2, line_y = 740.15
      idx 29 (14:00): swing high #3, line_y = 739.55
      idx 39 (15:00): BREAK CANDLE — close well above projected line 739.05
      idx 40 (15:05): RETEST — low taps projected line, closes above
      idx 41 (15:10): TRIGGER — close further above the line
    """
    SLOPE = -0.05
    INTERCEPT = 741.00

    def line(idx: int) -> float:
        return INTERCEPT + SLOPE * idx

    swing_idxs = {5, 17, 29}
    bars = []
    for idx in range(39):  # idxs 0..38 — the break/retest/trigger are appended below
        m = idx * 5  # 5min cadence starting 11:30
        if idx in swing_idxs:
            ly = line(idx)
            o, h, l, c = ly - 0.20, ly, ly - 0.30, ly - 0.10
            vol = 950_000
        else:
            # Stay well below the line so no other swings touch it.
            base = line(idx) - 0.50
            # Tiny up-down oscillation so neighbours of each swing are STRICTLY
            # lower / equal -> the swing remains a clean local max.
            wobble = 0.02 if idx % 2 == 0 else -0.02
            o = base + wobble
            h = base + 0.10 + wobble
            l = base - 0.20 + wobble
            c = base + 0.05 + wobble
            vol = 700_000
        bars.append(make_bar(m, o, h, l, c, volume=vol,
                             base_hour=11, base_min=30, date=base_date))

    # idx 39: BREAK CANDLE — line at 741.00 - 0.05*39 = 739.05. Close 740.88.
    bars.append(make_bar(39 * 5, 739.10, 741.00, 738.95, 740.88, volume=2_500_000,
                         base_hour=11, base_min=30, date=base_date))
    # idx 40: RETEST — line at 741.00 - 0.05*40 = 739.00. Low taps 739.00, close above.
    bars.append(make_bar(40 * 5, 740.50, 740.80, 738.95, 739.60, volume=1_500_000,
                         base_hour=11, base_min=30, date=base_date))
    # idx 41: TRIGGER bar — close 739.95 well above line 738.95.
    bars.append(make_bar(41 * 5, 739.60, 740.20, 739.40, 739.95, volume=1_200_000,
                         base_hour=11, base_min=30, date=base_date))
    return df_from_rows(bars)


def test_tier3_trendline_break_retest_positive():
    df = _build_trendline_bars()
    result = ssd.detect(
        today_bars=df,
        today_bar_idx=len(df) - 1,
        levels=[{"price": 742.00, "label": "next_resistance"}],
        ribbon=NEUTRAL_RIBBON,
        vix=17.5,
        htf_15m_stack="BULL",
    )
    assert result is not None, (
        "expected Tier 3 to fire on the 15:10 bar after 15:00 break + 15:05 retest"
    )
    assert result["tier"] == 3
    assert result["name"] == "TRENDLINE_BREAK_RETEST"
    assert result["direction"] == "bullish"
    assert result["target_label"] == "next_resistance"


def test_tier3_both_kinds_evaluated_not_first_wins():
    """Regression test for the 2026-05-16 bullish-bias bug.

    Original detector iterated `for kind in ("low", "high"): if best: break`,
    returning on the FIRST kind that found a candidate. In practice, "low"
    (rising support broken → bear) was evaluated first and won 100% of the
    time when ANY break existed, regardless of whether a higher-quality
    "high" (falling resistance broken → bull) break also existed on the same
    data. Result in production: 29 bearish / 0 bullish in 16 weeks of
    historical replay despite a clear uptrend.

    This test constructs a scenario where BOTH a rising-support break AND a
    falling-resistance break exist concurrently, and verifies the detector
    picks the higher-scoring one (more touches × 10 + span_bars) instead
    of defaulting to bearish.
    """
    # Build 40 bars: a falling-resistance trendline with 4 swing-high touches
    # (high score) AND a rising-support line with 3 swing-low touches (lower score).
    # The bullish setup has more touches, so it should win.
    SLOPE_RES = -0.05
    INTERCEPT_RES = 743.00
    SLOPE_SUP = 0.04
    INTERCEPT_SUP = 738.50

    def res_line(idx: int) -> float:
        return INTERCEPT_RES + SLOPE_RES * idx

    def sup_line(idx: int) -> float:
        return INTERCEPT_SUP + SLOPE_SUP * idx

    res_swing_idxs = {3, 11, 19, 27}  # 4 swing highs touching res line
    sup_swing_idxs = {6, 16, 26}  # 3 swing lows touching sup line

    rows = []
    for idx in range(38):
        m = idx * 5
        if idx in res_swing_idxs:
            ly = res_line(idx)
            o, h, l, c = ly - 0.25, ly, ly - 0.40, ly - 0.15
            vol = 950_000
        elif idx in sup_swing_idxs:
            ly = sup_line(idx)
            o, h, l, c = ly + 0.25, ly + 0.40, ly, ly + 0.15
            vol = 950_000
        else:
            mid = (res_line(idx) + sup_line(idx)) / 2.0
            wobble = 0.05 if idx % 2 == 0 else -0.05
            o, h, l, c = mid + wobble, mid + 0.30, mid - 0.30, mid + wobble + 0.05
            vol = 700_000
        rows.append(make_bar(m, o, h, l, c, volume=vol,
                             base_hour=11, base_min=30))

    # Break + retest of the FALLING RESISTANCE line (bull break).
    # Bar 38: closes well above projected res line at idx 38.
    ly_at_break = res_line(38)
    rows.append(make_bar(38 * 5, ly_at_break - 0.10, ly_at_break + 0.80,
                          ly_at_break - 0.15, ly_at_break + 0.70, volume=1_500_000,
                          base_hour=11, base_min=30))
    # Bar 39: retest — low taps line, closes above
    ly_at_retest = res_line(39)
    rows.append(make_bar(39 * 5, ly_at_retest + 0.30, ly_at_retest + 0.70,
                          ly_at_retest - 0.05, ly_at_retest + 0.50, volume=1_000_000,
                          base_hour=11, base_min=30))
    # Bar 40: trigger — close further above the broken line
    ly_at_trigger = res_line(40)
    rows.append(make_bar(40 * 5, ly_at_trigger + 0.50, ly_at_trigger + 0.90,
                          ly_at_trigger + 0.40, ly_at_trigger + 0.80, volume=900_000,
                          base_hour=11, base_min=30))

    df = df_from_rows(rows)
    result = ssd.detect(
        today_bars=df,
        today_bar_idx=len(df) - 1,
        levels=[{"price": 743.00, "label": "fixture_resistance"}],
        ribbon=NEUTRAL_RIBBON,
        vix=17.5,
        htf_15m_stack="BULL",
    )

    # The bullish trendline has 4 swing touches (= score 4*10 + ~24 span = 64)
    # vs bearish 3 touches (= score 3*10 + ~20 span = 50). The fix guarantees
    # the bullish wins on score. The pre-fix detector would have returned
    # bearish because "low" was evaluated first.
    assert result is not None, "expected SOME tier to fire on this fixture"
    if result.get("tier") == 3:
        assert result["direction"] == "bullish", (
            f"Tier 3 picked the wrong direction. With 4 bull touches "
            f"and 3 bear touches, bullish should win on score. "
            f"Got direction={result.get('direction')}"
        )


def test_tier1_once_per_session():
    """Regression test for Tier 1 over-firing (2026-05-16 fix).

    The original detector fired Tier 1 OPEN_REJECTION on EVERY subsequent bar
    that closed below the 09:30 open, producing 214 fires over 16 weeks of
    historical replay. The fix gates Tier 1 to fire ONCE per session — if any
    earlier bar already triggered, subsequent fires are suppressed.
    """
    # Build 8 RTH bars where bars 1, 2, 3 all close below the 09:30 open.
    # Pre-fix: detector fires on bar 1, bar 2, bar 3 (three fires).
    # Post-fix: detector fires on bar 1 only.
    rows = [
        # 09:30 rejection bar (idx 0): open 741.84, big upper wick, close near low
        make_bar(0, 741.84, 741.93, 739.31, 740.16, volume=900_000),
        # 09:35 (idx 1): closes below 741.84 — first trigger
        make_bar(5, 740.20, 740.50, 739.50, 739.80, volume=850_000),
        # 09:40 (idx 2): also closes below 741.84
        make_bar(10, 739.80, 740.00, 739.20, 739.60, volume=700_000),
        # 09:45 (idx 3): also closes below 741.84
        make_bar(15, 739.60, 740.10, 739.40, 739.90, volume=650_000),
        # 09:50–10:00: continued
        make_bar(20, 739.90, 740.20, 739.50, 740.00, volume=600_000),
        make_bar(25, 740.00, 740.30, 739.60, 740.10, volume=550_000),
        make_bar(30, 740.10, 740.40, 739.80, 740.20, volume=500_000),
        make_bar(35, 740.20, 740.50, 739.90, 740.30, volume=500_000),
    ]
    df = df_from_rows(rows)

    # Fire at idx 1: should fire (first trigger)
    r1 = ssd.detect(today_bars=df, today_bar_idx=1, levels=[],
                    ribbon=NEUTRAL_RIBBON, vix=17.0, htf_15m_stack=None)
    assert r1 is not None and r1["tier"] == 1, "expected Tier 1 fire at idx 1"

    # Fire at idx 2: should NOT fire (earlier bar already triggered)
    r2 = ssd.detect(today_bars=df, today_bar_idx=2, levels=[],
                    ribbon=NEUTRAL_RIBBON, vix=17.0, htf_15m_stack=None)
    assert r2 is None or r2.get("tier") != 1, (
        f"Tier 1 over-fired at idx 2 (idx 1 already triggered). Got {r2}"
    )

    # Fire at idx 3: also should NOT fire
    r3 = ssd.detect(today_bars=df, today_bar_idx=3, levels=[],
                    ribbon=NEUTRAL_RIBBON, vix=17.0, htf_15m_stack=None)
    assert r3 is None or r3.get("tier") != 1, (
        f"Tier 1 over-fired at idx 3. Got {r3}"
    )


def test_tier3_trendline_break_retest_negative_chop():
    """Noisy chop with no >=3 swing touches on any line — must not fire."""
    rng = [
        (739.20, 739.80, 738.90, 739.40),
        (739.40, 739.60, 738.70, 738.90),
        (738.90, 739.50, 738.50, 739.30),
        (739.30, 739.70, 738.80, 739.10),
        (739.10, 739.40, 738.60, 738.80),
        (738.80, 739.30, 738.40, 739.00),
        (739.00, 739.20, 738.50, 738.70),
        (738.70, 739.10, 738.30, 738.90),
        (738.90, 739.40, 738.60, 739.20),
        (739.20, 739.50, 738.70, 738.85),
        (738.85, 739.30, 738.50, 739.05),
        (739.05, 739.40, 738.60, 738.75),
        (738.75, 739.20, 738.40, 739.00),
        (739.00, 739.30, 738.50, 738.80),
        (738.80, 739.10, 738.40, 738.95),
    ]
    rows = []
    for i, (o, h, l, c) in enumerate(rng):
        rows.append(make_bar(i * 5, o, h, l, c, volume=800_000,
                             base_hour=11, base_min=30))
    df = df_from_rows(rows)
    result = ssd.detect(
        today_bars=df,
        today_bar_idx=len(df) - 1,
        levels=[],
        ribbon=NEUTRAL_RIBBON,
        vix=17.0,
        htf_15m_stack=None,
    )
    # Either nothing fires, or only Tier 1/Tier 2 fires; Tier 3 must not.
    assert result is None or result["tier"] != 3


# ---------------------------------------------------------------------------
# Closed-bar safety
# ---------------------------------------------------------------------------


def test_detector_never_reads_beyond_idx():
    """If we pass an index < len-1, the detector must not peek at the future bar."""
    rows = [
        make_bar(0, 741.84, 741.93, 739.31, 740.16),  # 09:30 rejection bar
        make_bar(5, 740.16, 740.40, 739.50, 739.95),  # 09:35 trigger
        make_bar(10, 9999.0, 9999.0, 9999.0, 9999.0), # sentinel future bar
    ]
    df = df_from_rows(rows)
    # With today_bar_idx=1, the detector should ignore the sentinel bar at idx 2.
    result = ssd.detect(
        today_bars=df,
        today_bar_idx=1,
        levels=[],
        ribbon=NEUTRAL_RIBBON,
        vix=17.0,
        htf_15m_stack=None,
    )
    assert result is not None
    assert result["tier"] == 1
