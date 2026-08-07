"""detector.py -- SSR (Sweep -> Structure-shift -> Retest) state machine.

Implements the state machine frozen in
backtest/futures/analysis/SSR-battery/DESIGN.md section 3 and
markdown/research/SSR-PIVOT-LIQUIDITY-STRATEGY.md section 4. `zone_atr_mult`
(k1) and `sweep_atr_mult` (s) are the ONLY grid knobs this battery varies;
every other SSRParams field is frozen at its DESIGN.md default.

State machine (per independent level episode -- see "Level identity" below):

    IDLE --(bar pierces the level by >= s*ATR[i], then a bar closes back
             through the level within sweep_close_back_bars bars of the
             pierce)--> SWEPT
    SWEPT --(within shift_window_bars bars of the sweep: an opposing
             BOS/CHoCH from crypto.lib.market_structure.walk_structure, OR a
             post-sweep lower-high [short] / higher-low [long] pivot
             confirmed by crypto.lib.trendlines.find_swing_points with the
             same fractal window, OR a displacement bar with range >=
             displacement_atr_mult*ATR[i] closing in trade direction, away
             from the level)--> SHIFTED
    SHIFTED --(within retest_window_bars bars of the shift: price re-enters
             the zone band [level - k1*ATR[i], level + k1*ATR[i]] AND the
             bar's close is a reaction in trade direction)--> SIGNAL
             (this module signals at that bar's close; the caller enters at
             the NEXT bar's open, per the repo's C6 entry-bar convention --
             this module does not touch entry timing beyond the entry-window
             filter below).
    Any stage timing out -> back to IDLE (the SAME level can sweep again
    later and generate an independent signal; see "Level identity"). SSR-v1
    ADDENDUM completeness fix: a bar that times out a stale SWEPT/SHIFTED
    episode is evaluated the SAME bar as a potential fresh IDLE-state sweep
    (v0 dropped this -- see test_ssr_adversarial_causality.py's
    TestSweptTimeoutSameBarCoverageGap, updated to pin the fixed behavior).

Direction: a buy-side sweep of a HIGH-type level arms SHORT (sweepable_highs
-- PDH/PWH/PREV_4H_HIGH/ASIA_HIGH/LONDON_HIGH/NY_HIGH). A sell-side sweep of
a LOW-type level arms LONG (sweepable_lows, mirror names). One signal max
per sweep episode: a SIGNAL (in-window or not) or a timeout both end that
episode and return the level to IDLE.

Level identity + snapshot contract (`snapshots`): built against the REAL
backtest/futures/ssr/levels.py::LevelSnapshot (Builder 1), consumed here
ONLY via its two public methods -- pure duck typing, no import of that class:

    snapshots: list                -- one entry per row of `bars` (same length,
                                       index-aligned: snapshots[i] is what's
                                       causally known as of bar i). Entries
                                       may be None (treated as "no levels
                                       known yet" -- skip that bar).
    snapshots[i].sweepable_highs() -- list[tuple[str, float]] of (level_name, price)
    snapshots[i].sweepable_lows()  -- list[tuple[str, float]] of (level_name, price)

A level's "episode" is keyed by its NAME (e.g. "PDH"). Per LevelSnapshot's
own docstring, a level's price is fixed while its underlying period is the
"most recently completed" one and only CHANGES when that period rolls over
(e.g. PDH updates once at the next trading day's boundary). This module
tracks the last-seen price per name; when the price for a name changes
between consecutive active bars, the in-flight episode (if any) is
DISCARDED and a fresh IDLE episode starts for the new occurrence -- an
in-progress sweep/shift against yesterday's PDH is meaningless once PDH has
rolled to a new value.

RUN_* levels (SSR-v1 ADDENDUM opt-in, levels.py's include_running=True) are
the one exception to that rule: their price legitimately grows every bar
while their period is in progress, so a bare price change must NOT discard
an in-flight episode. Instead, `_Episode.locked_level_price` snapshots the
level's price at the pierce bar (the IDLE->SWEPT transition) and every
downstream geometry check -- shift/displacement, zone band, stop, retest --
reads that locked value for the rest of the episode, never the live,
still-growing running value ("the level must not chase price"). A RUN_*
name that vanishes from a bar's active set entirely (its session/day ended)
discards any in-flight episode outright, so a stale lock can never resurface
against an unrelated later occurrence of the same name.

No-look-ahead (C6): `find_swing_points` + `walk_structure` are called ONCE
over the full `bars` array up front. This is intentionally NOT a look-ahead
violation -- both primitives are built so a swing/event at index i never
depends on bars after i (see backtest/futures/seeds/structure_seed.py's own
docstring + backtest/tests/test_swing_seeds.py::TestStructureSeedNoLookahead
for the proof this module reuses verbatim). The per-bar state-machine walk
below only ever reads swings/events keyed to the CURRENT bar index i
(`events_by_break_idx.get(i)` / `pivots_by_confirm_idx.get(i)`), and every
other per-bar check indexes bar/ATR arrays at `i` only -- so the overall
detector inherits the same guarantee: mutating `bars` strictly after index k
never changes any signal at bar_index <= k (test_ssr_detector.py guards this
directly, mirroring the seed's own regression test).
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import (  # noqa: E402
    LabeledSwing,
    StructureEvent,
    label_swings,
    walk_structure,
)
from crypto.lib.trendlines import find_swing_points  # noqa: E402


@dataclass(frozen=True)
class SSRParams:
    zone_atr_mult: float
    sweep_atr_mult: float
    sweep_close_back_bars: int = 2
    shift_window_bars: int = 16
    retest_window_bars: int = 16
    stop_atr_buffer: float = 0.15
    displacement_atr_mult: float = 1.5
    swing_window: int = 2
    entry_start_et: str = "03:00"
    entry_end_et: str = "15:00"


@dataclass(frozen=True)
class SSRSignal:
    ts_et: Any                 # tz-aware pd.Timestamp of the signal (reaction-close) bar
    bar_index: int
    direction: str              # "long" | "short"
    level_name: str
    level_price: float
    sweep_extreme: float
    stop_price: float
    entry_ref_close: float
    state_trace: dict           # {"swept_at_index", "shifted_at_index", "shift_mode"}


@dataclass
class _Episode:
    """Mutable per-level, per-sweep-attempt tracking state -- internal only,
    never returned to callers. `pierces` is a small rolling buffer of
    (bar_index, extreme_price) tuples pruned to `sweep_close_back_bars`.

    `locked_level_price` is the SSR-v1 ADDENDUM field: for RUN_* (running
    running-extreme) levels only, the level's price as of the pierce bar
    (the bar that transitioned IDLE -> SWEPT), locked so a live-growing
    RUN_* value never "chases price" through the rest of the sweep -> shift
    -> retest sequence (close-back, zone band, stop, retest all read this
    locked value once set -- see SSRDetector.run()). None for non-RUN
    levels (whose v0 `level_price` is already frozen for the episode's
    lifetime by construction) and for RUN_* levels still IDLE.

    `pending_ref_price` is the SELF-ABSORPTION FIX (round-1 fixer,
    2026-08-07): for a RUN_* level, the level_price ANCHOR in effect for the
    episode's CURRENT in-flight pierce sequence (from the bar of its first
    still-valid pierce onward), set by `SSRDetector.run()` -- never re-read
    from the live, still-growing snapshot value while `pierces` is non-empty.
    Without this, a RUN_* level's own pierce bar becomes a completed prior
    bar by the very next bar (levels.py's causal [period_start, i-1] rule),
    self-inflating the level BEFORE the close-back confirmation or the
    SWEPT-transition lock can read the true pierced value -- see
    test_ssr_adversarial_run_level_self_absorption.py for the full mechanism
    and a minimal reproduction. None whenever `pierces` is empty (no
    in-flight pierce sequence to anchor) and for non-RUN levels (irrelevant:
    their level_price is already frozen for the episode's lifetime)."""
    state: str = "IDLE"                      # "IDLE" | "SWEPT" | "SHIFTED"
    pierces: list = field(default_factory=list)
    swept_at_index: Optional[int] = None
    sweep_extreme: Optional[float] = None
    shifted_at_index: Optional[int] = None
    shift_mode: Optional[str] = None
    locked_level_price: Optional[float] = None
    pending_ref_price: Optional[float] = None

    def reset(self) -> None:
        self.state = "IDLE"
        self.pierces = []
        self.swept_at_index = None
        self.sweep_extreme = None
        self.shifted_at_index = None
        self.shift_mode = None
        self.locked_level_price = None
        self.pending_ref_price = None


def _infer_granularity_seconds(bars: pd.DataFrame) -> int:
    """Nominal bar spacing for the Bar dataclass invariant (must be positive;
    unused by find_swing_points/label_swings/walk_structure's own logic,
    which only reads open_time/high/low/close)."""
    if len(bars) < 2:
        return 900
    delta = bars["timestamp_et"].iloc[1] - bars["timestamp_et"].iloc[0]
    secs = int(delta.total_seconds())
    return secs if secs > 0 else 900


def _bars_to_bar_objects(bars: pd.DataFrame) -> list[Bar]:
    """DataFrame -> immutable crypto.lib.bar.Bar objects, tz-aware UTC.
    Copies backtest/futures/seeds/structure_seed.py::bars_df_to_bar_objects's
    conversion pattern verbatim (ET -> UTC, volume defaults to 0)."""
    gran = _infer_granularity_seconds(bars)
    out: list[Bar] = []
    for row in bars.itertuples(index=False):
        ts = row.timestamp_et
        ts_utc = ts.tz_convert(timezone.utc) if ts.tzinfo is not None else ts.tz_localize(timezone.utc)
        out.append(Bar(open_time=ts_utc, open=float(row.open), high=float(row.high),
                        low=float(row.low), close=float(row.close),
                        volume=float(getattr(row, "volume", 0) or 0),
                        granularity_seconds=gran, source="ssr_detector"))
    return out


def _parse_et_time(hhmm: str) -> dt.time:
    return dt.datetime.strptime(hhmm, "%H:%M").time()


def _pierced(direction: str, bar_high: float, bar_low: float, level_price: float,
             s_mult: float, atr_val: float) -> bool:
    if direction == "short":
        return bar_high >= level_price + s_mult * atr_val
    return bar_low <= level_price - s_mult * atr_val


def _closed_back_through(direction: str, close_px: float, level_price: float) -> bool:
    return close_px < level_price if direction == "short" else close_px > level_price


def _is_displacement_bar(direction: str, bar_open: float, bar_high: float, bar_low: float,
                          bar_close: float, level_price: float, atr_val: float,
                          d_mult: float) -> bool:
    if (bar_high - bar_low) < d_mult * atr_val:
        return False
    if direction == "short":
        return bar_close < bar_open and bar_close < level_price
    return bar_close > bar_open and bar_close > level_price


def _zone_band(level_price: float, atr_val: float, k1: float) -> tuple[float, float]:
    return level_price - k1 * atr_val, level_price + k1 * atr_val


def _retest_reaction(direction: str, bar_open: float, bar_high: float, bar_low: float,
                      bar_close: float, band_lo: float, band_hi: float) -> bool:
    """Retest = price re-enters the zone band from the sweep side; reaction
    close = a bar closing in trade direction, back inside/under (short) or
    inside/over (long) the band -- i.e. a rejection, not a breakout through
    the far side of the band."""
    if direction == "short":
        touched = bar_high >= band_lo
        reaction = bar_close < bar_open and bar_close <= band_hi
    else:
        touched = bar_low <= band_hi
        reaction = bar_close > bar_open and bar_close >= band_lo
    return touched and reaction


def _step_idle(ep: _Episode, direction: str, i: int, bar_high: float, bar_low: float,
               bar_close: float, level_price: float, s_mult: float,
               close_back_bars: int, atr_val: float) -> None:
    """`level_price` here is whatever reference the caller (`SSRDetector.run`)
    decided applies THIS bar -- for a RUN_* level with an in-flight pierce
    sequence, that is already the anchored `pending_ref_price` from the first
    pierce, not the live snapshot value (see `SSRDetector.run`'s IDLE-branch
    call site and `_Episode.pending_ref_price`'s docstring). This function
    stays a pure mechanical pierce/close-back tracker against whatever single
    `level_price` it's handed; it also persists that same value onto
    `ep.pending_ref_price` for the caller to reuse on the NEXT bar, cleared
    back to None the moment `pierces` empties (pruned away or consumed by a
    SWEPT transition) so a stale anchor can never leak into an unrelated
    later pierce sequence."""
    ep.pierces = [(idx, ext) for idx, ext in ep.pierces if (i - idx) < close_back_bars]
    if _pierced(direction, bar_high, bar_low, level_price, s_mult, atr_val):
        ep.pierces.append((i, bar_high if direction == "short" else bar_low))
    if ep.pierces and _closed_back_through(direction, bar_close, level_price):
        extremes = [ext for _, ext in ep.pierces]
        ep.state = "SWEPT"
        ep.swept_at_index = i
        ep.sweep_extreme = max(extremes) if direction == "short" else min(extremes)
        ep.pierces = []
    ep.pending_ref_price = level_price if ep.pierces else None


def _step_swept(ep: _Episode, direction: str, i: int, bar_open: float, bar_high: float,
                 bar_low: float, bar_close: float, level_price: float, atr_val: float,
                 p: SSRParams, events_by_break_idx: dict, pivots_by_confirm_idx: dict) -> None:
    want_event_dir = "bearish" if direction == "short" else "bullish"
    for ev in events_by_break_idx.get(i, ()):
        if ev.direction == want_event_dir and ev.break_index > ep.swept_at_index:
            ep.state, ep.shifted_at_index, ep.shift_mode = "SHIFTED", i, "bos"
            return
    want_kind = "swing_high" if direction == "short" else "swing_low"
    want_label = "LH" if direction == "short" else "HL"
    for sw in pivots_by_confirm_idx.get(i, ()):
        # sw.bar_index > swept_at_index guards against a PRE-sweep pivot that
        # merely happens to CONFIRM inside the post-sweep window (its
        # confirmation index is fixed at bar_index + swing_window regardless
        # of when the sweep occurred -- see module docstring's no-look-ahead
        # note for why bar_index-gating, not just confirm-index, is required).
        if sw.kind == want_kind and sw.label == want_label and sw.bar_index > ep.swept_at_index:
            ep.state, ep.shifted_at_index, ep.shift_mode = "SHIFTED", i, "pivot"
            return
    if _is_displacement_bar(direction, bar_open, bar_high, bar_low, bar_close,
                             level_price, atr_val, p.displacement_atr_mult):
        ep.state, ep.shifted_at_index, ep.shift_mode = "SHIFTED", i, "displacement"


def _step_shifted(ep: _Episode, direction: str, i: int, bar_open: float, bar_high: float,
                   bar_low: float, bar_close: float, level_price: float, atr_val: float,
                   p: SSRParams, level_name: str, ts_val: Any, entry_start: dt.time,
                   entry_end: dt.time) -> Optional[SSRSignal]:
    band_lo, band_hi = _zone_band(level_price, atr_val, p.zone_atr_mult)
    if not _retest_reaction(direction, bar_open, bar_high, bar_low, bar_close, band_lo, band_hi):
        return None
    stop_price = (ep.sweep_extreme + p.stop_atr_buffer * atr_val if direction == "short"
                  else ep.sweep_extreme - p.stop_atr_buffer * atr_val)
    sig: Optional[SSRSignal] = None
    t = ts_val.time() if hasattr(ts_val, "time") else None
    if t is not None and entry_start <= t < entry_end:
        sig = SSRSignal(
            ts_et=ts_val, bar_index=i, direction=direction,
            level_name=str(level_name), level_price=float(level_price),
            sweep_extreme=float(ep.sweep_extreme), stop_price=float(stop_price),
            entry_ref_close=float(bar_close),
            state_trace={"swept_at_index": ep.swept_at_index,
                         "shifted_at_index": ep.shifted_at_index,
                         "shift_mode": ep.shift_mode},
        )
    ep.reset()  # one signal max per sweep episode -- consumed either way (in-window or not)
    return sig


class SSRDetector:
    """Chronological single-pass sweep -> shift -> retest detector.

    See module docstring for the state machine + LevelSnapshot contract.
    """

    def __init__(self, params: SSRParams):
        self.params = params

    def run(self, bars: pd.DataFrame, snapshots: list, atr: pd.Series) -> list[SSRSignal]:
        n = len(bars)
        if n == 0:
            return []
        if len(snapshots) != n:
            raise ValueError(
                f"SSRDetector.run: len(snapshots)={len(snapshots)} must equal len(bars)={n} "
                "-- snapshots must be index-aligned, one LevelSnapshot per bar row"
            )
        p = self.params
        entry_start = _parse_et_time(p.entry_start_et)
        entry_end = _parse_et_time(p.entry_end_et)

        # -- one-shot, whole-array structure read (causal by construction; see docstring) --
        bar_objs = _bars_to_bar_objects(bars)
        swings = find_swing_points(bar_objs, window=p.swing_window, inclusive_right=True)
        _, events = walk_structure(bar_objs, swings, p.swing_window)
        labeled = label_swings(swings)

        events_by_break_idx: dict[int, list[StructureEvent]] = defaultdict(list)
        for ev in events:
            events_by_break_idx[ev.break_index].append(ev)
        pivots_by_confirm_idx: dict[int, list[LabeledSwing]] = defaultdict(list)
        for sw in labeled:
            pivots_by_confirm_idx[sw.bar_index + p.swing_window].append(sw)

        opens = bars["open"].astype(float).to_numpy()
        highs = bars["high"].astype(float).to_numpy()
        lows = bars["low"].astype(float).to_numpy()
        closes = bars["close"].astype(float).to_numpy()
        atr_arr = atr.astype(float).to_numpy()
        ts_col = bars["timestamp_et"]

        episodes: dict[str, _Episode] = {}
        last_price: dict[str, float] = {}
        prev_active_run_names: set = set()
        signals: list[SSRSignal] = []

        for i in range(n):
            snap = snapshots[i]
            if snap is None:
                continue
            active: dict[str, tuple[float, str]] = {}
            for name, px in snap.sweepable_highs():
                active[name] = (float(px), "high")
            for name, px in snap.sweepable_lows():
                active[name] = (float(px), "low")
            if not active:
                continue

            # RUN_* episode hygiene (addendum #1): a session-scoped (or
            # day-scoped, across a day roll) RUN_* level can vanish from
            # `active` entirely per levels.py's own contract ("a session's
            # running level exists only DURING that session") and later
            # reappear against a wholly unrelated occurrence. Discard any
            # in-flight episode the moment its name drops out, so a stale
            # locked reference can never silently resurface later (C7).
            cur_run_names = {name for name in active if name.startswith("RUN_")}
            for stale in prev_active_run_names - cur_run_names:
                if stale in episodes:
                    episodes[stale].reset()
            prev_active_run_names = cur_run_names

            a = atr_arr[i]
            atr_ok = np.isfinite(a) and a > 0

            for name, (level_price, kind) in active.items():
                if kind not in ("high", "low"):
                    raise ValueError(
                        f"SSRDetector.run: level {name!r} has invalid kind {kind!r}; "
                        "expected 'high' or 'low'"
                    )
                is_run = name in cur_run_names

                if name not in episodes:
                    episodes[name] = _Episode()
                    if not is_run:
                        last_price[name] = level_price
                elif not is_run and last_price.get(name) != level_price:
                    # fresh occurrence of a NON-running level (first sight, or
                    # its underlying period rolled to a new price) -> abandon
                    # any in-flight episode against the stale price and
                    # restart. RUN_* levels skip this entirely -- their price
                    # legitimately grows every bar, and the addendum requires
                    # the sweep reference to LOCK at the pierce bar rather
                    # than chase that live value (handled below via
                    # locked_level_price), so a bare price change must never
                    # abandon a RUN_* episode.
                    episodes[name] = _Episode()
                    last_price[name] = level_price

                if not atr_ok:
                    continue  # ATR warmup -> no episode activity this bar (spec: "ATR NaN -> no episodes")

                ep = episodes[name]
                direction = "short" if kind == "high" else "long"

                # Timeout completeness fix (addendum #3, v0 WARN): a bar that
                # times out a stale SWEPT/SHIFTED episode is reset to IDLE
                # in-place (not `continue`d past) so THIS SAME bar still gets
                # evaluated below as a potential fresh IDLE-state sweep.
                if ep.state == "SWEPT" and i - ep.swept_at_index > p.shift_window_bars:
                    ep.reset()
                elif ep.state == "SHIFTED" and i - ep.shifted_at_index > p.retest_window_bars:
                    ep.reset()

                # RUN_* sweep-reference lock (addendum #1): once an episode
                # has left IDLE, all geometry (close-back already happened at
                # the IDLE->SWEPT transition; shift/displacement, zone band,
                # stop, retest below) reads the LOCKED price from the pierce
                # bar, never the live (still-growing) running value. Non-RUN
                # levels have no lock -- their level_price is already frozen
                # for the episode's lifetime by construction.
                geo_price = (ep.locked_level_price if (is_run and ep.locked_level_price is not None)
                             else level_price)

                if ep.state == "IDLE":
                    # Self-absorption fix (round-1 fixer, 2026-08-07): once a
                    # RUN_* episode has an in-flight pierce sequence
                    # (ep.pierces non-empty from a PRIOR bar), feed
                    # `_step_idle` the ANCHORED price from that sequence's
                    # first pierce, never the live snapshot `level_price` --
                    # a RUN_* level's own pierce bar becomes a completed
                    # prior bar by the very next bar (levels.py's causal
                    # rule), so re-reading the live value here would let the
                    # close-back test and the SWEPT-transition lock compare
                    # against a level the episode's own pierce just inflated.
                    # A brand-new pierce sequence (ep.pierces empty entering
                    # this bar) still anchors off the live value, exactly as
                    # before. Non-RUN levels always use the live value, which
                    # is provably constant across an episode's lifetime
                    # anyway (see module docstring's "Level identity" note),
                    # so this is a no-op for v0.
                    idle_level_price = (
                        ep.pending_ref_price
                        if (is_run and ep.pierces and ep.pending_ref_price is not None)
                        else level_price
                    )
                    _step_idle(ep, direction, i, highs[i], lows[i], closes[i],
                               idle_level_price, p.sweep_atr_mult, p.sweep_close_back_bars, a)
                    if is_run and ep.state == "SWEPT":
                        ep.locked_level_price = idle_level_price  # lock at the TRUE pierce-bar value
                elif ep.state == "SWEPT":
                    _step_swept(ep, direction, i, opens[i], highs[i], lows[i], closes[i],
                                geo_price, a, p, events_by_break_idx, pivots_by_confirm_idx)
                elif ep.state == "SHIFTED":
                    sig = _step_shifted(ep, direction, i, opens[i], highs[i], lows[i], closes[i],
                                        geo_price, a, p, name, ts_col.iloc[i],
                                        entry_start, entry_end)
                    if sig is not None:
                        signals.append(sig)

        return signals


__all__ = ["SSRParams", "SSRSignal", "SSRDetector"]
