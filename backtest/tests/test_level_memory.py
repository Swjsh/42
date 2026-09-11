"""Guards for backtest/lib/watchers/level_memory.py (chef R&D, 2026-07-07).

The load-bearing invariant is LOOK-AHEAD SAFETY: levels, roles, and role-flip
history at bar i must derive ONLY from bars <= i. We prove this by planting a
future level and asserting it is invisible at an earlier bar.

Also pins the 750.90 ANCHOR: over 2026-07-06..07-07 the engine must surface a
high-memory resistance level at the 07-07 open near J's 750.90 shelf and flag
the first-bar interaction as a rejection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_BT = Path(__file__).resolve().parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

from lib.watchers.level_memory import LevelMemory, SWING_HALF  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_bars(rows: list[tuple], start="2026-07-06 09:30") -> pd.DataFrame:
    """rows: list of (open, high, low, close). Timestamps at 5m from start (ET)."""
    ts = pd.date_range(start=start, periods=len(rows), freq="5min", tz="America/New_York")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df.insert(0, "timestamp_et", ts.tz_convert("UTC"))  # engine re-converts
    df["volume"] = 100000
    return df


def _load_anchor_window() -> pd.DataFrame:
    csv = _BT / "data" / "spy_5m_2026-05-19_2026-07-07.csv"
    df = pd.read_csv(csv)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    mask = df["timestamp_et"].dt.date.isin(
        [pd.Timestamp("2026-07-06").date(), pd.Timestamp("2026-07-07").date()]
    )
    return df[mask].reset_index(drop=True)


# ── Look-ahead safety (THE critical guard) ───────────────────────────────────

class TestLookAheadSafety:
    def test_planted_future_level_invisible_earlier(self):
        """Plant a strong level in the FUTURE; assert it is NOT visible before it forms."""
        # First 15 bars: quiet drift around 500. Then bars 15-25: repeated hard
        # touches of 510 (the planted future level). A pivot at bar p needs bars
        # up to p+SWING_HALF, so the earliest the 510 shelf can appear is ~bar 17.
        early = [(500.0, 500.3, 499.7, 500.1) for _ in range(15)]
        shelf = [(509.8, 510.1, 509.6, 509.9) for _ in range(12)]
        df = _make_bars(early + shelf)
        lm = LevelMemory(df)

        # At an EARLY bar (bar 10) — well before the 510 shelf — no level near 510.
        snap_early = lm.snapshot(10, lookback_days=5)
        near_510_early = [L for L in snap_early.levels if abs(L.price - 510.0) <= 1.0]
        assert near_510_early == [], (
            f"LOOK-AHEAD LEAK: level near 510 visible at bar 10 before the shelf "
            f"forms at bar 15+: {near_510_early}"
        )

        # At a LATE bar (last bar) the 510 shelf MUST now be visible.
        snap_late = lm.snapshot(len(df) - 1, lookback_days=5)
        near_510_late = [L for L in snap_late.levels if abs(L.price - 510.0) <= 1.0]
        assert near_510_late, "510 shelf should be visible once it has formed"

    def test_role_flip_history_is_causal(self):
        """role_flips at bar i must not count flips that happen after i."""
        # Build: price sits below 505 (505 = resistance), then breaks above at bar 20.
        below = [(504.0, 504.6, 503.6, 504.2) for _ in range(10)]
        touch = [(504.5, 504.9, 504.1, 504.7) for _ in range(8)]   # more pivots below
        breakup = [(505.0, 506.2, 504.9, 506.0) for _ in range(8)]  # decisive break above
        df = _make_bars(below + touch + breakup)
        lm = LevelMemory(df)

        # Before the break (bar 15): the 505-ish level should have 0 flips.
        snap_before = lm.snapshot(15, lookback_days=5)
        lv_before = [L for L in snap_before.levels if abs(L.price - 505.0) <= 1.0]
        if lv_before:
            assert max(L.role_flips for L in lv_before) == 0, (
                "role_flip counted a FUTURE break before it happened (look-ahead)"
            )

    def test_snapshot_ignores_all_future_bars(self):
        """Truncating the frame after bar i yields the identical snapshot at i."""
        df = _load_anchor_window()
        lm_full = LevelMemory(df)
        i = 120
        snap_full = lm_full.snapshot(i, lookback_days=5)

        lm_trunc = LevelMemory(df.iloc[: i + 1].reset_index(drop=True))
        snap_trunc = lm_trunc.snapshot(i, lookback_days=5)

        prices_full = sorted(round(L.price, 2) for L in snap_full.levels)
        prices_trunc = sorted(round(L.price, 2) for L in snap_trunc.levels)
        assert prices_full == prices_trunc, (
            "Snapshot at bar i changed when future bars were removed -> LOOK-AHEAD LEAK.\n"
            f"full={prices_full}\ntrunc={prices_trunc}"
        )


# ── 750.90 anchor ────────────────────────────────────────────────────────────

class TestAnchor750:
    def test_sees_750_shelf_as_resistance_at_0707_open(self):
        df = _load_anchor_window()
        lm = LevelMemory(df)
        t = df[
            (df["timestamp_et"].dt.date == pd.Timestamp("2026-07-07").date())
            & (df["timestamp_et"].dt.time == pd.Timestamp("09:30").time())
        ].index[0]
        snap = lm.snapshot(int(t), lookback_days=5)

        # A high-memory resistance level within ~45c of J's 750.90 shelf must exist,
        # WITH role-flip history (this is the flip-flopped level).
        cands = [
            L for L in snap.levels
            if abs(L.price - 750.90) <= 0.50 and L.role == "resistance" and L.role_flips >= 1
        ]
        assert cands, (
            "Engine did not surface J's 750.90 shelf as a role-flipped resistance "
            f"at 07-07 open. Levels: {[(round(L.price,2),L.role,L.role_flips) for L in snap.levels[:8]]}"
        )

        # The 07-07 first bar interaction must be a rejection of a resistance level.
        assert snap.interaction.kind == "reject", (
            f"07-07 first-bar interaction was '{snap.interaction.kind}', expected 'reject'. "
            f"detail={snap.interaction.detail}"
        )
        assert snap.nearest.role == "resistance"

    def test_exact_75092_level_present(self):
        """The fine-grained 750.92 sub-level (J's exact number +/-3c) is in the set."""
        df = _load_anchor_window()
        lm = LevelMemory(df)
        t = df[
            (df["timestamp_et"].dt.date == pd.Timestamp("2026-07-07").date())
            & (df["timestamp_et"].dt.time == pd.Timestamp("09:30").time())
        ].index[0]
        snap = lm.snapshot(int(t), lookback_days=5)
        exact = [L for L in snap.levels if abs(L.price - 750.90) <= 0.05]
        assert exact, (
            "No sub-level within 5c of J's exact 750.90. "
            f"Shelf levels: {[round(L.price,2) for L in snap.levels if 750.0<=L.price<=751.5]}"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
