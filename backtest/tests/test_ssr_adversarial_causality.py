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

def _mirror_rows(rows: list[tuple[float, float, float, float]], axis: float = 200.0):
    """Reflect a bar sequence around `axis` (price -> axis - price), swapping
    high/low so the OHLC invariant still holds -- same convention as
    test_ssr_detector.py's `_mirror` helper, reimplemented locally so this
    file stays self-contained per its own module docstring."""
    return [(axis - o, axis - l, axis - h, axis - c) for (o, h, l, c) in rows]


class TestSweptTimeoutSameBarCoverageGap:
    """SSR-v1 ADDENDUM change #3 (documented behavior CHANGE, sanctioned):
    detector.py's SWEPT/SHIFTED timeout path now resets the episode to IDLE
    IN-PLACE instead of `continue`ing past the current bar for this level --
    so a bar that both (a) times out a stale episode AND (b) independently
    qualifies as a brand-new pierce+close-back sweep on its own now DOES
    start a fresh episode from that same bar, rather than silently dropping
    it. This class pins the FIXED behavior (v0 pinned the dropped-fresh-sweep
    gap; that pin is superseded here per DESIGN.md's explicit sanction for
    this one test).

    `test_timeout_bar_that_is_also_a_fresh_sweep_completes_into_a_signal`
    extends the original v0 fixture (same warmup, same idx20 sweep, same
    16-flat-bar timeout runway, same idx37 fresh-sweep-on-timeout-bar) with a
    displacement shift + retest tail so the fix is proven OBSERVABLY -- via
    an actual emitted SSRSignal whose state_trace.swept_at_index == 37 (the
    timeout bar itself), not index 20 -- rather than merely asserting
    `signals == []`, which (as re-verified while writing this update) stays
    true with or without the fix applied to this short a tail and therefore
    cannot discriminate the two behaviors.
    `test_mirrored_long_variant_also_completes_into_a_signal` is the
    sanctioned "variant" proving the same fix generalizes to the LOW-type
    level / long-direction path (exact price-mirror of the short fixture,
    same technique as test_ssr_detector.py's mirrored-long case).
    """

    # Shared short-direction (PDH) tail: idx20 sweep -> 16 flat SWEPT bars ->
    # idx37 times out (37-20=17 > shift_window_bars=16) AND independently
    # re-pierces+closes back through PDH=110 on the SAME bar -> idx38
    # displacement bar shifts (SWEPT->SHIFTED) -> idx39-41 retrace -> idx42
    # retest touch + down reaction close -> SIGNAL. Every threshold below is
    # verified against the real detector's own Wilder-14 ATR, not hand-guessed.
    _WARMUP = [(100.0, 100.5, 99.5, 100.0)] * 20
    _SHORT_ROWS = _WARMUP + [
        (108.0, 111.5, 107.5, 109.5),                        # 20  original SWEEP -> SWEPT
        *([(109.5, 109.6, 109.4, 109.5)] * 16),               # 21..36  flat, still SWEPT
        (109.0, 112.0, 108.5, 109.2),                         # 37  timeout + fresh pierce+close-back
        (109.0, 109.3, 100.0, 101.0),                         # 38  displacement -> SHIFTED
        (101.0, 104.0, 100.5, 103.5),                         # 39  retrace
        (103.5, 107.0, 103.0, 106.5),                         # 40  retrace
        (106.5, 109.5, 106.0, 109.0),                         # 41  retrace
        (109.5, 110.4, 108.8, 109.0),                         # 42  retest touch + down reaction -> SIGNAL
    ]
    _START = pd.Timestamp("2026-06-01 00:00", tz=ET)  # early enough that bar42 (10:30 ET) is in-window

    def test_timeout_bar_that_is_also_a_fresh_sweep_completes_into_a_signal(self):
        bars = _mkbars_local(self._SHORT_ROWS, self._START)

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

        # Fixture-engineering proof, against the real detector's own ATR:
        a37, a38, a42 = float(atr.iloc[37]), float(atr.iloc[38]), float(atr.iloc[42])
        assert bars["high"].iloc[37] >= 110.0 + 0.25 * a37, "bar 37 must pierce PDH"
        assert bars["close"].iloc[37] < 110.0, "bar 37 must close back through PDH (same bar)"
        assert (bars["high"].iloc[38] - bars["low"].iloc[38]) >= 1.5 * a38, "bar 38 must be a displacement bar"
        assert bars["close"].iloc[38] < bars["open"].iloc[38] < 110.0, "bar 38 must close down, away from PDH"
        band_lo, band_hi = 110.0 - 0.5 * a42, 110.0 + 0.5 * a42
        assert bars["high"].iloc[42] >= band_lo, "bar 42 must touch back into the zone band"
        assert bars["close"].iloc[42] < bars["open"].iloc[42] and bars["close"].iloc[42] <= band_hi, (
            "bar 42 must close as a down reaction inside/under the band"
        )

        signals = SSRDetector(params).run(bars, snapshots, atr)

        assert len(signals) == 1, (
            f"expected exactly one signal completing from the timeout-bar fresh sweep, got {signals!r} -- "
            "if this is empty, the addendum #3 completeness fix (same-bar IDLE re-evaluation on timeout) "
            "regressed; the fresh sweep at bar 37 (NOT the original bar-20 sweep, which never reaches "
            "SHIFTED before its own bar-36 timeout) is the only path to a signal in this fixture"
        )
        sig = signals[0]
        assert sig.bar_index == 42
        assert sig.direction == "short"
        assert sig.level_name == "PDH"
        assert sig.sweep_extreme == 112.0                    # bar 37's high, NOT bar 20's 111.5
        assert sig.state_trace == {
            "swept_at_index": 37,       # the TIMEOUT bar itself, proving same-bar re-evaluation fired
            "shifted_at_index": 38,
            "shift_mode": "displacement",
        }

    def test_mirrored_long_variant_also_completes_into_a_signal(self):
        """Exact price-mirror (axis=200) of the short fixture above -- a
        sell-side sweep of PDL=90 that times out and re-sweeps on the same
        bar, shifts via displacement, retests, and signals LONG. Proves the
        addendum #3 fix is direction-symmetric, not an artifact of the
        short-side code path specifically."""
        long_rows = _mirror_rows(self._SHORT_ROWS)
        bars = _mkbars_local(long_rows, self._START)
        assert (bars["high"] >= bars["low"]).all(), "mirrored fixture must preserve OHLC invariant"

        from dataclasses import dataclass
        from typing import Optional as _Opt

        @dataclass(frozen=True)
        class _Snap:
            prev_day_low: _Opt[float] = None

            def sweepable_highs(self):
                return []

            def sweepable_lows(self):
                return [("PDL", self.prev_day_low)] if self.prev_day_low is not None else []

        snapshots = [_Snap(prev_day_low=90.0)] * len(bars)
        atr = wilder_atr(bars, period=14)
        params = SSRParams(zone_atr_mult=0.5, sweep_atr_mult=0.25,
                            shift_window_bars=16, retest_window_bars=16)

        signals = SSRDetector(params).run(bars, snapshots, atr)

        assert len(signals) == 1, signals
        sig = signals[0]
        assert sig.bar_index == 42
        assert sig.direction == "long"
        assert sig.level_name == "PDL"
        assert sig.sweep_extreme == 88.0                      # 200 - 112.0, the mirrored fresh-sweep low
        assert sig.state_trace == {
            "swept_at_index": 37,
            "shifted_at_index": 38,
            "shift_mode": "displacement",
        }


def _mkbars_local(rows: list[tuple[float, float, float, float]], start: pd.Timestamp) -> pd.DataFrame:
    out = []
    t = start
    for o, h, l, c in rows:
        out.append(_bar(t, o, h, l, c))
        t = t + pd.Timedelta(minutes=15)
    return pd.DataFrame(out)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
