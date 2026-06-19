"""NAMED_LEVEL_SECOND_TEST watcher (WATCH-ONLY per OP-21).

Detects a HIGHER-LOW (support) / LOWER-HIGH (resistance) SECOND test of a named
★★+ level within the same session — a structural "two-touch" confirmation that is
DISTINCT from the single-bar NAMED_LEVEL_WICK_BOUNCE (NLWB) setup.

────────────────────────────────────────────────────────────────────────────────
DISTINCTION FROM NLWB (named_level_wick_bounce_watcher.py) — confirmed distinct:
  NLWB              = ONE bar wicks below a named support and CLOSES BACK ABOVE it.
                      The signal is contained entirely within a single bar's
                      wick-and-reclaim. No memory of earlier tests required.
  NAMED_LEVEL_      = a level was tested EARLIER in the session AND bounced, THEN
  SECOND_TEST         tested AGAIN forming a HIGHER LOW (support) / LOWER HIGH
                      (resistance). REQUIRES two distinct tests across two
                      separated points in time with a higher-low / lower-high
                      structure between them. The edge is the structural sequence
                      (buyers stepping in higher each time), not a single reclaim.
  → SECOND_TEST is a TWO-TOUCH multi-bar structure; NLWB is a ONE-TOUCH single bar.
    A bar can satisfy NLWB without ever having a first test (so they do not
    collapse into each other), and SECOND_TEST does not require the current bar to
    wick BELOW the level at all — only to come within tolerance AND print a higher
    low than test #1.
────────────────────────────────────────────────────────────────────────────────

Motivating case (real 2026-06-18 session, long/support side):
  - PML 743.35 = named support
  - Test #1: 09:45 bar low 743.86 (within $0.51 of the level), bounced +$1.34 within
    the next 2 bars → confirmed first defense.
  - Test #2: 11:45 bar low 744.36 = +$0.50 HIGHER LOW vs test #1, closed green.
  - 11:50 ran to 746.40 (+$2.04 from the second-test bounce zone).

Pattern definition (support / long):
  1. FIRST TEST (history): a prior bar whose low came within LEVEL_TOLERANCE_FIRST
     of a named ★★+ support level, that then BOUNCED >= MIN_BOUNCE_DOLLARS within
     BOUNCE_WINDOW_BARS bars (the level was defended).
  2. SECOND TEST (current bar): the current bar's low is within LEVEL_TOLERANCE_SECOND
     of the SAME level AND current low >= first-test low + MIN_HIGHER_LOW_DOLLARS
     (a HIGHER low) AND the current bar closes GREEN (close > open).
  3. Confirmation: current-bar volume >= VOL_CONFIRM_MULT × 20-bar baseline →
     confidence "high"; without it, "medium". (No look-ahead — next-bar volume is
     unavailable, so the current bar's own volume is the only volume confirmation.)

Resistance / short is the exact mirror: a LOWER-HIGH second test of a named ★★+
resistance, current bar closes RED.

Exit logic (L51/L55 lesson encoded — chart-stop only, premium stop disabled):
  - Entry = current bar close (SPY price).
  - Stop  = current wick low - STOP_BELOW_WICK (long) / wick high + STOP_ABOVE_WICK
            (short).
  - TP1   = entry + TP1_SPY_MOVE OR the nearest named resistance above (long) /
            entry - TP1_SPY_MOVE OR nearest named support below (short),
            WHICHEVER IS CLOSER.
  - Runner= next major resistance / PMH above (long) / next major support / PML
            below (short); falls back to entry +/- RUNNER_SPY_MOVE if none found.

Time gate: 09:45 - 14:30 ET. Cooldown: 30 minutes.

OP-21 promotion gate (NOT YET PASSED):
  - Historical: requires named ★★+ levels from key-levels.json (not archived
    historically — same constraint as floor_hold / close_ceiling). Live watcher
    accumulates observations vs today's key-levels.json.
  - Live gate: N >= 20 observations WR >= 50% → real-fills → 3 live J wins.
  - DO NOT wire into production heartbeat.md until live gate passes.

Sources:
  backtest/lib/watchers/floor_hold_bounce_watcher.py  — structural template
  backtest/lib/watchers/named_level_wick_bounce_watcher.py — NLWB (the single-bar
    sibling this setup is explicitly distinct from)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from .level_source import load_named_levels
from ..filters import BarContext


# ── Detection parameters ─────────────────────────────────────────────────────

# How far back (bars before the current bar) to scan for the FIRST test.
LOOKBACK_BARS: int = 60

# First-test proximity: the first-test bar low must come within this of the level.
# Looser than the NLWB wick threshold — the first test need not wick BELOW; it just
# has to TOUCH the zone and bounce. The 2026-06-18 case was $0.51 above the level.
LEVEL_TOLERANCE_FIRST: float = 0.75

# Second-test proximity: the current bar's low must come within this of the level.
# Wider than the first-test tolerance: a genuine HIGHER LOW sits structurally above
# the level, so the second touch is naturally further away. The motivating
# 2026-06-18 case had test#2 low 744.36 vs PML 743.35 = $1.01 above. $1.25 keeps
# the anchored case reachable while still rejecting a "test" that is several dollars
# off the level (that would be a different swing, not a retest of this level).
LEVEL_TOLERANCE_SECOND: float = 1.25

# The first test must bounce at least this many dollars within BOUNCE_WINDOW_BARS.
MIN_BOUNCE_DOLLARS: float = 0.50

# How many bars after the first-test bar to look for the qualifying bounce.
BOUNCE_WINDOW_BARS: int = 2

# The second test must print a HIGHER low (support) / LOWER high (resistance) than
# the first test by at least this many dollars. 2026-06-18: +$0.50 higher low.
MIN_HIGHER_LOW_DOLLARS: float = 0.30

# Volume confirmation multiplier for the "high" confidence tier.
VOL_CONFIRM_MULT: float = 1.1

# Minimum bars that must separate test #1 and the current second-test bar so the
# two touches are genuinely "distinct" (not the same swing). 1 = at least one bar
# between them.
MIN_BARS_BETWEEN_TESTS: int = 1

# Time window: skip gap-open 15 min, avoid late-session theta drain.
ENTRY_TIME_START: dt.time = dt.time(9, 45)
ENTRY_TIME_END: dt.time = dt.time(14, 30)

# Cooldown: one signal per 30-minute window (prevents hammering the same level).
_COOLDOWN_MINUTES: int = 30

# Named-level gate: only fire at levels with strength.stars >= 2 (mirrors floor_hold).
_MIN_STARS: int = 2

# Roles that qualify as SUPPORT (long side). `type == "support"` is also accepted
# (some levels carry role=null but type=support — e.g. the 2026-06-18 PML).
_SUPPORT_ROLES: frozenset[str] = frozenset({
    "support",
    "carry",
    "broken_to_support",
})

# Roles that qualify as RESISTANCE (short side). `type == "resistance"` also accepted.
_RESISTANCE_ROLES: frozenset[str] = frozenset({
    "resistance",
    "carry",
    "broken_to_resistance",
    "support_flipped_to_resistance",
    "support_broken_to_resistance",
})

# Level `type` values matched IN ADDITION to roles (schema-v3 field the live file
# populates — role=null structural levels like the 2026-06-18 PML carry type only).
_SUPPORT_TYPES: frozenset[str] = frozenset({"support"})
_RESISTANCE_TYPES: frozenset[str] = frozenset({"resistance"})


# ── Exit knobs (conservative OP-21 watch-only defaults) ─────────────────────

DEFAULT_PREMIUM_STOP_PCT: float = -0.99    # chart-stop ONLY — L51/L55
DEFAULT_TP1_PREMIUM_PCT: float = 0.30
DEFAULT_RUNNER_TARGET_PCT: float = 1.5

# SPY-price stop/target geometry
_STOP_BELOW_WICK: float = 0.10      # long stop = second-test wick low - $0.10
_STOP_ABOVE_WICK: float = 0.10      # short stop = second-test wick high + $0.10
_TP1_SPY_MOVE: float = 0.70         # default TP1 distance if no nearer named level
_RUNNER_SPY_MOVE: float = 2.50      # default runner distance if no named level found


# ── Key-levels.json level loading (shared helper, 2026-06-18 schema fix) ──────
#
# Loaded via backtest.lib.watchers.level_source.load_named_levels, which derives
# ★-strength from the schema-v3 `tier` field (Active=2/Carry=3/Reference=2) when the
# planned `strength.stars` object is absent — it IS absent in the live file, so the
# original loader's `entry.get("strength",{}).get("stars",0) >= 2` was always False
# and this watcher fired on NOTHING live. Psychological/round-number levels are
# capped at ★ by the shared loader so they never clear the >=2 gate.
#
# Test/self-test override: _force_levels() sets the module globals _cached_support /
# _cached_resistance / _cached_levels_date to bypass file I/O. When the date matches,
# we honour those injected lists verbatim; otherwise we delegate to the shared loader.
_cached_support: list[float] = []
_cached_resistance: list[float] = []
_cached_levels_date: Optional[str] = None


def _load_named_levels(today_str: str) -> tuple[list[float], list[float]]:
    """Load (support_levels, resistance_levels), each ★★+, for today.

    Honours the _force_levels() injection override (_cached_support /
    _cached_resistance / _cached_levels_date). Returns sorted unique prices;
    ([], []) if the file is missing/corrupt (watcher then returns None gracefully).
    """
    if _cached_levels_date == today_str:
        return _cached_support, _cached_resistance

    supports = load_named_levels(
        today_str, roles=_SUPPORT_ROLES, types=_SUPPORT_TYPES, min_stars=_MIN_STARS
    )
    resistances = load_named_levels(
        today_str, roles=_RESISTANCE_ROLES, types=_RESISTANCE_TYPES, min_stars=_MIN_STARS
    )
    return supports, resistances


# ── Pure structural detectors (no ctx, easily unit-tested) ───────────────────

def _find_first_support_test(
    lows: list[float],
    highs: list[float],
    level: float,
) -> Optional[tuple[int, float]]:
    """Find the FIRST bar (earliest index) that tested `level` as support and bounced.

    A qualifying first test:
      low within LEVEL_TOLERANCE_FIRST of level, AND a subsequent bar within
      BOUNCE_WINDOW_BARS prints a high >= that bar's low + MIN_BOUNCE_DOLLARS.

    Returns (first_test_idx, first_test_low) or None.
    `lows`/`highs` are positional history EXCLUDING the current bar.
    """
    n = len(lows)
    for i in range(n):
        low_i = lows[i]
        # Touched the support zone?
        if abs(low_i - level) > LEVEL_TOLERANCE_FIRST:
            continue
        # Bounced within the window?
        window_end = min(n, i + 1 + BOUNCE_WINDOW_BARS)
        bounced = False
        for j in range(i + 1, window_end):
            if highs[j] - low_i >= MIN_BOUNCE_DOLLARS:
                bounced = True
                break
        if bounced:
            return i, low_i
    return None


def _find_first_resistance_test(
    lows: list[float],
    highs: list[float],
    level: float,
) -> Optional[tuple[int, float]]:
    """Mirror of _find_first_support_test for resistance (short side).

    Qualifying: high within LEVEL_TOLERANCE_FIRST of level, AND a subsequent bar
    within BOUNCE_WINDOW_BARS prints a low <= that bar's high - MIN_BOUNCE_DOLLARS
    (rejected back down). Returns (idx, first_test_high) or None.
    """
    n = len(highs)
    for i in range(n):
        high_i = highs[i]
        if abs(high_i - level) > LEVEL_TOLERANCE_FIRST:
            continue
        window_end = min(n, i + 1 + BOUNCE_WINDOW_BARS)
        rejected = False
        for j in range(i + 1, window_end):
            if high_i - lows[j] >= MIN_BOUNCE_DOLLARS:
                rejected = True
                break
        if rejected:
            return i, high_i
    return None


# ── Module-level cooldown state ───────────────────────────────────────────────

_last_signal_time: Optional[dt.datetime] = None


# ── Public detector ───────────────────────────────────────────────────────────

def detect_named_level_second_test_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect NAMED_LEVEL_SECOND_TEST (higher-low / lower-high second touch).

    direction="long"  for a HIGHER-LOW second test of named ★★+ support.
    direction="short" for a LOWER-HIGH second test of named ★★+ resistance.

    Returns None if any gate fails. Confidence "high" with volume confirmation
    (vol >= 1.1× baseline), else "medium".
    """
    global _last_signal_time

    # ── Gate 1: Time window (09:45 - 14:30 ET) ──────────────────────────────
    bar_time = ctx.timestamp_et.time()
    if bar_time < ENTRY_TIME_START or bar_time > ENTRY_TIME_END:
        return None

    # ── Gate 2: Cooldown ─────────────────────────────────────────────────────
    if _last_signal_time is not None:
        elapsed_min = (ctx.timestamp_et - _last_signal_time).total_seconds() / 60.0
        if elapsed_min < _COOLDOWN_MINUTES:
            return None

    # ── Gate 3: Named ★★+ levels available ───────────────────────────────────
    today_str = ctx.timestamp_et.date().isoformat()
    support_levels, resistance_levels = _load_named_levels(today_str)
    if not support_levels and not resistance_levels:
        return None

    # ── Current-bar OHLCV ─────────────────────────────────────────────────────
    bar_open = float(ctx.bar.get("open", 0))
    bar_high = float(ctx.bar.get("high", 0))
    bar_low = float(ctx.bar.get("low", 0))
    bar_close = float(ctx.bar.get("close", 0))

    # ── History EXCLUDING the current bar (prior_bars has current at [-1]) ────
    prior_df = ctx.prior_bars
    if prior_df is None or len(prior_df) < MIN_BARS_BETWEEN_TESTS + 2:
        return None
    scan_df = prior_df.tail(LOOKBACK_BARS + 1).iloc[:-1]
    if len(scan_df) < MIN_BARS_BETWEEN_TESTS + 1:
        return None
    hist_lows: list[float] = scan_df["low"].tolist()
    hist_highs: list[float] = scan_df["high"].tolist()
    n_hist = len(hist_lows)

    vol_baseline = getattr(ctx, "vol_baseline_20", 0.0) or 0.0
    bar_vol = float(ctx.bar.get("volume", 0))
    vol_ratio = (bar_vol / vol_baseline) if vol_baseline > 0 else 0.0
    vol_confirmed = vol_ratio >= VOL_CONFIRM_MULT
    vix_now = getattr(ctx, "vix_now", None) or 17.0

    # ── Try SUPPORT (long) — higher-low second test ──────────────────────────
    best: Optional[dict] = None  # winning candidate description

    for level in support_levels:
        # Current bar must be within tolerance of the level (second touch) ...
        if abs(bar_low - level) > LEVEL_TOLERANCE_SECOND:
            continue
        # ... and close GREEN (bounce confirmed on this bar).
        if bar_close <= bar_open:
            continue
        first = _find_first_support_test(hist_lows, hist_highs, level)
        if first is None:
            continue
        first_idx, first_low = first
        # Distinct-tests guard: at least MIN_BARS_BETWEEN_TESTS bars between the
        # first test and the current bar. first_idx is positional in `scan_df`;
        # the current bar sits one position after scan_df's last index.
        bars_between = (n_hist - first_idx)  # >=1 since first_idx in [0, n_hist-1]
        if bars_between < MIN_BARS_BETWEEN_TESTS + 1:
            continue
        # HIGHER LOW requirement.
        higher_low_by = round(bar_low - first_low, 2)
        if higher_low_by < MIN_HIGHER_LOW_DOLLARS:
            continue
        # Candidate qualifies. Prefer the LARGEST higher-low margin (strongest).
        if best is None or higher_low_by > best["margin"]:
            best = {
                "direction": "long",
                "level": level,
                "first_idx": first_idx,
                "first_extreme": first_low,
                "margin": higher_low_by,
                "bars_between": bars_between,
            }

    # ── Try RESISTANCE (short) — lower-high second test ──────────────────────
    for level in resistance_levels:
        if abs(bar_high - level) > LEVEL_TOLERANCE_SECOND:
            continue
        if bar_close >= bar_open:   # short needs a RED bar
            continue
        first = _find_first_resistance_test(hist_lows, hist_highs, level)
        if first is None:
            continue
        first_idx, first_high = first
        bars_between = (n_hist - first_idx)
        if bars_between < MIN_BARS_BETWEEN_TESTS + 1:
            continue
        lower_high_by = round(first_high - bar_high, 2)
        if lower_high_by < MIN_HIGHER_LOW_DOLLARS:
            continue
        if best is None or lower_high_by > best["margin"]:
            best = {
                "direction": "short",
                "level": level,
                "first_idx": first_idx,
                "first_extreme": first_high,
                "margin": lower_high_by,
                "bars_between": bars_between,
            }

    if best is None:
        return None

    # ── Build the signal ──────────────────────────────────────────────────────
    _last_signal_time = ctx.timestamp_et

    direction = best["direction"]
    level = best["level"]
    margin = best["margin"]
    first_extreme = best["first_extreme"]

    if direction == "long":
        stop_price = round(bar_low - _STOP_BELOW_WICK, 2)
        # TP1 = nearer of (entry + $0.70) or nearest named resistance above entry.
        default_tp1 = bar_close + _TP1_SPY_MOVE
        res_above = [r for r in resistance_levels if r > bar_close]
        if res_above:
            nearest_res = min(res_above)
            tp1_price = round(min(default_tp1, nearest_res), 2)
        else:
            tp1_price = round(default_tp1, 2)
        # Runner = next major resistance above TP1, else entry + $2.50.
        res_above_tp1 = [r for r in resistance_levels if r > tp1_price + 0.01]
        if res_above_tp1:
            runner_price = round(min(res_above_tp1), 2)
        else:
            runner_price = round(bar_close + _RUNNER_SPY_MOVE, 2)
        second_extreme = bar_low
        struct_word = "HIGHER LOW"
    else:  # short
        stop_price = round(bar_high + _STOP_ABOVE_WICK, 2)
        default_tp1 = bar_close - _TP1_SPY_MOVE
        sup_below = [s for s in support_levels if s < bar_close]
        if sup_below:
            nearest_sup = max(sup_below)
            tp1_price = round(max(default_tp1, nearest_sup), 2)
        else:
            tp1_price = round(default_tp1, 2)
        sup_below_tp1 = [s for s in support_levels if s < tp1_price - 0.01]
        if sup_below_tp1:
            runner_price = round(max(sup_below_tp1), 2)
        else:
            runner_price = round(bar_close - _RUNNER_SPY_MOVE, 2)
        second_extreme = bar_high
        struct_word = "LOWER HIGH"

    confidence = "high" if vol_confirmed else "medium"

    if vix_now < 15:
        vix_bucket = "<15"
    elif vix_now < 20:
        vix_bucket = "15-20"
    elif vix_now < 25:
        vix_bucket = "20-25"
    else:
        vix_bucket = ">=25"

    side_kind = "support" if direction == "long" else "resistance"
    instrument = "calls" if direction == "long" else "puts"
    vol_note = (
        f"vol={vol_ratio:.1f}x baseline (>= {VOL_CONFIRM_MULT}x → confirmed)"
        if vol_confirmed
        else f"vol={vol_ratio:.1f}x baseline (< {VOL_CONFIRM_MULT}x → unconfirmed, medium conf)"
    )

    reason = (
        f"Named-level SECOND TEST ({struct_word}) at ★★+ {side_kind} ${level:.2f}: "
        f"test #1 extreme={first_extreme:.2f}, test #2 (this bar) extreme={second_extreme:.2f} "
        f"= {margin:.2f} {struct_word.lower()} ({best['bars_between']} bars apart). "
        f"Bar closed {'green' if direction == 'long' else 'red'} (C:{bar_close:.2f} vs O:{bar_open:.2f}). "
        f"Direction: {direction} (buy {instrument}). "
        f"Entry={bar_close:.2f} Stop={stop_price:.2f} TP1={tp1_price:.2f} Runner={runner_price:.2f}. "
        f"{vol_note}. VIX={vix_now:.1f} ({vix_bucket}). "
        f"DISTINCT from NLWB: two-touch higher-low structure, not a single-bar wick reclaim. "
        f"Motivating case: 2026-06-18 PML 743.35 double test → +$2.04."
    )

    return WatcherSignal(
        watcher_name="named_level_second_test_watcher",
        setup_name="NAMED_LEVEL_SECOND_TEST",
        direction=direction,
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=reason,
        triggers_fired=[
            "NAMED_LEVEL_FIRST_TEST_BOUNCE",
            "SECOND_TEST_HIGHER_LOW" if direction == "long" else "SECOND_TEST_LOWER_HIGH",
            f"VOL_{vol_ratio:.1f}X" if vol_confirmed else "VOL_UNCONFIRMED",
        ],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "side": side_kind,
            "named_level": level,
            "first_test_extreme": round(first_extreme, 2),
            "second_test_extreme": round(second_extreme, 2),
            "structure_margin_dollars": margin,
            "bars_between_tests": best["bars_between"],
            "vol_ratio": round(vol_ratio, 2),
            "vol_confirmed": vol_confirmed,
            "vix_now": vix_now,
            "vix_bucket": vix_bucket,
            "distinct_from_nlwb": (
                "SECOND_TEST = two-touch higher-low/lower-high structure across "
                "separated bars; NLWB = single-bar wick-below-and-reclaim."
            ),
            "promotion_gate": (
                "OP-21: historical gate bypassed (no key-levels archive). "
                "Live gate: N>=20 obs WR>=50% → real-fills → 3 live J wins."
            ),
            "motivating_case": "2026-06-18 PML 743.35 (09:45 test#1 → 11:45 +$0.50 higher low → 11:50 746.40)",
        },
    )


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys

    def _mk_ctx(rows, *, vix=17.0, vol_baseline=1000.0):
        """Build a BarContext from a list of OHLCV+ts dicts (last row = current bar)."""
        df = pd.DataFrame(rows)
        cur = df.iloc[-1]
        return BarContext(
            bar_idx=len(df) - 1,
            timestamp_et=cur["timestamp_et"],
            bar=cur,
            prior_bars=df,                 # full history INCLUDING current at [-1]
            ribbon_now=None,
            ribbon_history=[],
            vix_now=vix,
            vix_prior=vix,
            vol_baseline_20=vol_baseline,
            range_baseline_20=0.5,
            levels_active=[],
            multi_day_levels=[],
            htf_15m_stack=None,
        )

    def _reset():
        global _last_signal_time, _cached_support, _cached_resistance, _cached_levels_date
        _last_signal_time = None
        _cached_support = []
        _cached_resistance = []
        _cached_levels_date = None

    # Force a deterministic level set (the real PML 743.35 long case) — patch the
    # day-cache so the test does not depend on the live key-levels.json contents.
    def _force_levels(supports, resistances, day):
        global _cached_support, _cached_resistance, _cached_levels_date
        _cached_support = sorted(set(supports))
        _cached_resistance = sorted(set(resistances))
        _cached_levels_date = day

    def _ts(h, m):
        return dt.datetime(2026, 6, 18, h, m)

    LEVEL = 743.35
    DAY = "2026-06-18"
    results: list[tuple[str, bool]] = []

    # ── FIXTURE A — SHOULD FIRE: 2026-06-18 PML higher-low second test ───────
    # test#1 ~09:45 low 743.86 (within $0.51), bounce +$1.34; drift; test#2 (current)
    # low 744.36 = +$0.50 higher low, closes green, with volume confirmation.
    _reset()
    rows_a = []
    # Filler bars well above the level (no accidental first test) 09:35-09:40
    rows_a.append(dict(timestamp_et=_ts(9, 35), open=746.0, high=746.3, low=745.7, close=746.1, volume=900))
    rows_a.append(dict(timestamp_et=_ts(9, 40), open=746.1, high=746.4, low=745.5, close=745.6, volume=950))
    # test#1 bar @09:45 — low 743.86 touches the zone
    rows_a.append(dict(timestamp_et=_ts(9, 45), open=745.0, high=745.2, low=743.86, close=744.2, volume=1500))
    # bounce confirmation within 2 bars (+$1.34 → high 745.20)
    rows_a.append(dict(timestamp_et=_ts(9, 50), open=744.2, high=745.20, low=744.0, close=745.0, volume=1300))
    # drift bars between the two tests (stay above the level, no second touch yet)
    for hh, mm in [(10, 0), (10, 30), (11, 0), (11, 30), (11, 40)]:
        rows_a.append(dict(timestamp_et=_ts(hh, mm), open=745.5, high=746.0, low=744.9, close=745.4, volume=800))
    # current bar = test#2 @ 11:45 — low 744.36 (+$0.50 higher low vs 743.86),
    # closes green, volume 1.2x baseline (1200/1000)
    rows_a.append(dict(timestamp_et=_ts(11, 45), open=744.6, high=745.0, low=744.36, close=744.95, volume=1200))
    ctx_a = _mk_ctx(rows_a, vix=17.0, vol_baseline=1000.0)
    _force_levels([LEVEL], [747.0, 748.0], DAY)
    sig_a = detect_named_level_second_test_setup(ctx_a)
    fired_a = sig_a is not None and sig_a.direction == "long"
    results.append(("A: PML higher-low 2nd test SHOULD fire (long)", fired_a))
    if sig_a is not None:
        print(f"[A] FIRED dir={sig_a.direction} conf={sig_a.confidence} "
              f"entry={sig_a.entry_price:.2f} stop={sig_a.stop_price:.2f} "
              f"tp1={sig_a.tp1_price:.2f} runner={sig_a.runner_price:.2f} "
              f"margin={sig_a.metadata['structure_margin_dollars']}")
    else:
        print("[A] no signal")

    # ── FIXTURE B — SHOULD NOT FIRE: LOWER low (broke support, not a higher low) ─
    _reset()
    rows_b = list(rows_a[:-1])  # same history
    # current bar prints a LOWER low than test#1 (743.50 < 743.86) → fails higher-low
    rows_b.append(dict(timestamp_et=_ts(11, 45), open=744.0, high=744.3, low=743.50, close=744.1, volume=1200))
    ctx_b = _mk_ctx(rows_b, vix=17.0, vol_baseline=1000.0)
    _force_levels([LEVEL], [747.0, 748.0], DAY)
    sig_b = detect_named_level_second_test_setup(ctx_b)
    results.append(("B: LOWER low (not higher) should NOT fire", sig_b is None))
    print(f"[B] {'no signal (correct)' if sig_b is None else 'FIRED (wrong!)'}")

    # ── FIXTURE C — SHOULD NOT FIRE: no first test (current is the FIRST touch) ─
    _reset()
    rows_c = []
    for k in range(0, 8):
        rows_c.append(dict(timestamp_et=_ts(11, 0 + k), open=746.0, high=746.3, low=745.6, close=746.0, volume=900))
    # current bar touches the level for the FIRST time, green — but no prior bounce
    rows_c.append(dict(timestamp_et=_ts(11, 45), open=744.0, high=744.8, low=743.9, close=744.7, volume=1200))
    ctx_c = _mk_ctx(rows_c, vix=17.0, vol_baseline=1000.0)
    _force_levels([LEVEL], [747.0, 748.0], DAY)
    sig_c = detect_named_level_second_test_setup(ctx_c)
    results.append(("C: no first-test bounce should NOT fire", sig_c is None))
    print(f"[C] {'no signal (correct)' if sig_c is None else 'FIRED (wrong!)'}")

    # ── FIXTURE D — SHOULD FIRE: resistance lower-high second test (short) ────
    _reset()
    RLEVEL = 750.62
    rows_d = []
    rows_d.append(dict(timestamp_et=_ts(9, 35), open=748.0, high=748.5, low=747.8, close=748.2, volume=900))
    # test#1 @09:40 — high 750.50 touches resistance zone, then rejects -$1.0
    rows_d.append(dict(timestamp_et=_ts(9, 40), open=749.5, high=750.50, low=749.4, close=749.6, volume=1500))
    rows_d.append(dict(timestamp_et=_ts(9, 45), open=749.6, high=749.8, low=749.50, close=749.55, volume=1300))
    for mm in (0, 10, 20, 30):  # 10:xx drift below resistance
        rows_d.append(dict(timestamp_et=_ts(10, mm), open=749.0, high=749.5, low=748.8, close=749.2, volume=800))
    # current bar = test#2 — high 750.12 = $0.38 LOWER high, closes red, vol confirmed
    rows_d.append(dict(timestamp_et=_ts(10, 40), open=749.9, high=750.12, low=749.3, close=749.4, volume=1200))
    ctx_d = _mk_ctx(rows_d, vix=17.0, vol_baseline=1000.0)
    _force_levels([743.35], [RLEVEL], DAY)
    sig_d = detect_named_level_second_test_setup(ctx_d)
    fired_d = sig_d is not None and sig_d.direction == "short"
    results.append(("D: resistance lower-high 2nd test SHOULD fire (short)", fired_d))
    if sig_d is not None:
        print(f"[D] FIRED dir={sig_d.direction} conf={sig_d.confidence} "
              f"entry={sig_d.entry_price:.2f} stop={sig_d.stop_price:.2f} "
              f"tp1={sig_d.tp1_price:.2f} runner={sig_d.runner_price:.2f} "
              f"margin={sig_d.metadata['structure_margin_dollars']}")
    else:
        print("[D] no signal")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n=== NAMED_LEVEL_SECOND_TEST self-test ===")
    all_pass = True
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        all_pass = all_pass and ok
    print(f"=== {'ALL PASS' if all_pass else 'SOME FAILED'} ===")
    _sys.exit(0 if all_pass else 1)
