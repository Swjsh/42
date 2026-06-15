"""OPENING_DRIVE_FADE setup detector.

The J-edge thesis: SPY's 09:35-10:30 ET opening drive carries overnight
gamma imbalance + opening-auction flow. When that drive establishes an
HOD (or LOD) then 2+ subsequent 5m bars trade within $0.20 of the
extreme on declining volume vs the thrust bar, the marginal buyer (or
seller) is spent. Fade in the OPPOSITE direction with ITM-2 0DTE.

Per CLAUDE.md OP 21 (Watch-First Promotion Path) the setup starts
WATCH-ONLY. Promotion to live orders requires 3+ historical wins via
watcher_grader.py + 3+ live wins observed by J + positive expectancy
over the 16-month backfill + J ratification.

Mirrors sniper_detector.py for typing + dataclass shape. Uses orb_watcher
per-day module-level dict state pattern for the BREAKOUT -> STALL ->
ENTRY state machine because the trigger inherently spans bars.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd


# ---------- Params ----------

@dataclass(frozen=True)
class OpeningDriveFadeParams:
    """Knobs for the OPENING_DRIVE_FADE detector. Immutable; one per combo.

    Spec section 6 knob grid (810 combos):
      thrust_bar_min_dollars: 0.30 / 0.40 / 0.50
      stall_bars_required:    2 / 3
      stall_proximity_dollars: 0.15 / 0.20 / 0.25
      vol_decline_ratio:       0.50 / 0.60 / 0.70 / 0.80 / 0.85
      time_window_end:         10:15 / 10:30 / 10:45

    Locked (spec section 6):
      time_window_start = 09:35
      entry_window_end  = 11:00
    """

    thrust_bar_min_dollars: float = 0.40
    stall_bars_required: int = 2
    stall_proximity_dollars: float = 0.20
    vol_decline_ratio: float = 0.70  # stall bar volume MUST be <= ratio * thrust volume

    time_window_start: dt.time = dt.time(9, 35)
    time_window_end: dt.time = dt.time(10, 30)
    entry_window_end: dt.time = dt.time(11, 0)


# ---------- Signal ----------

@dataclass(frozen=True)
class OpeningDriveFadeSignal:
    """Output of detect_opening_drive_fade() when the trigger fires."""

    direction: str            # "short" (HOD fade -> puts) or "long" (LOD fade -> calls)
    entry_price: float        # entry bar close (spot)
    timestamp: dt.datetime    # entry bar timestamp ET
    extreme_price: float      # HOD or LOD that was faded
    thrust_bar_time: dt.datetime
    stall_bar_count: int      # how many stall bars were printed before entry
    vol_ratio_thrust: float   # entry bar volume / thrust bar volume
    quality_tier: str         # "BASE" or "ELITE"
    reason: str


# ---------- Per-day state machine ----------

# Module-level state dict mirroring orb_watcher.py's _orb_state pattern.
# Key = ISO date string. Values track the HOD/LOD ratchet, the current
# thrust bar, the stall bar count, and whether we've already fired.
_odf_state: dict[str, dict] = {}


def _empty_state() -> dict:
    return {
        # HOD side
        "hod": None,                  # current session high
        "hod_thrust_bar_idx": None,   # bar index of thrust bar (within day)
        "hod_thrust_bar_ts": None,
        "hod_thrust_volume": None,
        "hod_stall_bars_seen": 0,
        "hod_fired": False,
        # LOD side
        "lod": None,
        "lod_thrust_bar_idx": None,
        "lod_thrust_bar_ts": None,
        "lod_thrust_volume": None,
        "lod_stall_bars_seen": 0,
        "lod_fired": False,
        # One-and-done per day per OP 21 + spec section 2 trigger #6
        "any_fired": False,
    }


def _get_state(date_str: str) -> dict:
    if date_str not in _odf_state:
        _odf_state[date_str] = _empty_state()
    return _odf_state[date_str]


def reset_state(date_str: str) -> None:
    """Reset per-day detector state. Call between days when batch-backtesting."""
    if date_str in _odf_state:
        del _odf_state[date_str]


def reset_all_state() -> None:
    """Reset every day's state. Useful for cross-evaluation tests."""
    _odf_state.clear()


# ---------- Helpers ----------

def _date_key(bar_time: dt.datetime) -> str:
    return bar_time.date().isoformat()


def _is_in_thrust_window(t: dt.time, params: OpeningDriveFadeParams) -> bool:
    return params.time_window_start <= t <= params.time_window_end


def _is_in_entry_window(t: dt.time, params: OpeningDriveFadeParams) -> bool:
    # Entry bar may extend past thrust window up to entry_window_end
    return params.time_window_start <= t <= params.entry_window_end


def _classify_quality(
    direction: str,
    extreme_price: float,
    vol_ratio: float,
    stall_bars_seen: int,
    params: OpeningDriveFadeParams,
) -> str:
    """Per spec section 4 quality_tier rules.

    ELITE requires ALL of:
      - vol_decline_ratio <= 0.50 (strong absorption)
      - stall_bars_seen >= 3 (extended distribution)
      - level confluence within $0.30 (NOT checked here; deferred to evaluator
        which has access to today-bias.json levels). For pure-detector path
        we tag ELITE based on the two intrinsic conditions and let the
        evaluator demote/promote based on level confluence if it has the data.
    """
    if vol_ratio <= 0.50 and stall_bars_seen >= 3:
        return "ELITE"
    return "BASE"


# ---------- Detector ----------

def detect_opening_drive_fade(
    bar: pd.Series,
    bar_idx: int,
    spy_bars: pd.DataFrame,
    params: OpeningDriveFadeParams,
) -> Optional[OpeningDriveFadeSignal]:
    """Detect an OPENING_DRIVE_FADE trigger on the current bar.

    Per-bar state machine (one call per RTH bar, day-bars only or full-
    series — function reads `bar` directly and uses `bar_idx` for context):

      1. Update HOD/LOD ratchet for the session.
      2. If bar is in [time_window_start, time_window_end] and forms a
         new extreme with body >= thrust_bar_min_dollars, record it as
         the thrust bar (replaces any prior thrust on that side).
      3. After a thrust bar exists, count stall bars: subsequent bars
         within stall_proximity_dollars of the extreme on declining
         volume (bar_vol <= vol_thrust * vol_decline_ratio).
      4. Once stall_bars_seen >= stall_bars_required AND we have a NEW
         bar (the "entry bar") whose close is within stall_proximity_dollars
         of the extreme but on the FADE side (close < HOD for HOD-fade /
         close > LOD for LOD-fade), AND bar time <= entry_window_end:
         emit signal.
      5. One-and-done per day per spec section 2 trigger #6.

    HOD path -> direction = "short" (puts).
    LOD path -> direction = "long" (calls).

    Returns None if no trigger; OpeningDriveFadeSignal if a fade fires.
    """
    bar_time = bar["timestamp_et"]
    if not hasattr(bar_time, "time"):
        return None
    bar_t = bar_time.time()
    bar_open = float(bar["open"])
    bar_close = float(bar["close"])
    bar_high = float(bar["high"])
    bar_low = float(bar["low"])
    bar_volume = float(bar["volume"])
    body = abs(bar_close - bar_open)

    date_key = _date_key(bar_time)
    state = _get_state(date_key)

    # If we've already fired today, lock out further fires (one direction per day).
    if state["any_fired"]:
        return None

    # ---- Update HOD/LOD ratchet (always, regardless of window) ----
    # IMPORTANT (2026-05-13 bug fix): a new HOD made by a bar WITHOUT
    # thrust-quality body must NOT wipe a previously-recorded thrust bar.
    # On real SPY data the HOD ratchets via many small-bodied bars after the
    # initial drive — those would otherwise erase the legitimate thrust and
    # the stall counter never gets to fire. We only update the thrust slot
    # when this bar itself qualifies as a thrust; otherwise we leave the
    # prior thrust intact and rely on stall accumulation to fire.
    if state["hod"] is None or bar_high > state["hod"]:
        state["hod"] = bar_high
        if _is_in_thrust_window(bar_t, params) and body >= params.thrust_bar_min_dollars:
            state["hod_thrust_bar_idx"] = bar_idx
            state["hod_thrust_bar_ts"] = bar_time
            state["hod_thrust_volume"] = bar_volume
            state["hod_stall_bars_seen"] = 0  # reset stall counter on fresh thrust

    if state["lod"] is None or bar_low < state["lod"]:
        state["lod"] = bar_low
        if _is_in_thrust_window(bar_t, params) and body >= params.thrust_bar_min_dollars:
            state["lod_thrust_bar_idx"] = bar_idx
            state["lod_thrust_bar_ts"] = bar_time
            state["lod_thrust_volume"] = bar_volume
            state["lod_stall_bars_seen"] = 0

    # Don't fire outside entry window
    if not _is_in_entry_window(bar_t, params):
        return None

    # ---- HOD-fade path: PUTS ----
    if (
        not state["hod_fired"]
        and state["hod_thrust_bar_idx"] is not None
        and state["hod_thrust_bar_idx"] < bar_idx
        and state["hod_thrust_volume"]
        and state["hod_thrust_volume"] > 0
    ):
        hod = state["hod"]
        vol_threshold = state["hod_thrust_volume"] * params.vol_decline_ratio

        # Is THIS bar a stall bar? Condition: bar.high within proximity AND
        # bar.volume < threshold. Stall counting is cumulative across bars
        # following the thrust bar.
        is_stall = (
            (hod - bar_high) <= params.stall_proximity_dollars
            and bar_high <= hod + 0.001  # didn't wick beyond HOD (extreme-stickiness)
            and bar_volume <= vol_threshold
        )
        if is_stall:
            state["hod_stall_bars_seen"] += 1

        # Entry condition: enough stall bars accumulated AND THIS bar closes
        # back inside the proximity envelope on the FADE side (close < HOD
        # but within stall_proximity_dollars).
        if (
            state["hod_stall_bars_seen"] >= params.stall_bars_required
            and (hod - bar_close) >= 0.0
            and (hod - bar_close) <= params.stall_proximity_dollars
        ):
            vol_ratio = bar_volume / state["hod_thrust_volume"] if state["hod_thrust_volume"] > 0 else 0.0
            quality = _classify_quality(
                "short", hod, vol_ratio, state["hod_stall_bars_seen"], params
            )
            state["hod_fired"] = True
            state["any_fired"] = True
            return OpeningDriveFadeSignal(
                direction="short",
                entry_price=bar_close,
                timestamp=bar_time,
                extreme_price=hod,
                thrust_bar_time=state["hod_thrust_bar_ts"],
                stall_bar_count=state["hod_stall_bars_seen"],
                vol_ratio_thrust=vol_ratio,
                quality_tier=quality,
                reason=(
                    f"HOD={hod:.2f} faded after {state['hod_stall_bars_seen']} stall bars "
                    f"vol={vol_ratio:.2f}x entry_close={bar_close:.2f} "
                    f"thrust@{state['hod_thrust_bar_ts'].strftime('%H:%M') if state['hod_thrust_bar_ts'] else '?'}"
                ),
            )

    # ---- LOD-fade path: CALLS ----
    if (
        not state["lod_fired"]
        and state["lod_thrust_bar_idx"] is not None
        and state["lod_thrust_bar_idx"] < bar_idx
        and state["lod_thrust_volume"]
        and state["lod_thrust_volume"] > 0
    ):
        lod = state["lod"]
        vol_threshold = state["lod_thrust_volume"] * params.vol_decline_ratio

        is_stall = (
            (bar_low - lod) <= params.stall_proximity_dollars
            and bar_low >= lod - 0.001
            and bar_volume <= vol_threshold
        )
        if is_stall:
            state["lod_stall_bars_seen"] += 1

        if (
            state["lod_stall_bars_seen"] >= params.stall_bars_required
            and (bar_close - lod) >= 0.0
            and (bar_close - lod) <= params.stall_proximity_dollars
        ):
            vol_ratio = bar_volume / state["lod_thrust_volume"] if state["lod_thrust_volume"] > 0 else 0.0
            quality = _classify_quality(
                "long", lod, vol_ratio, state["lod_stall_bars_seen"], params
            )
            state["lod_fired"] = True
            state["any_fired"] = True
            return OpeningDriveFadeSignal(
                direction="long",
                entry_price=bar_close,
                timestamp=bar_time,
                extreme_price=lod,
                thrust_bar_time=state["lod_thrust_bar_ts"],
                stall_bar_count=state["lod_stall_bars_seen"],
                vol_ratio_thrust=vol_ratio,
                quality_tier=quality,
                reason=(
                    f"LOD={lod:.2f} faded after {state['lod_stall_bars_seen']} stall bars "
                    f"vol={vol_ratio:.2f}x entry_close={bar_close:.2f} "
                    f"thrust@{state['lod_thrust_bar_ts'].strftime('%H:%M') if state['lod_thrust_bar_ts'] else '?'}"
                ),
            )

    return None
