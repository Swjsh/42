"""tw8_level_context.py -- level-context enrichment for the T-W8 HEADROOM+RETEST study.

The ribbon_ride signal schema (_signal_cache.py: date/entry_ts/side/entry_spot/setup/
direction) carries NO level context -- it is a strike-independent entry-event record.
This module recomputes it from SPY bars, reusing lib/levels.py's `_detect_from_history`
-- the SAME level detector lib/orchestrator.py uses to fire the BEARISH_REJECTION /
BULLISH_RECLAIM triggers in the first place (orchestrator.py imports `_detect_from_history`
directly; lib/filters.py's `detect_level_reclaim`/`detect_level_rejection` consume its
`.active` list).

INVOCATION CONVENTION (matches the backtest, not a re-derivation):
lib/orchestrator.py FREEZES the level set ONCE per date, at that date's first evaluated
bar (time >= 09:35 ET), from bars <= that bar only (orchestrator.py `_level_per_day`
cache, ~line 918-923) -- and reuses it for every bar of that session. This is NOT a bug
we're working around; it is the level set that was ACTUALLY ACTIVE when
detect_level_reclaim/detect_level_rejection fired the signals in this study's signal
sets. Two other places in this codebase independently confirm this is the established
convention for research code built on lib/levels.py:
  * backtest/replay_heartbeat_core.py ports it explicitly (see its "LEVEL-SET PORT"
    comment) specifically because a per-bar re-derivation changes trigger firing.
  * backtest/autoresearch/level_break_first_strike_scan.py computes levels once per day
    at the first RTH bar, independently, for the same reason.
This module reproduces that exact freeze. C6 (look-ahead): frozen_bar_time <= entry_ts
for every signal on the same date by construction (the loop only admits entries at
bar_time >= 09:35, so the freeze bar is always <= any admitted entry same-day).

ENTRY_TS vs ENTRY_SPOT TIMING (load-bearing for trigger-bar recovery):
simulator_real.py's real-fills path (no-look-ahead convention) sets:
  * entry_spot = the TRIGGER bar's CLOSE (`entry_bar["close"]`, orchestrator's bar_idx=idx)
  * entry_time_et (final, in the signal set) = the FILL/confirmation bar's timestamp,
    which is ONE 5-min bar (or more, if the option had no print at exactly +5min) AFTER
    the trigger bar (`fill.entry_time_et = entry_bar_opt.timestamp_et`, overwriting the
    initial `entry_time` assignment -- see simulator_real.py lines ~356-493).
So `entry_ts` in the signal JSON is NOT the trigger bar's timestamp. To recover the
trigger bar (needed for detect_level_reclaim/detect_level_rejection, which consume the
bar that actually crossed the level), we search backward from entry_ts on the same date
for the bar whose CLOSE matches entry_spot (both values originate from the exact same
source CSV, so an exact-cent match is expected and verified below with a tight
tolerance; v_pullback_enabled is OFF in this study's signal-generation params (L2_PATCH
never sets it), so entry_bar_idx == the original trigger idx, not a later pullback bar).

$0, local CSVs only (same SPY 5-min data T3/T4/T5 already load via autoresearch.runner).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(REPO / "backtest"))

from lib.levels import _detect_from_history, LevelSet          # noqa: E402
from lib.filters import detect_level_reclaim, detect_level_rejection  # noqa: E402

TRIGGER_BAR_MATCH_TOLERANCE = 0.005   # dollars; entry_spot is float(bar.close) from the SAME csv


def load_spy_full(start: dt.date, end: dt.date) -> pd.DataFrame:
    """Load SPY 5-min bars (incl. premarket where present) for [start, end], normalized
    to tz-naive ET timestamps -- same parsing convention orchestrator.py applies
    (`pd.to_datetime(...)` then stripped of tz), so bar identity matches what generated
    the signal sets. Adds `date`/`time` helper columns."""
    from autoresearch.runner import load_data
    spy, _vix = load_data(start, end)
    spy = spy.copy()
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    if spy["timestamp_et"].dt.tz is not None:
        spy["timestamp_et"] = spy["timestamp_et"].dt.tz_localize(None)
    spy = spy.sort_values("timestamp_et").reset_index(drop=True)
    spy["date"] = spy["timestamp_et"].dt.date
    spy["time"] = spy["timestamp_et"].dt.time
    return spy


def frozen_level_set_for_date(
    spy_full: pd.DataFrame, date: dt.date, cache: dict
) -> Optional[LevelSet]:
    """The orchestrator's per-day-frozen level set: computed ONCE at the date's first
    bar with time >= 09:35 ET, from bars <= that bar only. Memoized in `cache` (caller-
    owned dict) so multiple signals on the same date share one computation."""
    if date in cache:
        return cache[date]
    day_bars = spy_full[spy_full["date"] == date]
    eligible = day_bars[day_bars["time"] >= dt.time(9, 35)]
    if eligible.empty:
        cache[date] = None
        return None
    first_bar_time = eligible["timestamp_et"].iloc[0]
    full_history = spy_full[spy_full["timestamp_et"] <= first_bar_time]
    level_set = _detect_from_history(full_history, date)
    cache[date] = level_set
    return level_set


def find_trigger_bar(
    spy_full: pd.DataFrame, date: dt.date, entry_ts: dt.datetime, entry_spot: float,
    tolerance: float = TRIGGER_BAR_MATCH_TOLERANCE,
) -> tuple[Optional[pd.Series], Optional[float]]:
    """Recover the trigger bar: the closest-close bar on `date` at or before `entry_ts`.
    Returns (bar_row_or_None, abs_close_diff_or_None)."""
    day_bars = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] <= entry_ts)]
    if day_bars.empty:
        return None, None
    diffs = (day_bars["close"] - entry_spot).abs()
    idx = diffs.idxmin()
    best_diff = float(diffs.loc[idx])
    if best_diff > tolerance:
        return None, best_diff
    return day_bars.loc[idx], best_diff


def next_opposing_level(
    entry_spot: float, active_levels: list[float], side: str
) -> Optional[float]:
    """Nearest ACTIVE level on the OPPOSING side of entry_spot: resistance above for
    calls (side='C'), support below for puts (side='P'). None = no such level in the
    active set (unbounded headroom, per the pre-registration's H-gate definition)."""
    if side == "C":
        above = [lv for lv in active_levels if lv > entry_spot + 1e-9]
        return min(above) if above else None
    below = [lv for lv in active_levels if lv < entry_spot - 1e-9]
    return max(below) if below else None


def enrich_signal(sig: dict, spy_full: pd.DataFrame, level_cache: dict) -> dict:
    """Returns a COPY of `sig` with trigger_level / next_opposing_level / headroom_dollars
    / level_context_status added. Never mutates the input."""
    out = dict(sig)
    date = dt.date.fromisoformat(sig["date"])
    entry_ts = dt.datetime.fromisoformat(sig["entry_ts"])
    entry_spot = float(sig["entry_spot"])
    side = sig["side"]

    level_set = frozen_level_set_for_date(spy_full, date, level_cache)
    if level_set is None:
        out.update(trigger_level=None, next_opposing_level=None, headroom_dollars=None,
                    trigger_bar_match_diff=None, level_context_status="no_level_set")
        return out

    nxt = next_opposing_level(entry_spot, level_set.active, side)
    headroom = round(abs(nxt - entry_spot), 4) if nxt is not None else None

    trig_bar, diff = find_trigger_bar(spy_full, date, entry_ts, entry_spot)
    if trig_bar is None:
        status = "trigger_bar_no_bars" if diff is None else f"trigger_bar_unmatched(diff={diff:.4f})"
        out.update(trigger_level=None, next_opposing_level=nxt, headroom_dollars=headroom,
                    trigger_bar_match_diff=diff, level_context_status=status)
        return out

    if side == "C":
        trig_level = detect_level_reclaim(trig_bar, level_set.active)
    else:
        trig_level = detect_level_rejection(trig_bar, level_set.active)

    out.update(
        trigger_level=trig_level,
        next_opposing_level=nxt,
        headroom_dollars=headroom,
        trigger_bar_match_diff=round(diff, 6) if diff is not None else None,
        level_context_status="ok" if trig_level is not None else "ok_no_level_trigger",
    )
    return out


def enrich_signals(
    signals: list[dict], start: dt.date, end: dt.date
) -> tuple[list[dict], pd.DataFrame]:
    """Top-level convenience: loads SPY once, enriches every signal. Returns
    (enriched_signals, spy_full) -- callers that also need candidate-R's retest scan
    reuse the returned spy_full instead of reloading."""
    spy_full = load_spy_full(start, end)
    level_cache: dict = {}
    enriched = [enrich_signal(s, spy_full, level_cache) for s in signals]
    return enriched, spy_full


def spy_bars_by_time_for_day(spy_full: pd.DataFrame, date: dt.date) -> dict:
    """{datetime.time -> bar row} for one date -- used by candidate R's retest scan to
    align OPTION bars (indexed by time-of-day, per t4._load_bars) back to SPY price."""
    day_bars = spy_full[spy_full["date"] == date]
    return {row.time: row for row in day_bars.itertuples()}


if __name__ == "__main__":
    # Self-check: enrich both signal sets, print coverage stats. $0, no writes.
    import json
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _signal_cache as sc

    data = sc.load_or_build_signals()
    sigs = data["signals"] if isinstance(data, dict) else data
    enriched, _spy = enrich_signals(sigs, sc.START, sc.END)
    n_ok = sum(1 for e in enriched if e["level_context_status"] in ("ok", "ok_no_level_trigger"))
    n_trig = sum(1 for e in enriched if e.get("trigger_level") is not None)
    n_headroom = sum(1 for e in enriched if e.get("headroom_dollars") is not None)
    print(f"[tw8_level_context] exploratory: {len(enriched)} signals, {n_ok} level-set-ok, "
          f"{n_trig} with a detectable trigger_level, {n_headroom} with a finite headroom", flush=True)
    bad = [e for e in enriched if e["level_context_status"] not in ("ok", "ok_no_level_trigger")]
    for b in bad[:10]:
        print(f"  DIVERGENT: {b['date']} {b['entry_ts']} {b['side']} -> {b['level_context_status']}", flush=True)
