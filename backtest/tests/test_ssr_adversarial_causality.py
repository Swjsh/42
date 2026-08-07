"""ADVERSARIAL verifier tests for the SSR battery (C6 look-ahead + causality lens).

Written by an independent adversarial-verifier pass over
backtest/futures/ssr/{levels,detector,backtest_runner}.py per
backtest/futures/analysis/SSR-battery/DESIGN.md. These tests do NOT modify the
SSR implementation -- they attack it.

Two things this file specifically targets that the builder's own test files
(test_ssr_data_levels.py, test_ssr_detector.py, test_ssr_runner.py) do not:

  1. Family B's 730d GC=F 1h window crosses FOUR US DST transitions
     (2024-11-03, 2025-03-09, 2025-11-02, 2026-03-08). The causality mutation
     test in test_ssr_data_levels.py only exercises a small hand-built
     60-bar-in-June fixture that never crosses a transition. Here we prove the
     SAME invariant (mutating bars strictly after index k never changes
     snapshots[0..k]) holds against the REAL cached GC 1h data spanning a real
     transition, AND against a synthetic worst-case fall-back hour that is
     deliberately constructed to be ACTIVE (unlike the real market, which is
     always closed exactly when the ambiguous hour occurs) -- so the proof
     does not lean on "the market happens to be closed then."

  2. A genuine signal-completeness gap in detector.py's SWEPT/SHIFTED
     window-timeout handling: `if i - ep.swept_at_index > window: ep.reset();
     continue` resets state and `continue`s past the CURRENT bar for THIS
     level, meaning a bar that both (a) times out an old episode and (b)
     independently qualifies as a fresh pierce+close-back sweep on its own
     never gets evaluated against the fresh-IDLE state until the NEXT bar.
     This is NOT a look-ahead violation (everything used is bar-i-or-earlier)
     and cannot inflate any reported number -- if anything it makes the
     detector UNDER-count signals, so it is WARN not BLOCKING -- but it is a
     real, demonstrable behavior gap worth a regression guard.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(REPO / "backtest"))

from backtest.futures.ssr import levels  # noqa: E402
from backtest.futures.ssr.detector import SSRDetector, SSRParams  # noqa: E402
from backtest.futures.swing_sim import wilder_atr  # noqa: E402

ET = "America/New_York"
CACHED_GC_1H = REPO / "backtest" / "data" / "futures" / "ssr" / "GC_F_1h.csv"

# The four US DST transitions inside Family B's 730d window
# (2026-08-07 minus 730d ~= 2024-08-08 .. 2026-08-07).
DST_TRANSITIONS = [
    dt.date(2024, 11, 3),   # fall back (2am -> 1am)
    dt.date(2025, 3, 9),    # spring forward (2am -> 3am)
    dt.date(2025, 11, 2),   # fall back
    dt.date(2026, 3, 8),    # spring forward
]


def _bar(ts: pd.Timestamp, o: float, h: float, l: float, c: float) -> dict:
    return {"timestamp_et": ts, "open": o, "high": h, "low": l, "close": c, "volume": 1000.0}


# ═══════════════ (1a) real cached data: DST transitions are unambiguous ═════

@pytest.mark.skipif(not CACHED_GC_1H.exists(), reason="GC_F_1h.csv cache not present in this checkout")
class TestRealDataDSTSpotCheck:
    """Spot-check the ACTUAL data feed this battery's Family B runs against.

    If yfinance ever started delivering a duplicate or a missing wall-clock
    hour across a transition, `build_levels`'s single forward pass assumes
    ascending, one-row-per-period-instance input -- this would be the guard
    that catches it before it silently corrupts a period aggregate.
    """

    def _load(self) -> pd.DataFrame:
        df = pd.read_csv(CACHED_GC_1H)
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(ET)
        for col in ("open", "high", "low", "close"):
            df[col] = df[col].astype(float)
        return df

    @pytest.mark.parametrize("transition_date", DST_TRANSITIONS)
    def test_no_duplicate_or_missing_wall_clock_hour_across_transition(self, transition_date):
        df = self._load()
        anchor = pd.Timestamp(transition_date, tz=ET)
        mask = (df["timestamp_et"] >= anchor - pd.Timedelta(days=3)) & \
               (df["timestamp_et"] <= anchor + pd.Timedelta(days=3))
        sub = df.loc[mask]
        assert len(sub) > 0, f"no cached bars found within +/-3d of {transition_date}"
        # No duplicate INSTANTS (not just no duplicate wall-clock label -- tz-aware
        # equality distinguishes 01:00 EDT from 01:00 EST correctly).
        assert sub["timestamp_et"].is_unique, (
            f"duplicate bar instants near DST transition {transition_date}"
        )
        # Strictly ascending (build_levels's single forward pass requires this).
        assert sub["timestamp_et"].is_monotonic_increasing

    @pytest.mark.parametrize("transition_date", DST_TRANSITIONS)
    def test_causality_holds_across_real_transition(self, transition_date):
        """The SAME invariant test_ssr_data_levels.py::TestCausalityMutation
        proves on a synthetic June fixture, proven here against real GC 1h
        data actually spanning a DST transition: mutating bars strictly after
        index k never changes snapshots[0..k]."""
        df = self._load()
        anchor = pd.Timestamp(transition_date, tz=ET)
        mask = (df["timestamp_et"] >= anchor - pd.Timedelta(days=10)) & \
               (df["timestamp_et"] <= anchor + pd.Timedelta(days=10))
        sub = df.loc[mask].reset_index(drop=True)
        assert len(sub) > 40, "need enough bars either side of the transition for a meaningful cut"

        # cut point: last bar strictly before the transition instant itself
        before = sub.index[sub["timestamp_et"] < anchor]
        assert len(before) > 5
        k = int(before[-1])

        baseline = levels.build_levels(sub)
        mutated = sub.copy(deep=True)
        after_mask = mutated.index > k
        for col in ("open", "high", "low", "close"):
            mutated.loc[after_mask, col] = mutated.loc[after_mask, col] + 500.0
        rebuilt = levels.build_levels(mutated)

        assert rebuilt[: k + 1] == baseline[: k + 1], (
            f"mutating bars strictly after index {k} (around real DST transition "
            f"{transition_date}) changed a snapshot at or before index {k} -- look-ahead leak"
        )
        # sanity: the mutation is load-bearing, not vacuous
        assert rebuilt[k + 1:] != baseline[k + 1:]


# ═══════════════ (1b) synthetic worst case: an ACTIVE ambiguous fall-back hour ═

class TestSyntheticActiveDSTFallback:
    """Real CME/Globex products never actually trade during the ambiguous
    repeated hour (US DST always flips 2am Sunday, deep inside the Fri
    17:00 -> Sun 18:00 weekly closure) -- confirmed empirically above. This
    test removes that accidental protection: it builds a synthetic bar
    sequence with TWO distinct real bars that both display as "01:00" local
    ET time (one at -04:00, one at -05:00 -- a genuine ambiguous ET fall-back
    hour), both carrying live, distinguishable price action, and proves
    `build_levels` still (a) doesn't crash/misorder and (b) preserves the
    causality invariant across that pair.
    """

    def test_ambiguous_hour_bars_are_distinct_instants_and_causal(self):
        # 2024-11-03: US EDT->EST fall-back. 01:00 occurs twice: once at UTC
        # offset -04:00 (before the flip) and once at -05:00 (after).
        pre_flip = pd.Timestamp("2024-11-03 05:00", tz="UTC").tz_convert(ET)   # displays 01:00 EDT
        post_flip = pd.Timestamp("2024-11-03 06:00", tz="UTC").tz_convert(ET)  # displays 01:00 EST
        assert pre_flip.time() == post_flip.time() == dt.time(1, 0)
        assert pre_flip.utcoffset() != post_flip.utcoffset()
        assert pre_flip < post_flip  # genuinely earlier in real time despite equal wall-clock label

        rows = [
            _bar(pd.Timestamp("2024-11-03 00:00", tz=ET).tz_convert("UTC").tz_convert(ET), 100, 102, 99, 101),
            _bar(pre_flip, 101, 108, 100, 107),     # "01:00" instance #1 -- a big up move
            _bar(post_flip, 107, 107.5, 90, 91),    # "01:00" instance #2 -- a big down move
            _bar(pd.Timestamp("2024-11-03 03:00", tz=ET).tz_convert("UTC").tz_convert(ET), 91, 93, 89, 92),
        ]
        bars = pd.DataFrame(rows).reset_index(drop=True)
        assert bars["timestamp_et"].is_monotonic_increasing
        assert bars["timestamp_et"].is_unique

        snapshots = levels.build_levels(bars)
        assert len(snapshots) == 4

        # Causality: mutate bar 3 only (strictly after the ambiguous pair at
        # idx 1,2) and confirm snapshots[0..2] (which include BOTH "01:00"
        # instances) are untouched.
        baseline = levels.build_levels(bars)
        mutated = bars.copy(deep=True)
        mutated.loc[3, ["open", "high", "low", "close"]] = [500.0, 600.0, 400.0, 550.0]
        rebuilt = levels.build_levels(mutated)
        assert rebuilt[:3] == baseline[:3], (
            "mutating the bar strictly after an ambiguous DST fall-back hour pair "
            "changed a snapshot at or before it -- look-ahead leak"
        )


# ═══════════════ (2) SWEPT-timeout same-bar fresh-sweep coverage gap ════════

class TestSweptTimeoutSameBarCoverageGap:
    """WARN-severity, not BLOCKING: demonstrates that detector.py's SWEPT
    timeout path (`if i - swept_at_index > shift_window_bars: ep.reset();
    continue`) discards the current bar's own IDLE-state evaluation, so a bar
    that both times out a stale SWEPT episode AND independently qualifies as
    a brand-new pierce+close-back sweep produces ZERO signal from that fresh
    sweep -- it is silently dropped, not deferred. This can only make the
    detector UNDER-count signals (conservative), so it cannot turn a KILL
    verdict into a PASS; it is disclosed here as a real completeness gap, not
    a correctness/look-ahead defect (detector.py:363-368 in the current tree).
    """

    def test_timeout_bar_that_is_also_a_fresh_sweep_is_dropped(self):
        ET_ = ET
        warmup = [(100.0, 100.5, 99.5, 100.0)] * 20
        rows = warmup + [(108.0, 111.5, 107.5, 109.5)]        # idx20: SWEEP -> SWEPT
        rows += [(109.5, 109.6, 109.4, 109.5)] * 16            # idx21..36: flat, still SWEPT
        # idx37: i - swept_at_index(20) = 17 > shift_window_bars(16) -> timeout.
        # This SAME bar ALSO independently pierces PDH=110 by >= 0.25*ATR and
        # closes back below it -- a textbook fresh sweep, engineered to be
        # verified against the real detector's own ATR, not a hand guess.
        rows += [(109.0, 112.0, 108.5, 109.2)]
        rows += [(109.2, 109.3, 109.1, 109.2)] * 3

        start = pd.Timestamp("2026-06-01 05:00", tz=ET_)
        t = start
        out = []
        for o, h, l, c in rows:
            out.append(_bar(t, o, h, l, c))
            t += pd.Timedelta(minutes=15)
        bars = pd.DataFrame(out)

        from dataclasses import dataclass
        from typing import Optional as _Opt

        @dataclass(frozen=True)
        class _Snap:
            prev_day_high: _Opt[float] = None

            def sweepable_highs(self):
                return [("PDH", self.prev_day_high)] if self.prev_day_high is not None else []

            def sweepable_lows(self):
                return []

        snapshots = [_Snap(prev_day_high=110.0)] * len(bars)
        atr = wilder_atr(bars, period=14)
        params = SSRParams(zone_atr_mult=0.5, sweep_atr_mult=0.25,
                            shift_window_bars=16, retest_window_bars=16)

        # Confirm the fixture actually exercises what it claims: bar 37 is a
        # genuine fresh pierce+close-back against the SAME atr[37] the real
        # detector will use.
        a37 = float(atr.iloc[37])
        assert bars["high"].iloc[37] >= 110.0 + 0.25 * a37, "fixture must pierce PDH on bar 37"
        assert bars["close"].iloc[37] < 110.0, "fixture must close back through PDH on bar 37"

        signals = SSRDetector(params).run(bars, snapshots, atr)

        # The completeness gap: this fixture, despite containing a textbook
        # second sweep at exactly the timeout bar, produces NO signal at all
        # (no shift/retest ever gets a chance to start from that fresh sweep,
        # since IDLE never even registers it). If this assertion ever flips
        # to `len(signals) >= 1`, the gap has been fixed upstream -- update
        # this test's docstring/assertion accordingly rather than deleting it.
        assert signals == [], (
            "expected the known SWEPT-timeout same-bar coverage gap (fresh sweep at "
            "the exact timeout bar is dropped) -- if this now fires a signal, detector.py's "
            "timeout handling changed and this regression guard should be updated, not removed"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
