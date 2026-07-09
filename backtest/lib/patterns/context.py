"""context.py — PatternContext: the single causal data carrier for the pattern grammar.

A PatternContext precomputes, ONCE over a full bar sequence, the derived reads every
grammar predicate needs (market structure/swings, session VWAP, Bollinger bandwidth) so
that evaluating a rule at any bar index `t` is a cheap array lookup, not a re-scan.

WHY PRECOMPUTE-ONCE IS STILL C6-SAFE (bars <= t only):
  Every array this module builds (`structure`, `vwap`, `bandwidth`) is produced by a
  strictly left-to-right / causal algorithm — each output at position i is a pure
  function of inputs at positions <= i, never i+1..end:
    - `crypto.lib.market_structure.analyze_structure` walks bars in order, only ever
      comparing the CURRENT bar's close to the most recently CONFIRMED swing (itself
      only confirmed `window` bars after its pivot — walk_structure's `by_confirm`
      dict). A swing pivot or structure event at position i is identical whether you
      run analyze_structure on bars[:N] or on bars[:i+1] and look at the same i.
    - `_session_vwap_array` / `_bollinger_bandwidth_array` are cumulative / rolling-
      window sums that reset at session (date) boundaries — position i only reads
      bars[session_start(i)..i].
  So precomputing over the FULL array once and then filtering each predicate's read to
  entries whose own index (bar_index / break_index) is <= t is PROVABLY equivalent to
  truncating the array to bars[:t+1] and recomputing from scratch at every t — just far
  cheaper (one O(n) pass instead of O(n^2)). See tests/test_pattern_grammar.py::test_c6_*
  for the black-box regression harness that would catch a violation of this contract.

LEVELS are handled differently on purpose: `levels_by_date` must be built by the CALLER
(see backtest/tools/pattern_prescreen.py::build_levels_by_date) from ONLY the prior
session's closed bars via backtest.lib.watchers.level_memory.LevelMemory — i.e. today's
level set is fixed at today's open and held through the session, mirroring how
automation/state/key-levels.json is actually refreshed (periodically, not every bar) and
trivially causal (today's rules can only ever see yesterday-and-earlier levels).
"""
from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

# crypto/ is a sibling of backtest/ at the repo root, not a backtest/lib package.
# Self-bootstrap sys.path exactly like backtest/futures/seeds/structure_seed.py does,
# so this module resolves `crypto.lib.*` regardless of caller CWD / pytest rootdir.
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import DEFAULT_WINDOW, MarketStructureRead, analyze_structure  # noqa: E402

# Bollinger bandwidth period — matches backtest/lib/watchers/bollinger_squeeze_watcher.py
# BB_N=20 exactly (the validated squeeze definition this grammar's compression()
# predicate reuses). See predicates.py::compression.
BANDWIDTH_PERIOD = 20
BANDWIDTH_K = 2.0


@dataclass(frozen=True, slots=True)
class LevelLike:
    """A price level, source-agnostic — adapts either automation/state/key-levels.json
    dict rows or backtest.lib.watchers.level_memory.Level objects to one shape the
    grammar's level-relative predicates can read.

    role:        "support" | "resistance"
    role_flips:  causal role-flip count (0 = never flipped). Feeds level_role=
                 "flipped_support"/"flipped_resistance" (see level_matches_role).
    """
    price: float
    role: str
    role_flips: int = 0
    memory_score: float = 0.0
    label: str = ""


LEVEL_ROLE_VALUES: tuple[str, ...] = (
    "any", "support", "resistance", "flipped_support", "flipped_resistance",
)


def level_matches_role(level: LevelLike, level_role: str) -> bool:
    """Filter used by every level-relative predicate. `flipped_*` requires role_flips>=1
    — i.e. a level the market has broken and re-respected at least once (level_memory's
    own definition of "battle-tested"; see backtest/lib/watchers/level_memory.py)."""
    if level_role == "any":
        return True
    if level_role == "support":
        return level.role == "support"
    if level_role == "resistance":
        return level.role == "resistance"
    if level_role == "flipped_support":
        return level.role == "support" and level.role_flips >= 1
    if level_role == "flipped_resistance":
        return level.role == "resistance" and level.role_flips >= 1
    raise ValueError(f"unknown level_role {level_role!r}; expected one of {LEVEL_ROLE_VALUES}")


def levels_from_level_memory(levels: Sequence[object]) -> tuple[LevelLike, ...]:
    """Adapt backtest.lib.watchers.level_memory.Level objects (or any object exposing
    .price/.role/.role_flips/.memory_score) into LevelLike, sorted by price (descending)
    for deterministic nearest-level tie-breaks in the predicates."""
    out = [
        LevelLike(
            price=round(float(lv.price), 2),
            role=str(lv.role),
            role_flips=int(getattr(lv, "role_flips", 0)),
            memory_score=float(getattr(lv, "memory_score", 0.0)),
            label=str(getattr(lv, "label", "")),
        )
        for lv in levels
    ]
    out.sort(key=lambda lv: -lv.price)
    return tuple(out)


def levels_from_key_levels_json(rows: Sequence[dict]) -> tuple[LevelLike, ...]:
    """Adapt automation/state/key-levels.json's `levels` array (schema_version 3) into
    LevelLike. Unknown/missing fields fail soft (default role_flips=0, memory_score=0)."""
    out = [
        LevelLike(
            price=round(float(r["price"]), 2),
            role=str(r.get("role") or r.get("type") or "support"),
            role_flips=int(r.get("role_flips", 0) or 0),
            memory_score=float(r.get("memory_score", 0.0) or 0.0),
            label=str(r.get("label", "")),
        )
        for r in rows
        if "price" in r
    ]
    out.sort(key=lambda lv: -lv.price)
    return tuple(out)


def _session_vwap_array(bars: Sequence[Bar]) -> tuple[float, ...]:
    """Cumulative typical-price VWAP, resetting at each session (date) boundary.

    Causal by construction: vwap[i] is a cumulative sum over bars[session_start..i]
    only. Same math as backtest/lib/vwap_rejection_detector.py::compute_session_vwap and
    backtest/lib/watchers/vwap_continuation_watcher.py::_session_rth_vwap (both defined
    on pandas DataFrames — this is the SAME formula ported to the Sequence[Bar] contract
    crypto/lib/chart_patterns.py and crypto/lib/market_structure.py already use).
    """
    out: list[float] = []
    day: Optional[dt.date] = None
    cum_pv = 0.0
    cum_v = 0.0
    for b in bars:
        d = b.open_time.date()
        if d != day:
            day = d
            cum_pv = 0.0
            cum_v = 0.0
        typical = (b.high + b.low + b.close) / 3.0
        cum_pv += typical * b.volume
        cum_v += b.volume
        out.append(cum_pv / cum_v if cum_v > 0 else b.close)
    return tuple(out)


def _bollinger_bandwidth_array(
    bars: Sequence[Bar], *, period: int = BANDWIDTH_PERIOD, k: float = BANDWIDTH_K,
) -> tuple[float, ...]:
    """Per-session BB(period, k) bandwidth = (upper-lower)/mid, population stdev (TV
    ta.stdev convention) — BYTE-FOR-BYTE the math in
    backtest/lib/watchers/bollinger_squeeze_watcher.py::bollinger_session, ported to
    Bar sequences. NaN until `period` bars into each session (causal warmup; resets at
    session/date boundaries so no cross-day leakage).
    """
    out: list[float] = [float("nan")] * len(bars)
    day: Optional[dt.date] = None
    session_start = 0
    for i, b in enumerate(bars):
        d = b.open_time.date()
        if d != day:
            day = d
            session_start = i
        if i - session_start + 1 < period:
            continue
        window = bars[i - period + 1: i + 1]
        closes = [w.close for w in window]
        mean = sum(closes) / period
        var = sum((c - mean) ** 2 for c in closes) / period  # population stdev
        sd = var ** 0.5
        out[i] = (2 * k * sd) / mean if mean else 0.0
    return tuple(out)


@dataclass(frozen=True, slots=True)
class PatternContext:
    """Everything a grammar predicate may read, precomputed ONCE over the full bar
    sequence handed to `.build()`. See module docstring for the C6 argument.
    """
    bars: tuple[Bar, ...]
    structure: MarketStructureRead
    vwap: tuple[float, ...]
    bandwidth: tuple[float, ...]
    levels_by_date: dict           # dt.date -> tuple[LevelLike, ...]
    swing_window: int = DEFAULT_WINDOW

    def levels_for(self, t: int) -> tuple[LevelLike, ...]:
        """Levels visible AT bar t — the level set fixed for bar t's trading session
        (see module docstring: built from the PRIOR session only, so this is trivially
        causal for every bar in the current session)."""
        d = self.bars[t].open_time.date()
        return self.levels_by_date.get(d, ())

    @classmethod
    def build(
        cls,
        bars: Sequence[Bar],
        *,
        levels_by_date: Optional[dict] = None,
        swing_window: int = DEFAULT_WINDOW,
        bandwidth_period: int = BANDWIDTH_PERIOD,
        bandwidth_k: float = BANDWIDTH_K,
    ) -> "PatternContext":
        bars_t = tuple(bars)
        structure = analyze_structure(bars_t, window=swing_window)
        vwap = _session_vwap_array(bars_t)
        bandwidth = _bollinger_bandwidth_array(bars_t, period=bandwidth_period, k=bandwidth_k)
        return cls(
            bars=bars_t,
            structure=structure,
            vwap=vwap,
            bandwidth=bandwidth,
            levels_by_date=dict(levels_by_date or {}),
            swing_window=swing_window,
        )
