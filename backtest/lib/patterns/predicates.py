"""predicates.py — the 15 domain predicates the pattern grammar composes rules from.

Each is a FACTORY: call it with its knobs to get back a `Predicate`
(`Callable[[PatternContext, int], Optional[dict]]`) — a pure function that reads
`ctx.bars[<=t]` (plus the precomputed-but-causal `ctx.structure` / `ctx.vwap` /
`ctx.bandwidth` / `ctx.levels_for(t)`, see context.py) and returns `None` (does not hold)
or an evidence dict (holds).

C6 CONTRACT — every predicate here must only ever read index <= t. Concretely that means:
  - direct bar access: `ctx.bars[t]`, `ctx.bars[t-k]` for k >= 0 — NEVER `ctx.bars[t+k]`.
  - structure reads: filter `ctx.structure.labeled_swings` / `.events` to entries whose
    own `bar_index`/`break_index` (+ confirmation window, where noted) is <= t.
  - `ctx.vwap[t]` / `ctx.bandwidth[t]` are safe as-is (cumulative/rolling, causal by
    construction — see context.py's module docstring for the proof).
  - `ctx.levels_for(t)` is safe as-is (built from the PRIOR session only).
tests/test_pattern_grammar.py::test_c6_* is the enforcement harness: it mutates bars
strictly AFTER a fixed evaluation index and asserts the result at that index is
unchanged for every registry rule, and separately proves the harness has teeth by
showing it DOES catch a deliberately future-peeking predicate.

Primitive -> Step-1 inventory primitive it wraps or is modeled on (see
markdown/research/PATTERN-GRAMMAR.md sec 1 for the full citation table):
  swing_label, monotone_swings, flat_side  -> crypto/lib/market_structure.py (HH/HL/LH/LL)
  structure_event                          -> crypto/lib/market_structure.py (BOS/CHoCH)
  close_above, close_below, level_proximity -> backtest/lib/watchers/level_memory.py +
                                                automation/state/key-levels.json
  compression                              -> backtest/lib/watchers/bollinger_squeeze_watcher.py
  volume_expansion                         -> crypto/lib/chart_patterns.py::momentum_acceleration
  wick_rejection                           -> crypto/lib/chart_patterns.py (failed_breakdown_wick /
                                               rejection_at_level) + backtest/lib/watchers/
                                               ribbon_rejection_wick_detector.py
  engulfing, inside_bar                    -> TA-PATTERN-REFERENCE.md sec D (candlesticks)
  pullback_depth                           -> TA-PATTERN-REFERENCE.md sec C.1 (flag/pennant)
  gap_event                                -> backtest/lib/watchers/gap_and_go_watcher.py
  near_vwap                                -> backtest/lib/vwap_rejection_detector.py +
                                               backtest/lib/watchers/vwap_*_watcher.py
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from .context import PatternContext, level_matches_role

Predicate = Callable[[PatternContext, int], Optional[dict]]


# ── 1. market structure (HH/HL/LH/LL labels) ──────────────────────────────────

def swing_label(*, kind: str, labels: Sequence[str], window: Optional[int] = None) -> Predicate:
    """True iff the LAST swing of `kind` ("swing_high"|"swing_low") confirmed by bar t
    carries a label in `labels` (from {"H","HH","LH","L","HL","LL"} —
    crypto.lib.market_structure.label_swings). `window` defaults to ctx.swing_window.
    """
    labels_set = set(labels)

    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        w = ctx.swing_window if window is None else window
        cand = [s for s in ctx.structure.labeled_swings if s.kind == kind and s.bar_index + w <= t]
        if not cand:
            return None
        last = cand[-1]
        if last.label not in labels_set:
            return None
        return {
            "swing_label": last.label, "swing_price": round(last.price, 2),
            "swing_bar_index": last.bar_index, "trigger_level": round(last.price, 2),
        }
    return _p


# ── 2. market structure (BOS / CHoCH) ─────────────────────────────────────────

def structure_event(*, kind: str, direction: str) -> Predicate:
    """True iff a BOS/CHoCH of `kind` ("BOS"|"CHoCH") + `direction` ("bullish"|"bearish")
    printed EXACTLY at bar t (break_index == t) — the "fresh event, no re-emit"
    convention used by backtest/lib/watchers/market_structure_watcher.py.
    """
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        for e in ctx.structure.events:
            if e.break_index == t and e.kind == kind and e.direction == direction:
                return {
                    "event_kind": e.kind, "event_direction": e.direction,
                    "trigger_level": round(e.broken_price, 2), "swing_index": e.swing_index,
                }
        return None
    return _p


# ── 3/4. level-relative: close crosses a named/memory level ──────────────────

def _qualifying_levels(ctx: PatternContext, t: int, level_role: str):
    return [lv for lv in ctx.levels_for(t) if level_matches_role(lv, level_role)]


def close_above(
    *, level_role: str = "any", require_cross: bool = True, max_distance: Optional[float] = None,
) -> Predicate:
    """True iff close[t] sits ABOVE a level matching `level_role` (e.g.
    "flipped_support" — a support level that has role-flipped at least once, per
    backtest/lib/watchers/level_memory.py). require_cross=True (default): close[t-1]
    must NOT already have been above it (a fresh break, not a stale state). max_distance:
    if set, the level must have been within this $ of close[t-1] (no wild same-bar jumps
    counted as a "break" of a level nowhere near where price was).
    """
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        if t < 1:
            return None
        c0, c1 = ctx.bars[t].close, ctx.bars[t - 1].close
        qualifying = []
        for lv in _qualifying_levels(ctx, t, level_role):
            if not (c0 > lv.price):
                continue
            if require_cross and not (c1 <= lv.price):
                continue
            if max_distance is not None and abs(c1 - lv.price) > max_distance:
                continue
            qualifying.append(lv)
        if not qualifying:
            return None
        lv = min(qualifying, key=lambda x: abs(c1 - x.price))
        return {"trigger_level": lv.price, "level_role": lv.role, "level_role_flips": lv.role_flips}
    return _p


def close_below(
    *, level_role: str = "any", require_cross: bool = True, max_distance: Optional[float] = None,
) -> Predicate:
    """Mirror of close_above for a decisive close BELOW a qualifying level."""
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        if t < 1:
            return None
        c0, c1 = ctx.bars[t].close, ctx.bars[t - 1].close
        qualifying = []
        for lv in _qualifying_levels(ctx, t, level_role):
            if not (c0 < lv.price):
                continue
            if require_cross and not (c1 >= lv.price):
                continue
            if max_distance is not None and abs(c1 - lv.price) > max_distance:
                continue
            qualifying.append(lv)
        if not qualifying:
            return None
        lv = min(qualifying, key=lambda x: abs(c1 - x.price))
        return {"trigger_level": lv.price, "level_role": lv.role, "level_role_flips": lv.role_flips}
    return _p


# ── 5. level-relative: proximity (state, not an event) ───────────────────────

def level_proximity(*, max_distance: float, level_role: str = "any") -> Predicate:
    """True iff the NEAREST level matching `level_role` sits within `max_distance` $ of
    close[t]. A state predicate (no cross required) — composes with event predicates
    like wick_rejection/engulfing to anchor them to a named level."""
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        levels = _qualifying_levels(ctx, t, level_role)
        if not levels:
            return None
        c = ctx.bars[t].close
        lv = min(levels, key=lambda x: abs(c - x.price))
        d = abs(c - lv.price)
        if d > max_distance:
            return None
        return {"trigger_level": lv.price, "level_role": lv.role, "distance": round(d, 4)}
    return _p


# ── 6. compression (Bollinger-bandwidth squeeze) ──────────────────────────────

def compression(*, percentile_lookback: int = 20, percentile_threshold: float = 20.0) -> Predicate:
    """True iff the BB(20,2) bandwidth at t (ctx.bandwidth) ranks in the bottom
    `percentile_threshold` of its trailing `percentile_lookback` bandwidth samples — the
    SAME squeeze definition as backtest/lib/watchers/bollinger_squeeze_watcher.py
    (SQ_LOOKBACK=20, SQ_QUANTILE=0.20 default)."""
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        if t < percentile_lookback - 1:
            return None
        cur = ctx.bandwidth[t]
        if cur != cur:  # NaN warmup
            return None
        window = ctx.bandwidth[t - percentile_lookback + 1: t + 1]
        valid = [x for x in window if x == x]
        if len(valid) < percentile_lookback:
            return None
        rank = sum(1 for x in valid if x <= cur) / len(valid) * 100.0
        if rank > percentile_threshold:
            return None
        return {"bandwidth_pct_rank": round(rank, 1), "bandwidth": round(cur, 5)}
    return _p


# ── 7. volume expansion ───────────────────────────────────────────────────────

def volume_expansion(*, lookback: int = 20, mult: float = 1.5) -> Predicate:
    """True iff volume[t] >= `mult` x the trailing `lookback`-bar average volume (bars
    [t-lookback, t-1], NOT including t itself). Matches the volume-confirmation
    convention shared by crypto/lib/chart_patterns.py::momentum_acceleration and
    backtest/lib/watchers/bollinger_squeeze_watcher.py's VOL_MULT gate."""
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        if t < lookback:
            return None
        prior = ctx.bars[t - lookback: t]
        avg = sum(b.volume for b in prior) / lookback
        if avg <= 0:
            return None
        v = ctx.bars[t].volume
        ratio = v / avg
        if ratio < mult:
            return None
        return {"volume_mult": round(ratio, 2), "volume": v, "avg_prior_volume": round(avg, 0)}
    return _p


# ── 8. wick rejection (optionally anchored to a named level) ─────────────────

def wick_rejection(
    *,
    side: str,
    min_wick_frac: float = 0.33,
    min_range_dollars: float = 0.05,
    at_level_role: Optional[str] = None,
    max_level_distance: float = 0.30,
) -> Predicate:
    """side="lower": long lower wick + close in the upper part of the range (bullish
    rejection). side="upper": mirror (bearish rejection). Geometry per
    TA-PATTERN-REFERENCE.md sec D.4 (pin bar) and crypto/lib/chart_patterns.py
    (failed_breakdown_wick / rejection_at_level).

    If `at_level_role` is given (e.g. "support"), the wick's extreme (low for
    side="lower", high for side="upper") must ALSO pierce through a level of that role
    within `max_level_distance`, with the close ending back on the level's origin side —
    turning a bare rolling-window wick into a NAMED-LEVEL failed-break / Wyckoff-spring
    read (see registry.py::failed_break_spring). at_level_role=None (default) is
    level-agnostic, matching chart_patterns.py's rolling-window behaviour; its
    "trigger_level" then falls back to the wick's own extreme price.
    """
    if side not in ("lower", "upper"):
        raise ValueError("side must be 'lower' or 'upper'")

    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        bar = ctx.bars[t]
        rng = bar.high - bar.low
        if rng < min_range_dollars:
            return None
        body_hi, body_lo = max(bar.open, bar.close), min(bar.open, bar.close)
        if side == "lower":
            wick = body_lo - bar.low
            extreme = bar.low
        else:
            wick = bar.high - body_hi
            extreme = bar.high
        frac = wick / rng
        if frac < min_wick_frac:
            return None
        evidence = {
            "wick_frac": round(frac, 3), "range_dollars": round(rng, 3),
            "trigger_level": round(extreme, 2),
        }
        if at_level_role is None:
            return evidence
        for lv in _qualifying_levels(ctx, t, at_level_role):
            if abs(extreme - lv.price) > max_level_distance:
                continue
            pierced = (extreme < lv.price) if side == "lower" else (extreme > lv.price)
            reclaimed = (bar.close > lv.price) if side == "lower" else (bar.close < lv.price)
            if pierced and reclaimed:
                return {
                    **evidence, "trigger_level": lv.price, "level_role": lv.role,
                    "level_role_flips": lv.role_flips,
                }
        return None
    return _p


# ── 9. engulfing candle ────────────────────────────────────────────────────────

def engulfing(*, direction: str) -> Predicate:
    """direction="bullish": bar t's body fully contains + exceeds bar t-1's body, bar t
    is green and bar t-1 was red (classic bullish engulfing). direction="bearish"
    mirrors. Geometry note: this is standard OHLC engulfing-candle geometry; it is NOT
    yet a subsection of TA-PATTERN-REFERENCE.md (the closest documented cousin is sec
    D.3 Harami — the OPPOSITE containment direction, small body inside a large one)."""
    if direction not in ("bullish", "bearish"):
        raise ValueError("direction must be 'bullish' or 'bearish'")

    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        if t < 1:
            return None
        cur, prev = ctx.bars[t], ctx.bars[t - 1]
        cur_hi, cur_lo = max(cur.open, cur.close), min(cur.open, cur.close)
        prev_hi, prev_lo = max(prev.open, prev.close), min(prev.open, prev.close)
        if not (cur_hi >= prev_hi and cur_lo <= prev_lo):
            return None
        cur_green, prev_green = cur.close > cur.open, prev.close > prev.open
        if direction == "bullish" and not (cur_green and not prev_green):
            return None
        if direction == "bearish" and not (not cur_green and prev_green):
            return None
        trigger = prev_lo if direction == "bullish" else prev_hi
        return {
            "engulfed_body_dollars": round(prev_hi - prev_lo, 3),
            "trigger_level": round(trigger, 2),
        }
    return _p


# ── 10. inside bar (single-bar containment) ───────────────────────────────────

def inside_bar() -> Predicate:
    """True iff bar t's range is fully contained within bar t-1's range (high<=prior
    high, low>=prior low) — the atomic consolidation unit. Compose N of these (or use
    registry.py's NR7 rule-local helper) for a multi-bar inside-bar count."""
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        if t < 1:
            return None
        cur, prev = ctx.bars[t], ctx.bars[t - 1]
        if cur.high <= prev.high and cur.low >= prev.low:
            return {"contained_in_range_dollars": round(prev.high - prev.low, 3)}
        return None
    return _p


# ── 11. monotone swing sequence (drives triangle/wedge family) ───────────────

def monotone_swings(
    *, kind: str, non_decreasing: bool, n: int = 2, window: Optional[int] = None,
) -> Predicate:
    """True iff the last `n` swings of `kind` ("swing_high"|"swing_low") confirmed by t
    are monotone non-decreasing (non_decreasing=True) or non-increasing (False).
    "trigger_level" = the MOST RECENT (last) swing's price — the current point of the
    rising/falling line. Powers the triangle/wedge family (TA-PATTERN-REFERENCE.md sec
    C.3-C.7)."""
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        w = ctx.swing_window if window is None else window
        cand = [s for s in ctx.structure.labeled_swings if s.kind == kind and s.bar_index + w <= t]
        if len(cand) < n:
            return None
        recent = cand[-n:]
        prices = [s.price for s in recent]
        if non_decreasing:
            ok = all(prices[i] <= prices[i + 1] for i in range(len(prices) - 1))
        else:
            ok = all(prices[i] >= prices[i + 1] for i in range(len(prices) - 1))
        if not ok:
            return None
        return {
            "swing_prices": [round(p, 2) for p in prices],
            "swing_bar_indices": [s.bar_index for s in recent],
            "trigger_level": round(prices[-1], 2),
        }
    return _p


# ── 12. flat swing cluster (the flat side of a triangle/rectangle/neckline) ──

def flat_side(*, kind: str, n_touches: int = 2, tolerance: float = 0.20, window: Optional[int] = None) -> Predicate:
    """True iff the last `n_touches` swings of `kind` cluster within `tolerance` $ of
    each other. "trigger_level" = their mean price. This is the flat line of a
    triangle's flat side, a rectangle's top/bottom, or a double-top/bottom neckline
    base (level_memory.TOUCH_TOL=0.20 is the matching precedent for "same level")."""
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        w = ctx.swing_window if window is None else window
        cand = [s for s in ctx.structure.labeled_swings if s.kind == kind and s.bar_index + w <= t]
        if len(cand) < n_touches:
            return None
        recent = cand[-n_touches:]
        prices = [s.price for s in recent]
        if max(prices) - min(prices) > tolerance:
            return None
        level = sum(prices) / len(prices)
        return {
            "trigger_level": round(level, 2), "touch_count": n_touches,
            "touch_spread": round(max(prices) - min(prices), 4),
        }
    return _p


# ── 13. pullback depth (flag/pennant continuation geometry) ──────────────────

def pullback_depth(*, max_pct: float = 0.38, lookback: int = 12, min_impulse_pct: float = 0.003) -> Predicate:
    """True iff price has retraced <= `max_pct` of the most recent impulse leg, where
    the impulse leg is the highest-high-to-lowest-low run in the `lookback` bars
    strictly BEFORE t. Sets bias="bullish" for a pullback within an UP impulse (buy the
    dip continuation) / "bearish" for a DOWN impulse. Powers flag_pullback_continuation
    (TA-PATTERN-REFERENCE.md sec C.1). max_pct=0.38 is a common continuation heuristic
    (NOT a Bulkowski statistic — flags/pennants carry no ranked stat per that doc)."""
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        if t < lookback:
            return None
        window = ctx.bars[t - lookback: t]  # excludes t itself
        hi = max(b.high for b in window)
        lo = min(b.low for b in window)
        leg = hi - lo
        if leg <= 0 or (lo > 0 and leg / lo < min_impulse_pct):
            return None
        hi_idx = max(range(len(window)), key=lambda i: window[i].high)
        lo_idx = min(range(len(window)), key=lambda i: window[i].low)
        impulse_up = hi_idx > lo_idx
        c = ctx.bars[t].close
        retrace = (hi - c) / leg if impulse_up else (c - lo) / leg
        if retrace < 0 or retrace > max_pct:
            return None
        return {
            "bias": "bullish" if impulse_up else "bearish",
            "impulse_direction": "up" if impulse_up else "down",
            "retrace_pct": round(retrace, 3), "impulse_dollars": round(leg, 3),
            "impulse_high": round(hi, 2), "impulse_low": round(lo, 2),
        }
    return _p


# ── 14. session-open gap ───────────────────────────────────────────────────────

def gap_event(*, min_gap_pct: float = 0.0025, max_gap_pct: float = 0.015, direction: str = "any") -> Predicate:
    """True iff bar t is the FIRST bar of a new session AND its open gaps between
    `min_gap_pct` and `max_gap_pct` (absolute) vs the prior session's last close. Ports
    the gap math + default thresholds from
    backtest/lib/watchers/gap_and_go_watcher.py::detect_gap_and_go_core (MIN_GAP=0.0025,
    MAX_GAP=0.015). direction: "up" | "down" | "any"."""
    if direction not in ("up", "down", "any"):
        raise ValueError("direction must be 'up', 'down', or 'any'")

    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        if t < 1:
            return None
        cur, prev = ctx.bars[t], ctx.bars[t - 1]
        if cur.open_time.date() == prev.open_time.date():
            return None  # not a session boundary
        prior_close = prev.close
        if prior_close <= 0:
            return None
        gap = cur.open / prior_close - 1.0
        if not (min_gap_pct <= abs(gap) <= max_gap_pct):
            return None
        if direction == "up" and gap <= 0:
            return None
        if direction == "down" and gap >= 0:
            return None
        return {
            "gap_pct": round(gap, 5), "trigger_level": round(prior_close, 2),
            "gap_direction": "up" if gap > 0 else "down",
        }
    return _p


# ── 15. VWAP relation ──────────────────────────────────────────────────────────

def near_vwap(*, max_distance: float = 0.15) -> Predicate:
    """True iff close[t] is within `max_distance` $ of the session VWAP at t (ctx.vwap
    — cumulative, causal, resets per session; see context.py). Powers
    flag_pullback_continuation's "pullback to VWAP" clause and any future VWAP-relation
    rule (VWAP relation is one of the 8 Step-1 primitive categories)."""
    def _p(ctx: PatternContext, t: int) -> Optional[dict]:
        v = ctx.vwap[t]
        c = ctx.bars[t].close
        d = abs(c - v)
        if d > max_distance:
            return None
        return {"vwap": round(v, 2), "vwap_distance": round(d, 4)}
    return _p
