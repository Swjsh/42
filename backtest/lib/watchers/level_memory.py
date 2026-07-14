"""LEVEL_MEMORY — a stateless, look-ahead-safe multi-day horizontal level engine.

PURPOSE (chef R&D, 2026-07-07):
  J's real edge is NOT a candle pattern. It is MULTI-DAY HORIZONTAL LEVEL MEMORY
  + ROLE-FLIPS. Worked example (verified on the tape):
    The 750.90 level — on 2026-07-06 price wicked off it (11:30/11:45 ET),
    consolidated along it (11:30-13:15), broke through (14:15) and it flipped
    resistance->support (retest-bounce ~14:40). Premarket 07-07 broke below it so
    it flipped back to resistance; 07-07's first candle touched 750.935 and
    REJECTED -> the dump.

  The live engine has NO memory-weighted multi-day levels (only today's intraday
  high/low/swing) and it deliberately SUPPRESSES role-flips (refresh_levels_intraday
  calls them "the flip-flop bug"). This module is the missing PERCEPTION layer.

DESIGN CONTRACT:
  - STATELESS: no persisted state. Given a DataFrame of 5m bars, `.up_to(i)` and
    `.snapshot(i)` derive everything from bars <= i only.
  - LOOK-AHEAD-SAFE: levels, roles, and role-flip history at bar i use ONLY bars
    with index <= i. This is the single most important invariant; a planted-future
    level MUST NOT be visible at an earlier bar. Guard: test_level_memory.py.
  - CAUSAL ROLE: a level's role (support/resistance) flips ONLY when a bar CLOSES
    decisively through it. Role at bar i reflects only closes <= i.

A LEVEL is a horizontal price the market repeatedly respected. It is built by
clustering swing highs + swing lows (from PRIOR closed bars) within a price
tolerance. Its MEMORY score aggregates:
    touches           — bars whose high/low came within tolerance of the level
    wicks             — bars that pierced the level intrabar but closed back on
                        the origin side (a rejection = respect)
    bars_consolidated — bars whose whole range sat within tolerance (base-building)
    role_flips        — # of causal role flips (resistance<->support). A level the
                        market flipped and re-respected is battle-tested memory.

We deliberately do NOT weight recency heavily: multi-day memory is the thesis.
Levels older than `lookback_days` are dropped.

This module returns SPY-PRICE structure only. It says nothing about option P&L
(that is a separate C3 question, established AFTER a price-structure edge is proven).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

import numpy as np
import pandas as pd


# ── Tunable structural constants (documented, not magic) ─────────────────────

# Swing pivot half-window: a bar is a swing high if its high is the max over
# [i-SWING_HALF, i+SWING_HALF]. Detected only on bars whose full window has
# closed (so pivot detection is itself look-ahead-safe up to the eval bar).
SWING_HALF: int = 2

# Cluster tolerance in DOLLARS: swing pivots within this band merge into one level.
# 0.35 ~= half a typical 5m SPY bar range; tight enough to separate 750.90 from
# 751.50, loose enough to absorb wick noise around a shelf.
CLUSTER_TOL: float = 0.35

# Interaction tolerance: a bar "touches" a level if its high or low comes within
# this of the level. Slightly wider than cluster tol to catch approach bars.
TOUCH_TOL: float = 0.20

# Decisive break: a bar CLOSES this far past the level (in dollars) to flip role.
# Prevents a single wick from flipping role — the close must commit.
BREAK_MARGIN: float = 0.15

# A level must have at least this many raw swing pivots feeding it to exist.
MIN_PIVOTS: int = 2

# Bars per RTH day at 5m incl. premarket rows in the master (used only for
# lookback-day windowing by calendar date, not by bar count).
DEFAULT_LOOKBACK_DAYS: int = 5


@dataclass(frozen=True)
class Level:
    """A memory-weighted horizontal level, as seen at a given eval bar."""
    price: float
    role: str  # "support" | "resistance"
    memory_score: float
    touches: int
    wicks: int
    bars_consolidated: int
    role_flips: int
    first_seen_idx: int
    last_touch_idx: int
    # Bar index of the MOST RECENT causal role flip (see _score_and_role), or -1 if the
    # level has never flipped. Feeds detect_role_flip's sustain-confirmation gate (T7,
    # 2026-07-09). Defaulted so existing keyword-only Level(...) call sites (tests, the
    # producer's _lvl() helper) keep working unchanged.
    last_flip_idx: int = -1


@dataclass(frozen=True)
class Interaction:
    """The current bar's interaction (if any) with the nearest high-memory level."""
    kind: str  # "touch" | "reject" | "break" | "retest" | "none"
    level: Optional[Level]
    distance: float  # signed: close - level.price
    detail: str = ""


@dataclass(frozen=True)
class Snapshot:
    """What LEVEL_MEMORY sees at one eval bar (all derived from bars <= idx)."""
    idx: int
    timestamp_et: pd.Timestamp
    close: float
    levels: tuple[Level, ...]
    nearest: Optional[Level]
    interaction: Interaction


# ── Swing pivot detection (look-ahead-safe up to eval bar) ───────────────────

def _swing_pivots(df: pd.DataFrame, up_to_idx: int) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Return (swing_highs, swing_lows) as (idx, price) using ONLY bars <= up_to_idx.

    A pivot at position p requires bars [p-SWING_HALF, p+SWING_HALF] to all exist
    and all be <= up_to_idx. So the newest confirmable pivot is at up_to_idx-SWING_HALF.
    This is intrinsically causal: we never peek past up_to_idx.
    """
    highs = df["high"].values
    lows = df["low"].values
    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []
    # p ranges so that p+SWING_HALF <= up_to_idx  ->  p <= up_to_idx - SWING_HALF
    last_p = up_to_idx - SWING_HALF
    for p in range(SWING_HALF, last_p + 1):
        window_hi = highs[p - SWING_HALF : p + SWING_HALF + 1]
        window_lo = lows[p - SWING_HALF : p + SWING_HALF + 1]
        if highs[p] >= window_hi.max() - 1e-9:
            swing_highs.append((p, float(highs[p])))
        if lows[p] <= window_lo.min() + 1e-9:
            swing_lows.append((p, float(lows[p])))
    return swing_highs, swing_lows


def _cluster(pivots: list[tuple[int, float]]) -> list[tuple[float, list[int]]]:
    """Cluster pivot prices within CLUSTER_TOL. Return (mean_price, member_idxs)."""
    if not pivots:
        return []
    ordered = sorted(pivots, key=lambda t: t[1])
    clusters: list[tuple[float, list[int]]] = []
    cur_prices = [ordered[0][1]]
    cur_idxs = [ordered[0][0]]
    for idx, price in ordered[1:]:
        if price - cur_prices[0] <= CLUSTER_TOL:
            cur_prices.append(price)
            cur_idxs.append(idx)
        else:
            clusters.append((float(np.mean(cur_prices)), cur_idxs))
            cur_prices = [price]
            cur_idxs = [idx]
    clusters.append((float(np.mean(cur_prices)), cur_idxs))
    return clusters


# ── Memory scoring + causal role assignment ──────────────────────────────────

def _score_and_role(
    df: pd.DataFrame,
    level_price: float,
    member_idxs: list[int],
    up_to_idx: int,
) -> Optional[Level]:
    """Compute memory metrics + causal current role for one candidate level.

    All measured over bars [first_member .. up_to_idx]. Causal by construction.
    Returns None if the level fails MIN_PIVOTS.
    """
    if len(member_idxs) < MIN_PIVOTS:
        return None

    first_idx = min(member_idxs)
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    touches = 0
    wicks = 0
    bars_consol = 0
    role_flips = 0
    last_touch_idx = first_idx
    last_flip_idx = -1  # -1 = never flipped (see Level.last_flip_idx)

    # Initialize role from the FIRST decisive close relative to the level.
    # Until a decisive close occurs, infer role from where price mostly sits.
    role: Optional[str] = None
    # seed role from the first member bar's close side
    seed_close = closes[first_idx]
    role = "resistance" if seed_close <= level_price else "support"

    for i in range(first_idx, up_to_idx + 1):
        hi, lo, cl = highs[i], lows[i], closes[i]

        # Touch: high or low within TOUCH_TOL of the level
        if (abs(hi - level_price) <= TOUCH_TOL) or (abs(lo - level_price) <= TOUCH_TOL) \
           or (lo <= level_price <= hi):
            touches += 1
            last_touch_idx = i

        # Wick / rejection: pierced intrabar but closed back on the origin side
        if role == "resistance":
            if hi > level_price + 1e-9 and cl < level_price - 1e-9:
                wicks += 1
        else:  # support
            if lo < level_price - 1e-9 and cl > level_price + 1e-9:
                wicks += 1

        # Consolidation: whole bar range within tolerance band of the level
        if (hi - level_price) <= TOUCH_TOL and (level_price - lo) <= TOUCH_TOL:
            bars_consol += 1

        # Causal role flip: a bar CLOSES decisively through the level
        if role == "resistance" and cl >= level_price + BREAK_MARGIN:
            role = "support"
            role_flips += 1
            last_flip_idx = i
        elif role == "support" and cl <= level_price - BREAK_MARGIN:
            role = "resistance"
            role_flips += 1
            last_flip_idx = i

    memory_score = float(touches + wicks + bars_consol + 2.0 * role_flips)

    return Level(
        price=round(level_price, 2),
        role=role or "resistance",
        memory_score=memory_score,
        touches=touches,
        wicks=wicks,
        bars_consolidated=bars_consol,
        role_flips=role_flips,
        first_seen_idx=first_idx,
        last_touch_idx=last_touch_idx,
        last_flip_idx=last_flip_idx,
    )


# ── Public engine ────────────────────────────────────────────────────────────

class LevelMemory:
    """Stateless multi-day level engine over a 5m OHLCV frame.

    Usage:
        lm = LevelMemory(df)                    # df: timestamp_et,open,high,low,close,volume
        snap = lm.snapshot(i)                   # everything at bar i, causal
        levels = lm.levels_at(i, lookback_days) # just the levels
    """

    def __init__(self, df: pd.DataFrame):
        d = df.copy().reset_index(drop=True)
        if "timestamp_et" in d.columns:
            d["timestamp_et"] = pd.to_datetime(d["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
        for col in ("open", "high", "low", "close"):
            d[col] = pd.to_numeric(d[col], errors="coerce")
        self.df = d
        self._dates = d["timestamp_et"].dt.date.values

    def _lookback_start_idx(self, up_to_idx: int, lookback_days: int) -> int:
        """First bar index within `lookback_days` calendar trading days of bar up_to_idx."""
        dates_series = self.df["timestamp_et"].dt.date
        cur_date = dates_series.iloc[up_to_idx]
        unique_days = [d for d in sorted(set(dates_series.iloc[: up_to_idx + 1]))]
        keep_days = set(unique_days[-lookback_days:]) if lookback_days > 0 else set(unique_days)
        # first index whose date is in keep_days
        mask = dates_series.iloc[: up_to_idx + 1].isin(keep_days)
        first = mask[mask].index.min()
        return int(first)

    def levels_at(self, up_to_idx: int, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list[Level]:
        """Return memory-weighted levels visible at bar up_to_idx (causal).

        Only bars in [lookback_start, up_to_idx] feed pivot detection AND scoring.
        """
        start = self._lookback_start_idx(up_to_idx, lookback_days)
        window = self.df.iloc[start : up_to_idx + 1].reset_index(drop=True)
        # up_to within the window frame:
        win_up_to = len(window) - 1

        swing_highs, swing_lows = _swing_pivots(window, win_up_to)
        all_pivots = swing_highs + swing_lows
        clusters = _cluster(all_pivots)

        levels: list[Level] = []
        for lvl_price, member_idxs in clusters:
            lvl = _score_and_role(window, lvl_price, member_idxs, win_up_to)
            if lvl is None:
                continue
            # translate window-relative indices back to absolute (last_flip_idx stays -1
            # -- "never flipped" -- if it was never set; only shift a real index)
            lvl = replace(
                lvl,
                first_seen_idx=lvl.first_seen_idx + start,
                last_touch_idx=lvl.last_touch_idx + start,
                last_flip_idx=(lvl.last_flip_idx + start if lvl.last_flip_idx >= 0 else -1),
            )
            levels.append(lvl)

        levels.sort(key=lambda L: L.memory_score, reverse=True)
        return levels

    @staticmethod
    def _interaction_for_level(row, lvl: "Level") -> Interaction:
        """Classify how the CURRENT bar interacted with ONE specific level."""
        hi, lo, cl = row["high"], row["low"], row["close"]
        lp = lvl.price
        dist = float(cl - lp)
        interacted = (lo - TOUCH_TOL) <= lp <= (hi + TOUCH_TOL)
        if not interacted:
            return Interaction(kind="none", level=lvl, distance=dist, detail="no contact")

        if lvl.role == "resistance":
            if hi > lp + 1e-9 and cl < lp - 1e-9:
                kind, detail = "reject", f"wicked {(hi-lp)*100:.0f}c above R, closed {(lp-cl)*100:.0f}c below"
            elif cl >= lp + BREAK_MARGIN:
                kind, detail = "break", f"closed {(cl-lp)*100:.0f}c above R (break)"
            else:
                kind, detail = "touch", f"touched R, close {(cl-lp)*100:.1f}c from it"
        else:  # support
            if lo < lp - 1e-9 and cl > lp + 1e-9:
                kind, detail = "reject", f"wicked {(lp-lo)*100:.0f}c below S, closed {(cl-lp)*100:.0f}c above"
            elif cl <= lp - BREAK_MARGIN:
                kind, detail = "break", f"closed {(lp-cl)*100:.0f}c below S (break)"
            else:
                kind, detail = "touch", f"touched S, close {(cl-lp)*100:.1f}c from it"

        # retest = level flipped role at least once AND price is testing it from
        # the new side (touch, not decisive break). Highest-conviction memory event.
        if kind == "touch" and lvl.role_flips >= 1:
            kind = "retest"
            detail = f"retest of role-flipped level ({lvl.role_flips} flips): " + detail

        return Interaction(kind=kind, level=lvl, distance=dist, detail=detail)

    def _classify_interaction(
        self, up_to_idx: int, levels: list[Level]
    ) -> tuple[Optional[Level], Interaction]:
        """Pick the most SALIENT interaction of the current bar with a high-memory level.

        Saliency rule (in priority order): among every level the bar physically
        touched intrabar, prefer an active event (reject > break > retest > touch)
        on the HIGHEST-MEMORY level. This is why a bar that wicks a resistance
        level and closes far below it is flagged as a REJECT of that level, not
        a mere close-proximity touch of some nearer level. Falls back to the
        close-nearest level when the bar touched nothing.
        """
        if not levels:
            return None, Interaction(kind="none", level=None, distance=0.0)

        row = self.df.iloc[up_to_idx]
        cl = row["close"]

        _EVENT_RANK = {"reject": 3, "break": 2, "retest": 2, "touch": 1, "none": 0}
        best_level: Optional[Level] = None
        best_inter: Optional[Interaction] = None
        best_key = None
        for lvl in levels:
            inter = self._interaction_for_level(row, lvl)
            if inter.kind == "none":
                continue
            key = (_EVENT_RANK[inter.kind], lvl.memory_score)
            if best_key is None or key > best_key:
                best_key = key
                best_level = lvl
                best_inter = inter

        if best_inter is not None:
            return best_level, best_inter

        # nothing touched: report nearest-by-close for context, kind=none
        nearest = min(levels, key=lambda L: (abs(cl - L.price), -L.memory_score))
        return nearest, Interaction(
            kind="none", level=nearest, distance=float(cl - nearest.price), detail="no contact"
        )

    def snapshot(self, up_to_idx: int, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> Snapshot:
        """Full causal snapshot at bar up_to_idx."""
        levels = self.levels_at(up_to_idx, lookback_days)
        nearest, interaction = self._classify_interaction(up_to_idx, levels)
        row = self.df.iloc[up_to_idx]
        return Snapshot(
            idx=up_to_idx,
            timestamp_et=row["timestamp_et"],
            close=float(row["close"]),
            levels=tuple(levels),
            nearest=nearest,
            interaction=interaction,
        )


# ── Sustained role-flip confirmation (T7, 2026-07-09, SHADOW-ONLY) ───────────
# J's real edge (verified 2026-07-07 -> 2026-07-08): the 745.40 shelf was support on 07-07,
# broke overnight, and was THEREFORE resistance on 07-08 -- confirmed live by the 13:30 ET
# tag-746.09 / close-744.39 rejection. `_score_and_role` above already flips `role` causally
# on the FIRST decisive close (BREAK_MARGIN) -- correct for SCORING memory (a level that keeps
# getting re-tested is more battle-tested, hence `role_flips`), but too eager to REPORT as a
# confirmed regime change: a single 15c close through a level that reverts next bar is noise,
# not "745.40 is resistance now." That single-bar eagerness is exactly what produces the
# whipsaw `role_flips` counts already seen in production (10-25 flips per level over 10 days).
#
# detect_role_flip() adds a SECOND, stricter, opt-in confirmation gate for EXTERNAL reporting
# (key-levels-memory.json's flipped_at/provenance) -- it never touches `Level.role` itself,
# which stays the fast/causal signal role_flips already scores against. It works off
# `last_flip_idx` (the bar index of the level's most-recent causal flip, threaded through
# _score_and_role above): if no bar since last_flip_idx caused ANOTHER flip (by construction,
# since role_flips would have advanced last_flip_idx again), the role has HELD since then --
# "sustained" == up_to_idx - last_flip_idx + 1 >= sustain_bars.
#
#   ROLE_FLIP_SUSTAIN_BARS = 3   -- 3 consecutive 5m bars (15 min) with the role unchanged
#     since the flip. Long enough to reject a single wick-and-revert (the exact failure mode
#     BREAK_MARGIN alone allows through) but short enough to confirm INTRADAY, not EOD: the
#     real 745.40 flip held from the 07-08 premarket break all the way through the 13:30
#     rejection it explains -- thousands of times longer than 3 bars, but 3 is the minimum
#     that would have called it BEFORE the 09:30 open.
#   ROLE_FLIP_MEMORY_THRESHOLD = 50.0 -- only confirmed-flip-tag well-tested levels, between
#     the producer's MIN_MEMORY=20 selection floor and its STRONG_MEMORY=60 "Active" tier cut.
#     Untested levels flip too often (low memory_score correlates with few touches/wicks, i.e.
#     an unproven price) to be worth alerting J on. 50 is also literally the number in J's own
#     worked 07-08 read: the 745-area level cluster scores in the 120-160 range, comfortably
#     above 50, while noise-tier levels sit under 20 and never reach this gate at all.
ROLE_FLIP_SUSTAIN_BARS: int = 3
ROLE_FLIP_MEMORY_THRESHOLD: float = 50.0


def detect_role_flip(
    level: "Level",
    df: pd.DataFrame,
    up_to_idx: int,
    *,
    sustain_bars: int = ROLE_FLIP_SUSTAIN_BARS,
    memory_threshold: float = ROLE_FLIP_MEMORY_THRESHOLD,
) -> tuple[str, "str | None", "str | None"]:
    """PURE, no I/O. Returns (role, flipped_at_iso_et, provenance) for `level` as of up_to_idx.

    `df` must be the SAME frame `level`'s indices were computed against (i.e. `LevelMemory.df`,
    already tz-converted to America/New_York -- pass ET timestamps in, get an ET ISO string out;
    never hand-roll a UTC offset here).

    Semantics:
      - memory_score < memory_threshold, or the level has never flipped (role_flips == 0 /
        last_flip_idx < 0): the confirmation gate does not apply. Returns (level.role, None, None)
        unchanged -- there is nothing to confirm or deny.
      - The most recent flip has NOT held for `sustain_bars` bars yet (up_to_idx too close to
        last_flip_idx): NOT confirmed. Returns the level's PRIOR role (support<->resistance is
        binary, so "not this" == "the other one") with no flipped_at/provenance -- i.e. treat a
        too-fresh flip as still-the-old-regime rather than propagate single-bar noise outward.
      - The flip HAS held >= sustain_bars: CONFIRMED. Returns (level.role, <ISO ET timestamp of
        the flip bar>, <provenance string>).

    Look-ahead-safe: only ever reads df rows at indices <= up_to_idx.
    """
    if level.memory_score < memory_threshold or level.role_flips <= 0 or level.last_flip_idx < 0:
        return level.role, None, None

    bars_since_flip = up_to_idx - level.last_flip_idx + 1
    if bars_since_flip < sustain_bars:
        prior_role = "support" if level.role == "resistance" else "resistance"
        return prior_role, None, None

    ts = df["timestamp_et"].iloc[level.last_flip_idx]
    flipped_at = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    # role == "resistance" means the flip that put it there was a decisive close BELOW the
    # level (support broke down -> resistance); role == "support" means a decisive close ABOVE
    # (resistance broke up -> support). See the _score_and_role flip branches above.
    side = "below" if level.role == "resistance" else "above"
    provenance = (
        f"closed {side} {level.price:.2f} for {bars_since_flip} consecutive 5m bars "
        f"starting {flipped_at}, memory_score={level.memory_score:.0f} >= "
        f"threshold {memory_threshold:.0f}"
    )
    return level.role, flipped_at, provenance


# ── G5 alert leg (2026-07-08): notify J on a high-memory-level REJECTION ──────────────────
# Notify-only, NO trading path. Fires when this bar REJECTS off a battle-tested level (the
# thing the live engine was blind to -- 07-07's 750.90 multi-day rejection). Writes the
# DELIVERED discord-outbox `content` schema (drain_outbox reads `content`). Fail-open.
ALERT_MIN_MEMORY = 3.0  # only ping battle-tested levels; raise as the corpus grows


def format_reject_alert(snap: "Snapshot", *, min_memory: float = ALERT_MIN_MEMORY):
    """Discord alert string for a high-memory-level rejection, or None if this bar's
    interaction is not a reject off a level whose memory_score >= min_memory. Pure + testable."""
    it = snap.interaction
    if it.kind != "reject" or it.level is None or it.level.memory_score < min_memory:
        return None
    lv = it.level
    return (f"LEVEL-MEMORY REJECT @ {lv.price:.2f} ({lv.role}) -- SPY {snap.close:.2f} rejected a "
            f"battle-tested level: memory {lv.memory_score:.1f}, {lv.touches} touches, "
            f"{lv.role_flips} role-flips, {snap.timestamp_et}. {it.detail}").strip()


def emit_reject_alert(snap: "Snapshot", outbox_path, *, min_memory: float = ALERT_MIN_MEMORY,
                      source: str = "level_memory") -> bool:
    """Append a discord-outbox ping on a high-memory reject. Notify-only; returns True if a row
    was written. Fail-open -- never raises into the caller's tick."""
    try:
        msg = format_reject_alert(snap, min_memory=min_memory)
        if not msg:
            return False
        import datetime as _dt
        import json as _json
        row = {"content": msg, "source": source,
               "queued_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
        with open(outbox_path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(row) + "\n")
        return True
    except Exception:
        return False
