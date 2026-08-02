"""reconstruct_levels_asof.py -- Path A admissibility for the level-target-exit prereg
(analysis/recommendations/level-target-exit-prereg-2026-07-31.json).

WHY THIS EXISTS. That prereg's step_1_level_source names `key-levels-history/{DATE}/{HHMM}
.json` as the level source, but that snapshot archive holds only 6 dates -- "very likely
FATAL to reaching the minimum n on the primary cohort." The prereg's own contingency names
Path A as the fix: "Reconstruct historical key-levels as-of files deterministically from
cached SPY bars using the SAME producer the live path uses (refresh_levels_intraday.py /
daily_context.py)... only admissible if the producer is provably causal... proven with a
vary-and-assert test BEFORE any reconstructed level file is used."

This module IS that reconstruction. backtest/tests/test_reconstruct_levels_asof.py IS that
proof (test_causality_vary_and_assert_future_bars_never_leak, RED-proofed against a
deliberately-unsliced control so the test is known to have teeth).

WHAT IT RECONSTRUCTS, AND WHAT IT DOES NOT (disclosed, not hidden):
  RECONSTRUCTED -- both are pure functions of bar history, confirmed by direct read of both
  source files this session (2026-08-02):
    * daily_context_shelf  (weight 5) -- daily_context.py's multi-week shelf-zone scan
      (band/touch/span/break/backside-retest), the exact producer of the 743.25 level that
      fired the 2026-07-31 anchor trade (verified below: reconstructing as of that trade's
      entry tick reproduces SHELF_742.45_744.05, mid 743.25, zone_width 0.80, byte-for-byte
      against the live-written key-levels-history snapshot).
    * intraday (weight 2)  -- refresh_levels_intraday.py's INTRADAY_RTH_HIGH/LOW, SWING_HIGH/
      LOW, PMH/PML, reusing its OWN `_swing_levels` / `_degeneracy_reason` / `_zone_width` /
      `_level` / `_normalize_levels` functions verbatim (imported, never reimplemented).
  NOT RECONSTRUCTED -- disclosed as a scope limit, not silently dropped:
    * level_memory (key-levels-memory.json) -- a separately-maintained shadow multi-day map,
      not a pure function of bar history as far as this session could establish; excluded.
    * premarket-curated / "protocol audit" levels -- daily_context.py's own docstring: "In
      production, levels are written by premarket from chart structure + protocol audit."
      Not purely algorithmic; excluded.
  NET EFFECT: this reconstruction is a CONSERVATIVE SUBSET of what a live key-levels.json
  would have shown at the same instant. It can only OMIT an eligible level a live file would
  have carried -- it can never FABRICATE one that would not have qualified. Every study that
  consumes this module must carry this scope note (the level-target-exit study does, in its
  own _meta block).

CAUSALITY, precisely. `reconstruct_levels()` takes the FULL daily-bar list and FULL 5-minute
DataFrame (any range) and slices BOTH internally to strictly <= as_of_et before any bar ever
reaches daily_context.compute_daily_context or refresh_levels_intraday's helpers -- both of
which are pure/injectable (verified by reading both source files: compute_daily_context(bars=
..., now=...) touches network ONLY when bars is None; refresh_levels_intraday's helpers take
DataFrames as plain arguments with zero I/O). "Today" is represented by a SYNTHETIC partial
daily bar built ONLY from today's own 5-minute bars <= as_of_et (open=today's first print,
high/low/close = the running max/min/last SO FAR, volume = the running sum) -- exactly what a
live mid-session daily-bar fetch would return, never a peek at today's eventual close.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import daily_context as dctx_mod          # noqa: E402
import refresh_levels_intraday as rli     # noqa: E402

SHELF_UPSERT_BAND = rli.SHELF_UPSERT_BAND
LEVEL_WEIGHT_SHELF = rli.LEVEL_WEIGHT_SHELF
LEVEL_WEIGHT_INTRADAY = rli.LEVEL_WEIGHT_INTRADAY

RECONSTRUCTION_SCOPE = (
    "shelf(daily_context_shelf, weight5) + intraday(RTH-hi-lo/swing/PMH-PML, weight2) ONLY "
    "-- level_memory + premarket-curated levels NOT reconstructed. Conservative subset: can "
    "omit an eligible level a live file would have carried, never fabricate one."
)


def _synthetic_today_daily_bar(bars_5m_today: pd.DataFrame, date_str: str) -> "dict | None":
    """Aggregate today's already-<=-as_of-sliced 5m bars into a partial daily OHLCV bar --
    exactly what a live mid-session daily-bar fetch would show: today's open, the high/low
    SO FAR, the last close SO FAR, volume SO FAR. None when no bars exist yet for today
    (pre-open as-of instant)."""
    if bars_5m_today.empty:
        return None
    return {
        "date": date_str,
        "o": float(bars_5m_today["open"].iloc[0]),
        "h": float(bars_5m_today["high"].max()),
        "l": float(bars_5m_today["low"].min()),
        "c": float(bars_5m_today["close"].iloc[-1]),
        "v": float(bars_5m_today["volume"].sum()),
    }


def _prep_5m(five_min_df: pd.DataFrame, as_of_et: dt.datetime) -> pd.DataFrame:
    """Slice to timestamp_et <= as_of_et. THE causality choke point for the intraday family."""
    df = five_min_df
    ts_col = df["timestamp_et"]
    if not pd.api.types.is_datetime64_any_dtype(ts_col):
        ts_col = pd.to_datetime(ts_col)
    if getattr(ts_col.dt, "tz", None) is not None:
        ts_col = ts_col.dt.tz_localize(None)
    df = df.assign(timestamp_et=ts_col)
    as_of_naive = pd.Timestamp(as_of_et)
    if as_of_naive.tzinfo is not None:
        as_of_naive = as_of_naive.tz_localize(None)
    df = df.loc[df["timestamp_et"] <= as_of_naive].copy()
    if not df.empty:
        df["date"] = df["timestamp_et"].dt.strftime("%Y-%m-%d")
        df["hm"] = df["timestamp_et"].dt.strftime("%H:%M")
    return df


def reconstruct_levels(*, as_of_et: dt.datetime, daily_bars: list, five_min_df: pd.DataFrame,
                       spot: float) -> dict:
    """Pure reconstruction of the engine's ACTIVE level list as of `as_of_et`. See module
    docstring for exact scope + causality argument.

    daily_bars  : chronological list[dict(date,o,h,l,c,v)], ANY range -- sliced internally to
                  date < as_of_et's date, THEN a synthetic partial bar for as_of_et's own date
                  is appended, built only from 5m bars <= as_of_et (never a peek at the real
                  eventual daily close).
    five_min_df : full-history 5-min SPY OHLCV DataFrame, column 'timestamp_et' (tz-aware or
                  naive ET), ANY range -- sliced internally to timestamp_et <= as_of_et.
    spot        : spot price at as_of_et (caller-supplied, e.g. the entry's own logged spot --
                  this function never re-derives "the" as-of print itself).
    """
    today_str = as_of_et.strftime("%Y-%m-%d")
    now_iso = as_of_et.strftime("%Y-%m-%dT%H:%M:%S-04:00")

    df = _prep_5m(five_min_df, as_of_et)
    if df.empty:
        return {"ok": False, "error": "no 5m bars at/before as_of", "levels": []}

    today_df = df[df["date"] == today_str]
    # LOOKBACK WINDOW PARITY: daily_context.py's live _fetch_daily_bars(days=LOOKBACK_DAYS=60)
    # requests exactly 60 CALENDAR days back from fetch time -- not the full cached history.
    # Matching this window matters: the shelf merge is a greedy strongest-first (most touches
    # wins) non-overlap scan, so handing it a much LONGER history than production ever saw can
    # surface extra historical touches for a competing candidate band and silently change which
    # shelf wins, even though the reconstruction stays causal (no future leakage) either way.
    # This is "the SAME producer... re-running it with a hard as-of cutoff" -- matching its own
    # fetch window, not just its function signature.
    window_start = (as_of_et.date() - dt.timedelta(days=dctx_mod.LOOKBACK_DAYS))
    prior_daily = [b for b in daily_bars if window_start.isoformat() <= b["date"] < today_str]
    synth_today = _synthetic_today_daily_bar(today_df, today_str)
    daily_bars_causal = prior_daily + ([synth_today] if synth_today else [])

    dctx = dctx_mod.compute_daily_context(bars=daily_bars_causal, now=as_of_et)

    rth = today_df[(today_df["hm"] >= "09:30") & (today_df["hm"] <= "16:00")]
    pre = today_df[today_df["hm"] < "09:30"]

    computed, refused = [], []

    def _try_add(label, price, source, sub):
        reason = rli._degeneracy_reason(sub)
        if reason:
            refused.append({"label": label, "reason": reason})
            return
        computed.append((label, price, source, len(sub), float(sub["volume"].sum())))

    if len(rth):
        _try_add("INTRADAY_RTH_HIGH", float(rth["high"].max()), "intraday_rth_high", rth)
        _try_add("INTRADAY_RTH_LOW", float(rth["low"].min()), "intraday_rth_low", rth)
    sh, sl = rli._swing_levels(rth)
    if sh is not None:
        _try_add("INTRADAY_SWING_HIGH", sh, "intraday_swing_high", rth)
    if sl is not None:
        _try_add("INTRADAY_SWING_LOW", sl, "intraday_swing_low", rth)
    if len(pre):
        _try_add("INTRADAY_PMH", float(pre["high"].max()), "premarket_high", pre)
        _try_add("INTRADAY_PML", float(pre["low"].min()), "premarket_low", pre)

    levels = []
    for label, price, source, n_bars, volume in computed:
        lvl = rli._level(price, spot, f"{label}_{today_str}", source, now_iso,
                         source_feed="sip_cached", n_bars=n_bars, volume=volume,
                         weight=LEVEL_WEIGHT_INTRADAY)
        levels.append(lvl)

    shelf_zones = (dctx.get("shelf_zones") or []) if dctx.get("ok") else []
    for sh_zone in shelf_zones:
        lo, hi = sh_zone["band_low"], sh_zone["band_high"]
        mid = round((lo + hi) / 2, 2)
        if abs(mid - spot) > SHELF_UPSERT_BAND:
            continue
        brk = sh_zone.get("break")
        if brk and brk.get("direction") == "down":
            role = "resistance"
        elif brk and brk.get("direction") == "up":
            role = "support"
        else:
            role = "resistance" if mid >= spot else "support"
        levels.append({
            "price": mid, "type": role, "role": role,
            "label": f"SHELF_{lo:.2f}_{hi:.2f}_{today_str}",
            "tier": "Active", "source": "daily_context_shelf",
            "zone_width": round((hi - lo) / 2, 4), "zone_width_provenance": "shelf_band_observed",
            "weight": LEVEL_WEIGHT_SHELF,
            "touches": sh_zone["touches"], "span_sessions": sh_zone["span_sessions"],
            "shelf_broken": sh_zone["broken"], "shelf_break": brk,
        })

    levels = rli._normalize_levels(levels, spot)

    return {
        "ok": True,
        "as_of_et": now_iso,
        "spot": spot,
        "levels": levels,
        "shelf_zones_raw": shelf_zones,
        "n_daily_bars_used": len(daily_bars_causal),
        "n_5m_bars_used": len(today_df),
        "refused": refused,
        "scope": RECONSTRUCTION_SCOPE,
    }
