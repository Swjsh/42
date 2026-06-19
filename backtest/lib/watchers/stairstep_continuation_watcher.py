"""STAIRSTEP_CONTINUATION watcher (WATCH-ONLY per OP-21).

Detects a continuation setup at a BROKEN named level where successive retests from
the broken side form a STRICT monotonic stairstep — progressively LOWER highs
(descending → short / puts) or progressively HIGHER lows (ascending → long / calls).

Pattern named after the missed 2026-05-07 735.40 sequence (playbook CANDIDATE
STAIRSTEP_CONTINUATION):
  - 735.40 broke to the downside, then three retests printed strictly lower highs:
      736.12 → 735.61 → 735.41  (LH-LH-LH)
  - SPY then continued -$5.65 to 729.75.
  - The system bought calls at 12:30 (counter-trend trap) — J's eye saw the stairstep
    the engine missed.

Hypothesis (playbook): when a key level breaks AND each subsequent retest from the
broken side prints a progressively lower high (or higher low for a support flip),
the level has rotated from defending to capping. Once 3+ rejections form a strict
sequence, continuation in the broken direction is the high-edge trade.

Detection (this watcher):
  1. BROKEN LEVEL — a named level qualifies as "broken to resistance" if its
     key-levels.json role is broken_to_resistance / support_flipped_to_resistance /
     support_broken_to_resistance, OR (fallback) price clearly broke a named level
     earlier today and is now trading on the broken side (a 5m close past it by
     >= BREAK_CLOSE_DOLLARS, and the current bar is on the broken side). Mirror for
     "broken to support".
  2. STAIRSTEP — collect the per-retest extreme of every bar that came within
     RETEST_TOLERANCE of the level FROM THE BROKEN SIDE. Require >= MIN_RETESTS
     such extremes forming a STRICT monotonic sequence (each strictly lower high
     for descending; each strictly higher low for ascending).
  3. CONFIRMING BAR — the last closed bar (the current bar) closes on the broken
     side AND is the right color (red for short / green for long).

Exit logic (L51/L55 — chart-stop only, premium stop disabled):
  - Entry  = current bar close (SPY price).
  - Stop   = most-recent retest HIGH + STOP_BUFFER (short) / most-recent retest LOW
             - STOP_BUFFER (long). If the stairstep is intact, price should not
             revisit the prior retest extreme.
  - TP1    = entry -/+ TP1_SPY_MOVE OR the next named level beyond entry in the
             continuation direction, WHICHEVER IS CLOSER.
  - Runner = the next major named level beyond TP1, else entry -/+ RUNNER_SPY_MOVE.

Time gate: 09:45 - 15:00 ET. Cooldown: 30 minutes.

OP-21 promotion gate (NOT YET PASSED — n=1 paper observation per playbook):
  - Live gate: N >= 20 obs WR >= 50% → real-fills → 3 live J wins.
  - DO NOT wire into production heartbeat.md until live gate passes.

Sources:
  strategy/playbook.md — CANDIDATE STAIRSTEP_CONTINUATION (the 5/07 735.40 case)
  strategy/key-levels-protocol.md §8 — role + bounce_history (stairstep memory)
  backtest/lib/watchers/floor_hold_bounce_watcher.py — structural template
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from .level_source import load_named_levels
from ..filters import BarContext


# ── Detection parameters ─────────────────────────────────────────────────────

# How far back (bars before the current bar) to scan for retests + the break.
LOOKBACK_BARS: int = 60

# A bar "retests" the level if its extreme (high for resistance / low for support)
# comes within this many dollars of the level, on the broken side.
RETEST_TOLERANCE: float = 0.75

# Minimum number of retest extremes forming the strict monotonic stairstep.
MIN_RETESTS: int = 3

# Fallback break detection: a prior bar closed past a named level by at least this.
BREAK_CLOSE_DOLLARS: float = 0.10

# Confirming bar must close past the level by at least this (on the broken side).
CONFIRM_CLOSE_DOLLARS: float = 0.01

# Time window.
ENTRY_TIME_START: dt.time = dt.time(9, 45)
ENTRY_TIME_END: dt.time = dt.time(15, 0)

# Cooldown: one signal per 30-minute window.
_COOLDOWN_MINUTES: int = 30

# Named-level gate: only fire at levels with strength.stars >= 2 (mirrors floor_hold).
_MIN_STARS: int = 2

# Roles that explicitly mark a level as already BROKEN to resistance (price below,
# level now caps). Short / descending side.
_BROKEN_TO_RESISTANCE_ROLES: frozenset[str] = frozenset({
    "broken_to_resistance",
    "support_flipped_to_resistance",
    "support_broken_to_resistance",
})

# Roles that explicitly mark a level as already BROKEN to support (price above,
# level now floors). Long / ascending side.
_BROKEN_TO_SUPPORT_ROLES: frozenset[str] = frozenset({
    "broken_to_support",
    "resistance_flipped_to_support",
    "resistance_broken_to_support",
})

# "All structural named levels" = the union of every support/resistance role plus
# both structural types. Passing this to the shared loader returns every ★★+ named
# level EXCEPT pure psychological/round-number levels (which are capped at ★ and so
# excluded — correct: a round-number magnet is not a stairstep break candidate).
_ALL_STRUCTURAL_ROLES: frozenset[str] = (
    _BROKEN_TO_RESISTANCE_ROLES
    | _BROKEN_TO_SUPPORT_ROLES
    | frozenset({"support", "resistance", "carry"})
)
_ALL_STRUCTURAL_TYPES: frozenset[str] = frozenset({"support", "resistance", "transition"})


# ── Exit knobs (conservative OP-21 watch-only defaults) ─────────────────────

DEFAULT_PREMIUM_STOP_PCT: float = -0.99    # chart-stop ONLY — L51/L55
DEFAULT_TP1_PREMIUM_PCT: float = 0.30
DEFAULT_RUNNER_TARGET_PCT: float = 1.5

_STOP_BUFFER: float = 0.10          # stop beyond the most-recent retest extreme
_TP1_SPY_MOVE: float = 0.70         # default TP1 distance if no nearer named level
_RUNNER_SPY_MOVE: float = 2.50      # default runner distance if no named level found


# ── Key-levels.json level loading (shared helper, 2026-06-18 schema fix) ──────
#
# Loaded via backtest.lib.watchers.level_source.load_named_levels, which derives
# ★-strength from the schema-v3 `tier` field when `strength.stars` is absent (it is,
# in the live file). The original loader read `strength.stars` directly → always 0 →
# empty all_levels → this watcher fired on NOTHING live.
#
# Self-test override: _force_levels() sets the module globals _cached_all /
# _cached_broken_res / _cached_broken_sup / _cached_levels_date to bypass file I/O.
# When the date matches, we honour those injected lists verbatim; otherwise delegate.
_cached_all: list[float] = []
_cached_broken_res: list[float] = []
_cached_broken_sup: list[float] = []
_cached_levels_date: Optional[str] = None


def _load_named_levels(
    today_str: str,
) -> tuple[list[float], list[float], list[float]]:
    """Load (all_levels, broken_to_resistance, broken_to_support), each ★★+, for today.

    Honours the _force_levels() injection override. Returns sorted unique prices;
    ([], [], []) if the file is missing/corrupt (watcher then returns None gracefully).
    """
    if _cached_levels_date == today_str:
        return _cached_all, _cached_broken_res, _cached_broken_sup

    all_levels = load_named_levels(
        today_str, roles=_ALL_STRUCTURAL_ROLES, types=_ALL_STRUCTURAL_TYPES,
        min_stars=_MIN_STARS,
    )
    broken_res = load_named_levels(
        today_str, roles=_BROKEN_TO_RESISTANCE_ROLES, min_stars=_MIN_STARS
    )
    broken_sup = load_named_levels(
        today_str, roles=_BROKEN_TO_SUPPORT_ROLES, min_stars=_MIN_STARS
    )
    return all_levels, broken_res, broken_sup


# ── Pure structural helpers ───────────────────────────────────────────────────

def _broke_below_intraday(
    closes: list[float],
    level: float,
) -> bool:
    """Fallback: did any prior bar close >= BREAK_CLOSE_DOLLARS BELOW the level?

    Indicates the level broke to the downside earlier in the session (→ resistance).
    """
    return any(c <= level - BREAK_CLOSE_DOLLARS for c in closes)


def _broke_above_intraday(
    closes: list[float],
    level: float,
) -> bool:
    """Fallback: did any prior bar close >= BREAK_CLOSE_DOLLARS ABOVE the level?

    Indicates the level broke to the upside earlier in the session (→ support).
    """
    return any(c >= level + BREAK_CLOSE_DOLLARS for c in closes)


def _collect_descending_retests(
    highs: list[float],
    closes: list[float],
    level: float,
) -> list[float]:
    """Per-RETEST highs that poked up toward `level` from BELOW (broken-to-resistance).

    A genuine retest is a LOCAL SWING HIGH — a bar that poked up toward the level and
    was rejected — not every bar that merely drifts near the level. Filtering to
    local peaks is what separates the stairstep highs (736.12, 735.61, 735.41) from
    the small bounce-leg bars between them.

    A bar at index i qualifies if:
      - it closed below the level (still on the broken side), AND
      - its high is within RETEST_TOLERANCE below the level (poked toward it), AND
      - its high is a LOCAL MAXIMUM: strictly greater than the previous bar's high
        and >= the next bar's high (a rejection peak). Endpoints compare against the
        single available neighbour.

    Returns the swing-high prices in time order — caller checks strict monotonicity.
    """
    out: list[float] = []
    n = len(highs)
    for i in range(n):
        h, c = highs[i], closes[i]
        if c >= level:
            continue
        if (level - h) > RETEST_TOLERANCE or h > level + RETEST_TOLERANCE:
            continue
        prev_h = highs[i - 1] if i > 0 else float("-inf")
        next_h = highs[i + 1] if i + 1 < n else float("-inf")
        if h > prev_h and h >= next_h:
            out.append(h)
    return out


def _collect_ascending_retests(
    lows: list[float],
    closes: list[float],
    level: float,
) -> list[float]:
    """Per-RETEST lows that poked down toward `level` from ABOVE (broken-to-support).

    Mirror of _collect_descending_retests: a genuine retest is a LOCAL SWING LOW —
    a bar that dipped toward the level and was supported — not every near-level bar.

    A bar at index i qualifies if:
      - it closed above the level (still on the broken side), AND
      - its low is within RETEST_TOLERANCE above the level (poked toward it), AND
      - its low is a LOCAL MINIMUM: strictly less than the previous bar's low and
        <= the next bar's low (a support dip).

    Returns the swing-low prices in time order — caller checks strict monotonicity.
    """
    out: list[float] = []
    n = len(lows)
    for i in range(n):
        l, c = lows[i], closes[i]
        if c <= level:
            continue
        if (l - level) > RETEST_TOLERANCE or l < level - RETEST_TOLERANCE:
            continue
        prev_l = lows[i - 1] if i > 0 else float("inf")
        next_l = lows[i + 1] if i + 1 < n else float("inf")
        if l < prev_l and l <= next_l:
            out.append(l)
    return out


def _longest_strict_monotonic_tail(seq: list[float], *, decreasing: bool) -> list[float]:
    """Return the longest strictly-monotonic run ENDING at the last element.

    For `decreasing=True`: each element strictly less than the previous (lower highs).
    For `decreasing=False`: each element strictly greater than the previous (higher lows).
    Walking backward from the end captures the most-recent stairstep, ignoring older
    noise. Returns the run in forward (time) order.
    """
    if not seq:
        return []
    run = [seq[-1]]
    for x in reversed(seq[:-1]):
        if decreasing:
            if x > run[-1]:        # going back in time, earlier high must be HIGHER
                run.append(x)
            else:
                break
        else:
            if x < run[-1]:        # earlier low must be LOWER
                run.append(x)
            else:
                break
    return list(reversed(run))


# ── Module-level cooldown state ───────────────────────────────────────────────

_last_signal_time: Optional[dt.datetime] = None


# ── Public detector ───────────────────────────────────────────────────────────

def detect_stairstep_continuation_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect STAIRSTEP_CONTINUATION at a broken named level.

    direction="short" for a DESCENDING stairstep (lower highs) at a broken-to-
        resistance level — continuation down (buy puts).
    direction="long"  for an ASCENDING stairstep (higher lows) at a broken-to-
        support level — continuation up (buy calls).

    Returns None if any gate fails. Confidence scales with the retest count.
    """
    global _last_signal_time

    # ── Gate 1: Time window (09:45 - 15:00 ET) ──────────────────────────────
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
    all_levels, broken_res, broken_sup = _load_named_levels(today_str)
    if not all_levels:
        return None

    # ── Current-bar OHLCV ─────────────────────────────────────────────────────
    bar_open = float(ctx.bar.get("open", 0))
    bar_close = float(ctx.bar.get("close", 0))

    # ── History EXCLUDING the current bar ─────────────────────────────────────
    prior_df = ctx.prior_bars
    if prior_df is None or len(prior_df) < MIN_RETESTS + 1:
        return None
    scan_df = prior_df.tail(LOOKBACK_BARS + 1).iloc[:-1]
    if len(scan_df) < MIN_RETESTS:
        return None
    hist_highs: list[float] = scan_df["high"].tolist()
    hist_lows: list[float] = scan_df["low"].tolist()
    hist_closes: list[float] = scan_df["close"].tolist()

    vix_now = getattr(ctx, "vix_now", None) or 17.0
    bar_red = bar_close < bar_open
    bar_green = bar_close > bar_open

    best: Optional[dict] = None

    # ── DESCENDING stairstep (short) at broken-to-resistance levels ──────────
    # Candidate levels: explicit broken-to-resistance role, OR fallback intraday break.
    desc_candidates = set(broken_res)
    for lvl in all_levels:
        if _broke_below_intraday(hist_closes, lvl):
            desc_candidates.add(lvl)

    for level in sorted(desc_candidates):
        # Confirming bar: current close on the broken side (below) + red.
        if bar_close > level - CONFIRM_CLOSE_DOLLARS:
            continue
        if not bar_red:
            continue
        retests = _collect_descending_retests(hist_highs, hist_closes, level)
        run = _longest_strict_monotonic_tail(retests, decreasing=True)
        if len(run) < MIN_RETESTS:
            continue
        # Strongest = longest run; tiebreak by total descent across the run.
        descent = round(run[0] - run[-1], 2)
        score = (len(run), descent)
        if best is None or score > best["score"]:
            best = {
                "direction": "short",
                "level": level,
                "run": run,
                "recent_extreme": run[-1],   # most-recent (lowest) retest high
                "descent": descent,
                "score": score,
                "from_role": level in broken_res,
            }

    # ── ASCENDING stairstep (long) at broken-to-support levels ───────────────
    asc_candidates = set(broken_sup)
    for lvl in all_levels:
        if _broke_above_intraday(hist_closes, lvl):
            asc_candidates.add(lvl)

    for level in sorted(asc_candidates):
        if bar_close < level + CONFIRM_CLOSE_DOLLARS:
            continue
        if not bar_green:
            continue
        retests = _collect_ascending_retests(hist_lows, hist_closes, level)
        run = _longest_strict_monotonic_tail(retests, decreasing=False)
        if len(run) < MIN_RETESTS:
            continue
        ascent = round(run[-1] - run[0], 2)
        score = (len(run), ascent)
        if best is None or score > best["score"]:
            best = {
                "direction": "long",
                "level": level,
                "run": run,
                "recent_extreme": run[-1],   # most-recent (highest) retest low
                "ascent": ascent,
                "score": score,
                "from_role": level in broken_sup,
            }

    if best is None:
        return None

    # ── Build the signal ──────────────────────────────────────────────────────
    _last_signal_time = ctx.timestamp_et

    direction = best["direction"]
    level = best["level"]
    run = best["run"]
    recent_extreme = best["recent_extreme"]
    n_retests = len(run)

    if direction == "short":
        stop_price = round(recent_extreme + _STOP_BUFFER, 2)
        default_tp1 = bar_close - _TP1_SPY_MOVE
        below = [x for x in all_levels if x < bar_close]
        if below:
            tp1_price = round(max(default_tp1, max(below)), 2)
        else:
            tp1_price = round(default_tp1, 2)
        below_tp1 = [x for x in all_levels if x < tp1_price - 0.01]
        runner_price = round(max(below_tp1), 2) if below_tp1 else round(bar_close - _RUNNER_SPY_MOVE, 2)
        struct_word = "LOWER HIGHS"
        move_dollars = best["descent"]
        instrument = "puts"
    else:  # long
        stop_price = round(recent_extreme - _STOP_BUFFER, 2)
        default_tp1 = bar_close + _TP1_SPY_MOVE
        above = [x for x in all_levels if x > bar_close]
        if above:
            tp1_price = round(min(default_tp1, min(above)), 2)
        else:
            tp1_price = round(default_tp1, 2)
        above_tp1 = [x for x in all_levels if x > tp1_price + 0.01]
        runner_price = round(min(above_tp1), 2) if above_tp1 else round(bar_close + _RUNNER_SPY_MOVE, 2)
        struct_word = "HIGHER LOWS"
        move_dollars = best["ascent"]
        instrument = "calls"

    # Confidence: more retests + role-confirmed break = stronger.
    if n_retests >= 4 and best["from_role"]:
        confidence = "high"
    elif n_retests >= 4 or best["from_role"]:
        confidence = "medium"
    else:
        confidence = "low"

    if vix_now < 15:
        vix_bucket = "<15"
    elif vix_now < 20:
        vix_bucket = "15-20"
    elif vix_now < 25:
        vix_bucket = "20-25"
    else:
        vix_bucket = ">=25"

    seq_str = " → ".join(f"{x:.2f}" for x in run)
    break_src = "role=broken" if best["from_role"] else "intraday break detected"

    reason = (
        f"Stairstep continuation ({struct_word}) at broken ★★+ level ${level:.2f} "
        f"({break_src}): {n_retests} strict retests {seq_str} "
        f"(total {move_dollars:.2f} {'descent' if direction == 'short' else 'ascent'}). "
        f"Confirming bar closed {'red below' if direction == 'short' else 'green above'} "
        f"the level (C:{bar_close:.2f} vs O:{bar_open:.2f}). "
        f"Direction: {direction} (buy {instrument}). "
        f"Entry={bar_close:.2f} Stop={stop_price:.2f} (beyond last retest {recent_extreme:.2f}) "
        f"TP1={tp1_price:.2f} Runner={runner_price:.2f}. VIX={vix_now:.1f} ({vix_bucket}). "
        f"Motivating case: 2026-05-07 LH-LH-LH at 735.40 (736.12→735.61→735.41) → -$5.65."
    )

    return WatcherSignal(
        watcher_name="stairstep_continuation_watcher",
        setup_name="STAIRSTEP_CONTINUATION",
        direction=direction,
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=reason,
        triggers_fired=[
            "BROKEN_LEVEL_ROLE" if best["from_role"] else "BROKEN_LEVEL_INTRADAY",
            "STRICT_LOWER_HIGHS" if direction == "short" else "STRICT_HIGHER_LOWS",
            "CONFIRM_BAR_BROKEN_SIDE",
        ],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "broken_level": level,
            "break_source": break_src,
            "retest_sequence": [round(x, 2) for x in run],
            "retest_count": n_retests,
            "stairstep_move_dollars": move_dollars,
            "recent_retest_extreme": round(recent_extreme, 2),
            "vix_now": vix_now,
            "vix_bucket": vix_bucket,
            "promotion_gate": (
                "OP-21: n=1 paper observation (5/07). "
                "Live gate: N>=20 obs WR>=50% → real-fills → 3 live J wins."
            ),
            "motivating_case": "2026-05-07 735.40 LH-LH-LH (736.12→735.61→735.41) → 729.75",
        },
    )


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys

    def _mk_ctx(rows, *, vix=17.0, vol_baseline=1000.0):
        df = pd.DataFrame(rows)
        cur = df.iloc[-1]
        return BarContext(
            bar_idx=len(df) - 1,
            timestamp_et=cur["timestamp_et"],
            bar=cur,
            prior_bars=df,
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
        global _last_signal_time, _cached_all, _cached_broken_res, _cached_broken_sup, _cached_levels_date
        _last_signal_time = None
        _cached_all = []
        _cached_broken_res = []
        _cached_broken_sup = []
        _cached_levels_date = None

    def _force_levels(all_levels, broken_res, broken_sup, day):
        global _cached_all, _cached_broken_res, _cached_broken_sup, _cached_levels_date
        _cached_all = sorted(set(all_levels))
        _cached_broken_res = sorted(set(broken_res))
        _cached_broken_sup = sorted(set(broken_sup))
        _cached_levels_date = day

    def _ts(h, m):
        return dt.datetime(2026, 5, 7, h, m)

    DAY = "2026-05-07"
    LEVEL = 735.40
    results: list[tuple[str, bool]] = []

    # ── FIXTURE A — SHOULD FIRE: 5/07 descending stairstep at broken 735.40 ──
    # Level breaks down (close 734.90 < 735.40 - 0.10), then 3 retests with strict
    # lower highs 736.12 → 735.61 → 735.41, confirming bar closes red below.
    _reset()
    rows_a = []
    # break bar: closes below the level
    rows_a.append(dict(timestamp_et=_ts(11, 35), open=735.5, high=735.6, low=734.7, close=734.90, volume=1500))
    # retest #1 — high 736.12 (within 0.75 of 735.40? 736.12-735.40=0.72 ✓), closes below
    rows_a.append(dict(timestamp_et=_ts(11, 40), open=734.9, high=736.12, low=734.8, close=735.10, volume=1200))
    # drift below
    rows_a.append(dict(timestamp_et=_ts(11, 45), open=735.0, high=735.2, low=734.5, close=734.7, volume=900))
    # retest #2 — high 735.61 (lower high), closes below
    rows_a.append(dict(timestamp_et=_ts(11, 50), open=734.7, high=735.61, low=734.6, close=735.00, volume=1100))
    rows_a.append(dict(timestamp_et=_ts(11, 55), open=735.0, high=735.1, low=734.3, close=734.5, volume=850))
    # retest #3 — high 735.41 (lower high again), closes below
    rows_a.append(dict(timestamp_et=_ts(12, 0), open=734.5, high=735.41, low=734.4, close=734.80, volume=1000))
    # confirming bar — closes red below the level (continuation)
    rows_a.append(dict(timestamp_et=_ts(12, 5), open=734.8, high=734.9, low=734.0, close=734.20, volume=1300))
    ctx_a = _mk_ctx(rows_a, vix=18.0)
    _force_levels([LEVEL, 729.75, 732.0], [LEVEL], [], DAY)
    sig_a = detect_stairstep_continuation_setup(ctx_a)
    fired_a = sig_a is not None and sig_a.direction == "short"
    results.append(("A: 5/07 descending stairstep SHOULD fire (short)", fired_a))
    if sig_a is not None:
        print(f"[A] FIRED dir={sig_a.direction} conf={sig_a.confidence} "
              f"entry={sig_a.entry_price:.2f} stop={sig_a.stop_price:.2f} "
              f"tp1={sig_a.tp1_price:.2f} runner={sig_a.runner_price:.2f} "
              f"seq={sig_a.metadata['retest_sequence']}")
    else:
        print("[A] no signal")

    # ── FIXTURE B — SHOULD NOT FIRE: non-monotonic retests (no stairstep) ────
    # Highs go 735.61 → 736.12 → 735.41 (middle one HIGHER → breaks strict descent).
    _reset()
    rows_b = []
    rows_b.append(dict(timestamp_et=_ts(11, 35), open=735.5, high=735.6, low=734.7, close=734.90, volume=1500))
    rows_b.append(dict(timestamp_et=_ts(11, 40), open=734.9, high=735.61, low=734.8, close=735.10, volume=1200))
    rows_b.append(dict(timestamp_et=_ts(11, 45), open=735.0, high=735.2, low=734.5, close=734.7, volume=900))
    rows_b.append(dict(timestamp_et=_ts(11, 50), open=734.7, high=736.12, low=734.6, close=735.00, volume=1100))  # HIGHER
    rows_b.append(dict(timestamp_et=_ts(11, 55), open=735.0, high=735.1, low=734.3, close=734.5, volume=850))
    rows_b.append(dict(timestamp_et=_ts(12, 0), open=734.5, high=735.41, low=734.4, close=734.80, volume=1000))
    rows_b.append(dict(timestamp_et=_ts(12, 5), open=734.8, high=734.9, low=734.0, close=734.20, volume=1300))
    ctx_b = _mk_ctx(rows_b, vix=18.0)
    _force_levels([LEVEL, 729.75, 732.0], [LEVEL], [], DAY)
    sig_b = detect_stairstep_continuation_setup(ctx_b)
    # Note: the tail-walk finds the longest monotonic run ENDING at last retest
    # (735.41). Going back: 735.41 < 736.12 (ok), 736.12 vs 735.61 -> 735.61 < 736.12
    # so the strict-decreasing-backward run from 735.41 is [736.12, 735.41] = len 2
    # (735.61 cannot extend since 735.61 < 736.12 going further back breaks it).
    # len 2 < MIN_RETESTS=3 -> no fire.
    results.append(("B: non-monotonic retests should NOT fire", sig_b is None))
    print(f"[B] {'no signal (correct)' if sig_b is None else 'FIRED (wrong!)'}")

    # ── FIXTURE C — SHOULD NOT FIRE: confirming bar is GREEN (no continuation) ─
    _reset()
    rows_c = list(rows_a[:-1])
    rows_c.append(dict(timestamp_et=_ts(12, 5), open=734.2, high=735.0, low=734.1, close=734.90, volume=1300))  # green
    ctx_c = _mk_ctx(rows_c, vix=18.0)
    _force_levels([LEVEL, 729.75, 732.0], [LEVEL], [], DAY)
    sig_c = detect_stairstep_continuation_setup(ctx_c)
    results.append(("C: green confirming bar should NOT fire", sig_c is None))
    print(f"[C] {'no signal (correct)' if sig_c is None else 'FIRED (wrong!)'}")

    # ── FIXTURE D — SHOULD FIRE: ascending stairstep at broken-to-support ────
    # Level 740.00 breaks UP, retest lows 739.40 → 739.70 → 739.95 (higher lows),
    # confirming bar closes green above.
    _reset()
    SLEVEL = 740.00
    rows_d = []
    rows_d.append(dict(timestamp_et=_ts(10, 0), open=739.8, high=740.6, low=739.7, close=740.30, volume=1500))  # break up
    rows_d.append(dict(timestamp_et=_ts(10, 5), open=740.3, high=740.5, low=739.40, close=740.10, volume=1200))  # retest1 low 739.40
    rows_d.append(dict(timestamp_et=_ts(10, 10), open=740.1, high=740.7, low=740.0, close=740.5, volume=900))
    rows_d.append(dict(timestamp_et=_ts(10, 15), open=740.5, high=740.8, low=739.70, close=740.20, volume=1100))  # retest2 low 739.70
    rows_d.append(dict(timestamp_et=_ts(10, 20), open=740.2, high=740.9, low=740.1, close=740.6, volume=850))
    rows_d.append(dict(timestamp_et=_ts(10, 25), open=740.6, high=741.0, low=739.95, close=740.40, volume=1000))  # retest3 low 739.95
    rows_d.append(dict(timestamp_et=_ts(10, 30), open=740.4, high=741.3, low=740.35, close=741.20, volume=1300))  # confirm green above
    ctx_d = _mk_ctx(rows_d, vix=18.0)
    _force_levels([SLEVEL, 743.0, 745.0], [], [SLEVEL], DAY)
    sig_d = detect_stairstep_continuation_setup(ctx_d)
    fired_d = sig_d is not None and sig_d.direction == "long"
    results.append(("D: ascending stairstep SHOULD fire (long)", fired_d))
    if sig_d is not None:
        print(f"[D] FIRED dir={sig_d.direction} conf={sig_d.confidence} "
              f"entry={sig_d.entry_price:.2f} stop={sig_d.stop_price:.2f} "
              f"tp1={sig_d.tp1_price:.2f} runner={sig_d.runner_price:.2f} "
              f"seq={sig_d.metadata['retest_sequence']}")
    else:
        print("[D] no signal")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n=== STAIRSTEP_CONTINUATION self-test ===")
    all_pass = True
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        all_pass = all_pass and ok
    print(f"=== {'ALL PASS' if all_pass else 'SOME FAILED'} ===")
    _sys.exit(0 if all_pass else 1)
