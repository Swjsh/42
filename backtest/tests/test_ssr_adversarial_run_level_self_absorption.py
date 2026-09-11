"""ADVERSARIAL verifier test (Lens 1: RUN_* causality + locked-reference audit).

Written by an independent adversarial-verifier pass over
backtest/futures/ssr/{levels,detector}.py per the SSR-v1 ADDENDUM
(backtest/futures/analysis/SSR-battery/DESIGN.md). Does NOT modify the SSR
implementation except where noted below -- it attacks it.

ORIGINAL FINDING (BLOCKING, confirmed and FIXED by round-1 fixer 2026-08-07):
RUN_* levels self-absorb their own pierce bar one bar later, corrupting the
sweep-reference lock for any episode whose pierce-then-close-back spans MORE
than one bar (a real, common case -- `sweep_close_back_bars` defaults to 2,
i.e. DESIGN.md section 3 explicitly allows a 2-bar close-back window: "bar
exceeds level by >= s*ATR then closes back through within N=2 bars").

Mechanism: levels.py's RUN_* fields are correctly C6-causal in isolation --
`run_day_high` at bar i is computed strictly from bars [day_start, i-1]
(proven by TestRunningExtremeCausalityMutation in test_ssr_data_levels.py).
But when a bar PIERCES a RUN_* high-type level, that pierce bar's own high is
BY CONSTRUCTION a new day-high (piercing means bar_i_high > level_price[i] +
s*ATR > level_price[i] == the running max through i-1) -- so at the VERY NEXT
bar, the running level has already grown to (at least) that pierce bar's own
extreme. If the close-back-through confirmation happens on that next bar
(rather than the same bar as the pierce -- the multi-bar branch `_step_idle`
explicitly supports via its `pierces` rolling buffer), `_closed_back_through`
compared the bar's close against this ALREADY-INFLATED level, not the level
that was actually pierced. detector.py's SWEPT-transition code then did
`ep.locked_level_price = level_price` using this SAME inflated, per-bar-fresh
`level_price` -- so the "locked pierce-bar value" the addendum promises for
the rest of the episode (zone band, displacement check, retest band -- see
SWEPT/SHIFTED's `geo_price` reads) was not the level that was swept at all.

Demonstrated on REAL v1 production data (NQ=F 15m, h4_anchor='2000',
zone_atr_mult=0.5, sweep_atr_mult=0.1 -- the exact combo the integrator cited
as family A''s best/PULSE cell): of 387 RUN_* IDLE->SWEPT transitions in that
single cell, 253 (65%) went through this multi-bar-pierce path.

FIX (detector.py, round-1 fixer 2026-08-07): `SSRDetector.run()`'s IDLE
branch now anchors the `level_price` it feeds `_step_idle` to the value in
effect at the FIRST pierce of an in-flight sequence (`_Episode.
pending_ref_price`, set/cleared by `_step_idle` itself), rather than
re-reading the live, still-growing RUN_* snapshot value on every bar. The
SWEPT-transition lock (`ep.locked_level_price`) now stores that SAME anchored
value. This is a no-op for non-RUN levels (their level_price is already
provably constant across an episode's lifetime) and for same-bar pierce+
close-back sequences (the anchor equals the live value on the pierce bar
itself either way) -- see test_ssr_detector.py::TestRunLevelLockedReference
and its same-bar RUN_* fixture, unmodified and still green.

TEST-FIXTURE NOTE (round-1 fixer correction, 2026-08-07): the ORIGINAL
version of this file's `test_close_back_confirmation_...` and
`test_locked_reference_...` tests asserted that a SWEPT transition fires at
bar 21 using bar 21's close=103.0 -- engineered to sit above the TRUE level
(100.0) but below the self-inflated one (106.0), reasoning that "if this is
spurious relative to the true level, a CORRECT fix must not let the wrong
reference manufacture it." That reasoning is correct, but its conclusion was
mis-drawn: a genuinely fixed detector, given price that never once closes
below the true level, must NOT transition to SWEPT at all -- which is
exactly what detector.py now does (verified below). The original two tests'
own `pytest.fail(...)` precondition-check paths are what actually fire under
the fix, which is the CORRECT outcome, not a "recalibrate the fixture"
signal to ignore. This file is restructured into two independent, mutually
consistent scenarios so both directions of the fix are pinned explicitly:

  1. `TestNoSpuriousSweptOnSelfInflatedReference` -- the original fixture,
     UNCHANGED numbers: proves the fix suppresses the spurious SWEPT
     entirely (price never closes back through the TRUE level in this
     fixture, so no SWEPT should ever fire, regardless of what the
     self-inflated running value would have permitted).
  2. `TestGenuineMultiBarSweepLocksTrueLevel` -- a new fixture where bar 21's
     close genuinely closes back through the TRUE level (98.0 < 100.0, still
     nowhere near the self-inflated 106.0): proves that when a real
     close-back occurs, the SWEPT transition fires AND locks the TRUE
     pierce-bar level (100.0), never the self-inflated running value.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backtest.futures.ssr import detector as det  # noqa: E402
from backtest.futures.ssr.detector import SSRDetector, SSRParams  # noqa: E402
from backtest.futures.swing_sim import wilder_atr  # noqa: E402

ET = "America/New_York"


@dataclass(frozen=True)
class _RunHighSnap:
    """Minimal stub of a real include_running=True LevelSnapshot exposing a
    single RUN_DAY_HIGH sweepable level -- same shape as
    test_ssr_detector.py's `_RunHighSnap`, reimplemented locally so this file
    stays self-contained (its own module docstring convention, mirroring
    test_ssr_adversarial_causality.py)."""
    run_day_high: Optional[float] = None

    def sweepable_highs(self):
        return [("RUN_DAY_HIGH", self.run_day_high)] if self.run_day_high is not None else []

    def sweepable_lows(self):
        return []


def _mkbars(rows: list[tuple[float, float, float, float]], start: pd.Timestamp) -> pd.DataFrame:
    out = []
    t = start
    for o, h, l, c in rows:
        out.append({"timestamp_et": t, "open": o, "high": h, "low": l, "close": c, "volume": 1000.0})
        t = t + pd.Timedelta(minutes=15)
    return pd.DataFrame(out)


def _run_and_capture_swept_state(rows, run_high_at):
    """Runs the real SSRDetector over the fixture, capturing the episode's
    state via a non-mutating trace on `_step_idle` (the same technique
    test_ssr_adversarial_causality.py's own module docstring describes this
    file's sibling as using) -- this file calls the REAL, unmodified
    detector.py functions throughout; nothing here monkeypatches behavior,
    only observes it.

    `run_high_at(i)` supplies the RUN_DAY_HIGH snapshot value at bar i (the
    caller's fixture-specific schedule). `trace["ep"]` captures a REFERENCE
    to the actual `_Episode` object (not a copy) at the moment `_step_idle`
    hands control back to `SSRDetector.run` -- `run()`'s own subsequent lock
    line mutates that SAME object in place, so reading `ep.locked_level_price`
    AFTER `run()` returns reflects the real, fully-applied lock."""
    start = pd.Timestamp("2026-06-01 05:00", tz=ET)
    bars = _mkbars(rows, start)
    atr = wilder_atr(bars, period=14)
    snaps = [_RunHighSnap(run_day_high=run_high_at(i)) for i in range(len(bars))]
    params = SSRParams(zone_atr_mult=0.5, sweep_atr_mult=0.1,
                        shift_window_bars=16, retest_window_bars=16)

    trace: dict = {}
    orig_step_idle = det._step_idle

    def _traced(ep, direction, i, bh, bl, bc, level_price, s_mult, cb, a):
        orig_step_idle(ep, direction, i, bh, bl, bc, level_price, s_mult, cb, a)
        if i == 21:
            trace["ep"] = ep
            trace["state_after_bar21"] = ep.state
            trace["swept_at_index"] = ep.swept_at_index
            trace["level_price_used_for_closeback"] = level_price

    det._step_idle = _traced
    try:
        SSRDetector(params).run(bars, snaps, atr)
    finally:
        det._step_idle = orig_step_idle

    if "ep" in trace:
        trace["locked_level_price"] = trace["ep"].locked_level_price
    return trace


# 20 flat warmup bars (range 0.4, no gaps) -- seeds Wilder-14 ATR well below 1.0
# so the deliberately small sweep_atr_mult=0.1 threshold used below is easy to
# calibrate; flat/equal highs never register as pierces of the flat 100.0
# level during warmup (no bar exceeds 100.0 + 0.1*ATR until bar 20).
_WARMUP = [(100.0, 100.2, 99.8, 100.0)] * 20
_TRUE_LEVEL = 100.0
_SELF_INFLATED_LEVEL = 106.0  # bar 20's own pierce high, must NEVER be used as "the level"


class TestNoSpuriousSweptOnSelfInflatedReference:
    """BLOCKING (fixed): a RUN_* episode must NOT transition IDLE -> SWEPT
    using a level price that is not the level actually pierced. This fixture
    engineers bar 21's close (103.0) to sit STRICTLY ABOVE the true original
    level (100.0) -- i.e. price never once closes back through the level
    that was actually pierced -- so a correct detector must never register a
    SWEPT transition here, even though 103.0 IS below the self-inflated
    running value (106.0) a buggy implementation would compare against."""

    # idx20: pierces the TRUE level (100.0, the causal RUN_DAY_HIGH as of bar
    # 19) by a wide margin (high=106.0), but its OWN close (105.0) stays
    # ABOVE 100.0 -- no same-bar close-back, so the episode stays IDLE with
    # the pierce recorded in ep.pierces (the multi-bar branch DESIGN.md
    # section 3 and sweep_close_back_bars=2 explicitly provide for).
    #
    # idx21: the CAUSAL RUN_DAY_HIGH snapshot (mirroring levels.py's real,
    # C6-correct output) has now grown to 106.0 -- bar 20's own high, folded
    # into the running day-max now that bar 20 is a completed prior bar
    # relative to bar 21's i-1 window. Bar 21's close (103.0) is STILL ABOVE
    # the true original level (100.0) -- price never once closed back
    # through the level that was actually swept.
    _ROWS = _WARMUP + [
        (100.0, 106.0, 99.8, 105.0),   # idx20: pierce, no same-bar close-back
        (105.0, 105.2, 102.5, 103.0),  # idx21: close 103.0 -- ABOVE true level 100.0
    ]

    @staticmethod
    def _run_high_at(i: int) -> float:
        return _TRUE_LEVEL if i <= 20 else _SELF_INFLATED_LEVEL

    def test_fixture_sanity_price_never_closes_below_true_level(self):
        """Ground truth: from the pierce bar (idx20) onward, at no point does
        price close back through the TRUE original level (100.0) -- bar 21's
        close (103.0) is still 3 points above it. (Warmup bars close exactly
        AT 100.0 by construction -- flat/no-op bars, irrelevant to the
        pierce/close-back sequence under test, so they're excluded here.)"""
        bars = _mkbars(self._ROWS, pd.Timestamp("2026-06-01 05:00", tz=ET))
        post_pierce_closes = bars["close"].iloc[20:]
        assert (post_pierce_closes > _TRUE_LEVEL).all(), (
            "fixture sanity failed: some bar at/after the pierce already closes at/below the "
            "true level, which would make this fixture unable to isolate the self-absorption effect"
        )

    def test_close_back_confirmation_uses_the_true_pierced_level_not_a_self_inflated_one(self):
        trace = _run_and_capture_swept_state(self._ROWS, self._run_high_at)

        used = trace["level_price_used_for_closeback"]
        assert used == pytest.approx(_TRUE_LEVEL), (
            f"detector.py's close-back-through check at bar 21 used level_price={used!r} -- but "
            f"the level actually pierced at bar 20 was {_TRUE_LEVEL!r}. A value of "
            f"{_SELF_INFLATED_LEVEL!r} here would mean the level chased its own sweep bar before "
            f"the reference lock could take effect."
        )

    def test_no_spurious_swept_transition_fires(self):
        """The affirmative regression pin: given price that never truly
        closes back through the pierced level, NO SWEPT transition -- and
        therefore no lock -- should ever occur for this episode."""
        trace = _run_and_capture_swept_state(self._ROWS, self._run_high_at)
        assert trace.get("state_after_bar21") != "SWEPT", (
            f"spurious SWEPT transition fired using a self-inflated reference (trace={trace!r}) -- "
            "price never genuinely closed back through the true pierced level (100.0; see "
            "test_fixture_sanity_price_never_closes_below_true_level)."
        )
        assert trace.get("locked_level_price") is None, (
            f"no genuine sweep completed, so no lock should exist: {trace!r}"
        )


class TestGenuineMultiBarSweepLocksTrueLevel:
    """Positive counterpart: when price DOES genuinely close back through
    the true pierced level (not merely the self-inflated one) across a
    multi-bar pierce->close-back window, the SWEPT transition must fire AND
    lock the TRUE pierce-bar level (100.0), never the self-inflated running
    value (106.0) that would also, coincidentally, permit a close-back here."""

    # Identical idx20 pierce bar to the class above. idx21's close (98.0) now
    # sits BELOW the true level (100.0) -- a genuine close-back -- while the
    # causal RUN_DAY_HIGH snapshot at bar 21 has still (correctly, per
    # levels.py) grown to the self-inflated 106.0. A buggy implementation
    # would lock at 106.0 (still consistent with 98.0 < 106.0); the fixed
    # implementation must lock at the TRUE 100.0.
    _ROWS = _WARMUP + [
        (100.0, 106.0, 99.8, 105.0),   # idx20: pierce, no same-bar close-back
        (105.0, 105.2, 96.5, 98.0),    # idx21: close 98.0 -- genuinely BELOW true level 100.0
    ]

    @staticmethod
    def _run_high_at(i: int) -> float:
        return _TRUE_LEVEL if i <= 20 else _SELF_INFLATED_LEVEL

    def test_fixture_sanity_bar21_close_is_a_genuine_close_back(self):
        bars = _mkbars(self._ROWS, pd.Timestamp("2026-06-01 05:00", tz=ET))
        assert bars["close"].iloc[21] < _TRUE_LEVEL, (
            "fixture sanity failed: bar 21 must close genuinely below the true level for this "
            "scenario to test the POSITIVE (correct-SWEPT) path"
        )

    def test_swept_transition_fires_and_locks_the_true_pierced_level(self):
        trace = _run_and_capture_swept_state(self._ROWS, self._run_high_at)

        assert trace.get("state_after_bar21") == "SWEPT", (
            f"expected a genuine SWEPT transition at bar 21 (a real close-back through the true "
            f"level occurred) -- got {trace!r}"
        )
        used = trace["level_price_used_for_closeback"]
        assert used == pytest.approx(_TRUE_LEVEL), (
            f"close-back check used level_price={used!r}, expected the true pierced level "
            f"{_TRUE_LEVEL!r}"
        )
        locked = trace["locked_level_price"]
        assert locked == pytest.approx(_TRUE_LEVEL), (
            f"locked_level_price={locked!r} after the bar-21 SWEPT transition, expected "
            f"{_TRUE_LEVEL!r} (the level genuinely pierced at bar 20), not the self-inflated "
            f"running value ({_SELF_INFLATED_LEVEL!r}) that bar 21's own snapshot happened to show. "
            f"Every downstream geometry check for this episode (zone band, displacement, retest) "
            f"would otherwise be built around the wrong reference for the episode's entire "
            f"remaining lifetime."
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
