"""Missed-Setups Scanner — EOD Stage 4b.

Problem statement (J, 2026-05-15 evening): the chart was "all over the key
levels" but the engine made only 1 trade. The existing EOD pipeline does NOT
surface which level interactions WOULD have qualified for a setup but never
fired. This is the missing post-mortem question:

    "For every named ★★+ level today, did SPY interact with it during RTH,
     and if so, would any of the 4 active/draft setups have qualified?
     What was the would-be P&L of every missed setup, summed?"

The scanner walks every closed 5m RTH bar of `date_et` and:

  1. Loads named levels from ``automation/state/key-levels.json``. Round-number
     "psychological" levels are awareness-only per OP 5 — they are NOT
     scanned as interaction sources.

  2. For each bar, classifies the bar/level interaction as one of:
       - touch       (high or low within $0.10 of level, no break)
       - rejection   (touched then closed back on the original side, ≥ $0.15 wick)
       - break       (close on the opposite side of the level by ≥ $0.10)
       - reclaim     (after a prior break, close back on the original side)

  3. For each interaction, runs the qualifier for each of the 4 setups:
       - BEARISH_REJECTION_RIDE_THE_RIBBON (puts)
       - BULLISH_RECLAIM_RIDE_THE_RIBBON   (calls)
       - SNIPER_LEVEL_BREAK                (calls or puts on a clean break)
       - SHOTGUN_SCALPER (tiers 1/2/3)     (puts or calls)

     Qualifier logic is INTENTIONALLY SIMPLIFIED relative to the live engine.
     This scanner is a hindsight diagnostic — its job is "would this have
     qualified under loose-but-honest gates?" not "exactly replicate the
     production heartbeat." We rely on detection.py for the strict replay.

  4. For each qualifying setup, computes the theoretical trade:
       - Strike pick = OTM-1 for SHOTGUN_SCALPER, ATM for RIBBON-RIDE, ATM/ITM-2
         for SNIPER (as the playbook documents).
       - Entry premium: real OPRA mid via ``lib/option_pricing_real.py`` if the
         cached CSV exists; otherwise a coarse BS-style estimate stamped
         ``pricing_source="bs_estimate"``.
       - Exit: simulates the chandelier ladder + premium stop + time stop using
         subsequent 5m bars' SPY OHLC + a delta-based premium proxy. Returns
         realized P&L and hold-minutes.

  5. Aggregates: ``missed_setup_count``, ``missed_setup_total_pnl_dollars``,
     ``engine_trades_today``, ``engine_pnl_today``, and ``edge_capture_pct``.

The scanner is INTENTIONALLY SIDE-EFFECT-FREE. It only reads. It returns a
dict. The EOD pipeline (main.py Stage 4b) calls it and may persist the result
into research_handoffs + the markdown journal section.

Per CLAUDE.md OP 8 (no deferral) and OP 22 (don't stop cooking) this lands in
the post-4pm work block on 2026-05-15.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# --- Repository wiring ----------------------------------------------------

REPO = Path(__file__).resolve().parent.parent.parent.parent
# REPO = C:\Users\jackw\Desktop\42

KEY_LEVELS_PATH = REPO / "automation" / "state" / "key-levels.json"
TRADES_CSV = REPO / "journal" / "trades.csv"
DATA_DIR = REPO / "backtest" / "data"
OPTIONS_CACHE_DIR = REPO / "backtest" / "data" / "options"

# Allow ``from lib.option_pricing_real import ...`` to resolve.
_BACKTEST_DIR = REPO / "backtest"
if str(_BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKTEST_DIR))

try:
    from lib.option_pricing_real import (  # type: ignore
        option_symbol,
        load_contract_bars,
        bar_at_or_after,
        bar_containing,
    )
    OPRA_AVAILABLE = True
except Exception as _e_opra:  # pragma: no cover — defensive
    OPRA_AVAILABLE = False
    logger.warning("option_pricing_real import failed: %s", _e_opra)

# Shared schema-v3 star derivation (2026-06-18 fix). The live key-levels.json
# (and even the daily archive snapshots) carry `tier` but NOT `strength.stars`
# — every level's `strength.stars` is null. The old local _level_stars() read
# that null and returned 0, so EVERY named level fell below MIN_STAR_RATING and
# this scanner operated on ZERO named levels. level_stars() derives stars from
# `tier` (Active=2/Carry=3/Reference=2) when `strength.stars` is absent and caps
# psychological/round-number levels at ★1.  Lesson C7 (silent zero-coverage).
try:
    from lib.watchers.level_source import level_stars as _level_source_stars  # type: ignore
    _LEVEL_SOURCE_AVAILABLE = True
except Exception as _e_lvlsrc:  # pragma: no cover — defensive
    _LEVEL_SOURCE_AVAILABLE = False
    logger.warning("level_source import failed: %s", _e_lvlsrc)


# --- Constants ------------------------------------------------------------

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
ENTRY_GATE_OPEN = dt.time(9, 30)
ENTRY_GATE_CLOSE = dt.time(15, 0)

LEVEL_TOUCH_TOLERANCE = 0.10
REJECTION_WICK_MIN = 0.15
BREAK_BODY_MIN = 0.10
MIN_STAR_RATING = 2  # ★★+ named levels only

# Default setup knobs (mirror playbook / params.json defaults).
SHOTGUN_PREMIUM_STOP_PCT = -0.20
SHOTGUN_TARGET_CAP_DOLLARS = 1.50
SHOTGUN_FALLBACK_TARGET_PCT = 0.50
SHOTGUN_TIME_STOP_MIN = 12
SHOTGUN_CHANDELIER = [(0.25, 0.0), (0.50, 0.20), (0.75, 0.40)]
SHOTGUN_QTY = 3  # Safe account default per playbook

RIBBON_TP1_PREMIUM_PCT = 0.30
RIBBON_PREMIUM_STOP_PCT = -0.08
RIBBON_TIME_STOP_MIN = 240  # 4 hours (heartbeat 15:50 ET cap dominates anyway)
RIBBON_RUNNER_TARGET_PCT = 1.50  # +150% premium runner cap
RIBBON_QTY = 3

SNIPER_PREMIUM_STOP_PCT_BEAR = -0.20
SNIPER_PREMIUM_STOP_PCT_BULL = -0.08
SNIPER_PROFIT_LOCK_THRESHOLD = 0.05
SNIPER_TIME_STOP_MIN = 360
SNIPER_QTY = 3

# Delta proxy for premium movement on a SPY tick (cents premium / cents spot).
# OTM-1 ≈ 0.45; ATM ≈ 0.55; ITM-2 ≈ 0.70. Used only when OPRA bars unavailable.
DELTA_PROXIES = {
    "ATM": 0.55,
    "OTM-1": 0.45,
    "OTM-2": 0.35,
    "ITM-2": 0.70,
}


# --- Public API -----------------------------------------------------------


def scan_missed_setups(date_et: dt.date) -> dict[str, Any]:
    """Scan the given session for missed-setup opportunities.

    Args:
        date_et: trading date (Eastern). Bars and levels are loaded for this
            date only.

    Returns:
        dict with the schema documented at the top of this module. Always
        returns a dict — never raises (errors are surfaced via the
        ``scan_warnings`` field).
    """
    date_str = date_et.isoformat()
    warnings: list[str] = []
    result: dict[str, Any] = {
        "date": date_str,
        "level_interactions": [],
        "missed_setup_count": 0,
        "missed_setup_total_pnl_dollars": 0.0,
        "engine_trades_today": 0,
        "engine_pnl_today": 0.0,
        "edge_capture_pct": 0.0,
        "scan_warnings": warnings,
        "opra_available": OPRA_AVAILABLE,
    }

    try:
        spy = _load_spy_bars(date_et)
        if spy is None or spy.empty:
            warnings.append(f"no SPY bars found for {date_str}")
            return result

        levels = _load_named_levels(date_et)
        if not levels:
            warnings.append("no ★★+ named levels found in key-levels.json")
            return result

        rth = _filter_rth(spy, date_et)
        if rth.empty:
            warnings.append(f"no RTH bars for {date_str}")
            return result

        # Track which (level_price, direction) combos have been broken so
        # subsequent reclaim/rejection classification is sequence-aware.
        broken_state: dict[tuple[float, str], int] = {}

        all_missed_pnl = 0.0
        all_missed_count = 0

        for bar_idx in range(len(rth)):
            bar = rth.iloc[bar_idx]
            bar_time = _bar_time(bar)
            if bar_time is None:
                continue

            for level in levels:
                interaction = _classify_interaction(bar, level, broken_state)
                if interaction is None:
                    continue

                # For each interaction run all qualifier candidates.
                qualifying: list[dict[str, Any]] = []
                for setup_fn in (
                    _qualify_shotgun_tier1,
                    _qualify_shotgun_tier2,
                    _qualify_shotgun_tier3,
                    _qualify_bearish_rejection,
                    _qualify_bullish_reclaim,
                    _qualify_sniper_break,
                ):
                    try:
                        miss = setup_fn(
                            bar=bar,
                            bar_idx=bar_idx,
                            level=level,
                            interaction=interaction,
                            rth=rth,
                            levels=levels,
                            date_et=date_et,
                        )
                    except Exception as _e:
                        warnings.append(
                            f"qualifier {setup_fn.__name__} raised at "
                            f"bar={bar_time} level={level['price']}: {type(_e).__name__}: {_e}"
                        )
                        miss = None
                    if miss is not None:
                        qualifying.append(miss)
                        all_missed_pnl += float(miss.get("would_be_pnl_dollars", 0.0))
                        all_missed_count += 1

                if qualifying:
                    result["level_interactions"].append({
                        "bar_time": _format_bar_time(bar),
                        "bar_idx": bar_idx,
                        "level": float(level["price"]),
                        "level_label": _level_label(level),
                        "level_stars": _level_stars(level),
                        "interaction_type": interaction["type"],
                        "interaction_distance": interaction.get("distance"),
                        "qualifying_setups": qualifying,
                    })

        result["missed_setup_count"] = all_missed_count
        result["missed_setup_total_pnl_dollars"] = round(all_missed_pnl, 2)

        # Engine performance for the same day.
        engine_trades, engine_pnl = _load_engine_trades(date_et)
        result["engine_trades_today"] = engine_trades
        result["engine_pnl_today"] = round(engine_pnl, 2)

        # Edge capture: engine_captured / (engine_captured + missed_positive).
        # If engine lost money on its trades, the captured numerator is 0
        # (we did not capture edge on those days — we LOST on them).
        captured = max(0.0, engine_pnl)
        missed_positive = max(0.0, all_missed_pnl)
        denom = captured + missed_positive
        if denom > 0:
            result["edge_capture_pct"] = round(100.0 * captured / denom, 1)
        else:
            result["edge_capture_pct"] = 0.0

    except Exception as exc:
        # Top-level catch — keep the EOD pipeline alive even if the scanner
        # blows up on unexpected input (OP 22 don't crash the rest of EOD).
        logger.exception("scan_missed_setups failed for %s", date_str)
        warnings.append(f"scan_missed_setups_error: {type(exc).__name__}: {exc}")

    return result


# --- Bar / level loaders --------------------------------------------------


def _load_spy_bars(date_et: dt.date) -> Optional[pd.DataFrame]:
    """Find a CSV containing 5m bars for date_et and return that day's slice."""
    date_str = date_et.isoformat()
    candidates = sorted(DATA_DIR.glob("spy_5m_*.csv"), reverse=True)
    for path in candidates:
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if "timestamp_et" not in df.columns:
            continue
        try:
            ts = pd.to_datetime(df["timestamp_et"], utc=True)
            df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
        except Exception:
            try:
                df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
                if df["timestamp_et"].dt.tz is not None:
                    df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
            except Exception:
                continue
        sub = df[df["timestamp_et"].dt.date == date_et].copy()
        if not sub.empty:
            sub = sub.sort_values("timestamp_et").reset_index(drop=True)
            return sub
    return None


def _filter_rth(spy: pd.DataFrame, date_et: dt.date) -> pd.DataFrame:
    """Return rows whose timestamp_et falls in [09:30, 16:00) RTH on date_et."""
    if spy is None or spy.empty:
        return pd.DataFrame()
    same_day = spy[spy["timestamp_et"].dt.date == date_et]
    times = same_day["timestamp_et"].dt.time
    mask = (times >= RTH_OPEN) & (times < RTH_CLOSE)
    return same_day[mask].reset_index(drop=True)


def _load_named_levels(date_et: dt.date) -> list[dict[str, Any]]:
    """Load ★★+ named levels from key-levels.json (excluding psychologicals).

    For historical dates where the snapshot's as_of doesn't match, the named
    levels are typically irrelevant — falls back to auto-derived levels
    (prior-day RTH H/L + premarket H/L for date_et) so historical replay
    still finds interactions. The two sources are merged with named-levels
    taking precedence when prices collide within $0.10.
    """
    named: list[dict[str, Any]] = []

    if KEY_LEVELS_PATH.exists():
        try:
            payload = json.loads(KEY_LEVELS_PATH.read_text(encoding="utf-8-sig"))
        except Exception:
            logger.exception("failed to read %s", KEY_LEVELS_PATH)
            payload = {}
        as_of = (payload.get("as_of") or "")[:10]
        snapshot_date = as_of if as_of else None

        for lv in payload.get("levels", []) or []:
            lvtype = (lv.get("type") or "").lower()
            if lvtype == "psychological":
                continue
            stars = _level_stars(lv)
            if stars < MIN_STAR_RATING:
                continue
            try:
                price = float(lv.get("price"))
            except (TypeError, ValueError):
                continue
            named.append({
                "price": price,
                "type": lvtype,
                "tier": lv.get("tier") or "",
                "label": _level_label(lv),
                "stars": stars,
                "source": lv.get("source") or "",
                "role": lv.get("role") or "",
            })

        # If named levels are dated to the requested date, use them as-is.
        if snapshot_date == date_et.isoformat() and named:
            return named

    # Fallback / augmentation: auto-derive from history.
    auto = _auto_derive_levels_for_date(date_et)

    # Merge: keep named entries first, append auto entries that aren't within $0.10 of a named.
    merged: list[dict[str, Any]] = list(named)
    for a in auto:
        ap = a["price"]
        if any(abs(ap - n["price"]) < 0.10 for n in merged):
            continue
        merged.append(a)
    return merged


def _auto_derive_levels_for_date(date_et: dt.date) -> list[dict[str, Any]]:
    """Compute prior-day RTH H/L + today's premarket H/L for a historical date.

    Used when named levels from key-levels.json don't apply (snapshot date
    differs from the date being scanned). Mirrors the auto-derive in
    shotgun_scalper_grinder._build_auto_levels for consistency.
    """
    today = _load_spy_bars(date_et)
    if today is None or today.empty:
        return []

    levels: list[dict[str, Any]] = []

    # Prior trading day's RTH H/L — load prior date explicitly (single-day loader limitation).
    for back in range(1, 7):  # walk back up to 6 days to skip weekends/holidays
        prior_date = date_et - dt.timedelta(days=back)
        prior = _load_spy_bars(prior_date)
        if prior is None or prior.empty:
            continue
        prior_rth = prior[
            (prior["timestamp_et"].dt.time >= RTH_OPEN)
            & (prior["timestamp_et"].dt.time < RTH_CLOSE)
        ]
        if prior_rth.empty:
            continue
        pdh = float(prior_rth["high"].max())
        pdl = float(prior_rth["low"].min())
        levels.append({"price": pdh, "type": "resistance", "tier": "Reference",
                       "label": f"PDH {prior_date}", "stars": 2,
                       "source": "auto_derived_PDH", "role": ""})
        levels.append({"price": pdl, "type": "support", "tier": "Reference",
                       "label": f"PDL {prior_date}", "stars": 2,
                       "source": "auto_derived_PDL", "role": ""})
        break

    # Today's premarket H/L (04:00–09:30 ET)
    pm = today[today["timestamp_et"].dt.time < RTH_OPEN]
    if not pm.empty:
        pmh = float(pm["high"].max())
        pml = float(pm["low"].min())
        levels.append({"price": pmh, "type": "resistance", "tier": "Active",
                       "label": f"PMH {date_et}", "stars": 2,
                       "source": "auto_derived_PMH", "role": ""})
        levels.append({"price": pml, "type": "support", "tier": "Active",
                       "label": f"PML {date_et}", "stars": 2,
                       "source": "auto_derived_PML", "role": ""})

    return levels


def _level_label(lv: dict[str, Any]) -> str:
    src = lv.get("source") or ""
    if src:
        # Trim source to a short label.
        return src.split("—")[0].strip()[:60]
    return f"{lv.get('tier') or ''} {lv.get('type') or ''}".strip()


def _level_stars(lv: dict[str, Any]) -> int:
    """Effective ★ rating for a level entry.

    2026-06-18 fix: delegate to the shared ``level_source.level_stars`` so that
    schema-v3 levels (which carry ``tier`` but a NULL ``strength.stars``) derive
    a real rating from tier (Active=2/Carry=3/Reference=2), with psychological /
    round-number levels capped at ★1. The previous body read ``strength.stars``
    directly and returned 0 for every live/archive level → zero named levels.

    Precedence (handled inside level_source.level_stars):
      1. ``strength.stars`` when present and > 0 (forward-compat).
      2. else tier→stars.
    Falls back to an explicit top-level ``stars`` key (used by this module's
    auto-derived PDH/PDL/PMH/PML levels) only if level_source is unavailable.
    """
    if _LEVEL_SOURCE_AVAILABLE:
        try:
            return int(_level_source_stars(lv))
        except (TypeError, ValueError):
            pass
    # Defensive fallback (level_source import failed): honour an explicit
    # strength.stars, then a top-level stars key, else 0.
    strength = lv.get("strength")
    if isinstance(strength, dict):
        try:
            s = int(strength.get("stars") or 0)
            if s > 0:
                return s
        except (TypeError, ValueError):
            pass
    try:
        return int(lv.get("stars") or 0)
    except (TypeError, ValueError):
        return 0


# --- Interaction classification ------------------------------------------


def _classify_interaction(
    bar: pd.Series,
    level: dict[str, Any],
    broken_state: dict[tuple[float, str], int],
) -> Optional[dict[str, Any]]:
    """Classify how `bar` interacts with `level`.

    Side-effects: updates `broken_state` when a fresh break is detected so a
    subsequent reclaim can be classified correctly.
    """
    try:
        lp = float(level["price"])
        bh = float(bar["high"])
        bl = float(bar["low"])
        bo = float(bar["open"])
        bc = float(bar["close"])
    except (TypeError, ValueError, KeyError):
        return None

    lvtype = (level.get("type") or "").lower()
    # Treat any non-support/non-resistance as both-sided for safety.
    is_resistance = lvtype.startswith("resistance") or lvtype == "trendline" or lvtype == ""
    is_support = lvtype.startswith("support") or lvtype == "trendline" or lvtype == ""

    # --- Break: a CLOSE through the level by >= BREAK_BODY_MIN ---
    if is_resistance and bc > lp + BREAK_BODY_MIN and bo <= lp + BREAK_BODY_MIN:
        broken_state[(lp, "above")] = broken_state.get((lp, "above"), 0) + 1
        return {"type": "break", "direction": "up", "distance": round(bc - lp, 4)}
    if is_support and bc < lp - BREAK_BODY_MIN and bo >= lp - BREAK_BODY_MIN:
        broken_state[(lp, "below")] = broken_state.get((lp, "below"), 0) + 1
        return {"type": "break", "direction": "down", "distance": round(lp - bc, 4)}

    # --- Reclaim: a prior break exists and this bar closes BACK on the original side ---
    if is_resistance and broken_state.get((lp, "above"), 0) > 0 and bc < lp - BREAK_BODY_MIN:
        broken_state[(lp, "above")] = 0  # consume
        return {"type": "reclaim", "direction": "down", "distance": round(lp - bc, 4)}
    if is_support and broken_state.get((lp, "below"), 0) > 0 and bc > lp + BREAK_BODY_MIN:
        broken_state[(lp, "below")] = 0
        return {"type": "reclaim", "direction": "up", "distance": round(bc - lp, 4)}

    # --- Rejection: bar wicked through the level then closed back on the original side ---
    # Bearish rejection at a resistance: high > level by REJECTION_WICK_MIN,
    # close < level (so high - close >= REJECTION_WICK_MIN and high > level).
    if is_resistance and bh >= lp - LEVEL_TOUCH_TOLERANCE and bh - bc >= REJECTION_WICK_MIN and bc < lp:
        return {"type": "rejection", "direction": "down", "distance": round(bh - lp, 4)}
    # Bullish rejection at support: low pierces level, close back above.
    if is_support and bl <= lp + LEVEL_TOUCH_TOLERANCE and bc - bl >= REJECTION_WICK_MIN and bc > lp:
        return {"type": "rejection", "direction": "up", "distance": round(lp - bl, 4)}

    # --- Touch: bar's high/low came within tolerance but didn't reject/break ---
    if (
        (is_resistance and abs(bh - lp) <= LEVEL_TOUCH_TOLERANCE)
        or (is_support and abs(bl - lp) <= LEVEL_TOUCH_TOLERANCE)
    ):
        ext = abs(bh - lp) if is_resistance else abs(bl - lp)
        return {"type": "touch", "direction": "neutral", "distance": round(ext, 4)}

    return None


# --- Setup qualifiers ----------------------------------------------------


def _in_entry_window(bar_time: dt.time) -> bool:
    return ENTRY_GATE_OPEN <= bar_time < ENTRY_GATE_CLOSE


def _qualify_shotgun_tier1(
    *,
    bar: pd.Series,
    bar_idx: int,
    level: dict[str, Any],
    interaction: dict[str, Any],
    rth: pd.DataFrame,
    levels: list[dict[str, Any]],
    date_et: dt.date,
) -> Optional[dict[str, Any]]:
    """SHOTGUN_SCALPER Tier 1: OPEN_REJECTION on the 09:30 bar."""
    if bar_idx != 0:
        return None
    if interaction["type"] not in ("rejection", "break"):
        return None
    bar_time = _bar_time(bar)
    if bar_time != RTH_OPEN:
        return None

    direction = "PUT" if interaction["direction"] == "down" else "CALL"
    spy_entry = float(bar["close"])
    return _simulate_shotgun_trade(
        rth=rth,
        entry_bar_idx=bar_idx,
        direction=direction,
        spy_entry=spy_entry,
        date_et=date_et,
        tier_name="SHOTGUN_SCALPER_TIER_1",
        level_label=_level_label(level),
        level_price=float(level["price"]),
    )


def _qualify_shotgun_tier2(
    *,
    bar: pd.Series,
    bar_idx: int,
    level: dict[str, Any],
    interaction: dict[str, Any],
    rth: pd.DataFrame,
    levels: list[dict[str, Any]],
    date_et: dt.date,
) -> Optional[dict[str, Any]]:
    """Tier 2: LEVEL_REJECT_LIVE — any RTH bar, rejection at a named ≥2★ level."""
    if bar_idx == 0:
        return None  # Tier 1 owns the 09:30 bar
    if interaction["type"] != "rejection":
        return None
    bar_time = _bar_time(bar)
    if bar_time is None or not _in_entry_window(bar_time):
        return None

    direction = "PUT" if interaction["direction"] == "down" else "CALL"
    spy_entry = float(bar["close"])
    return _simulate_shotgun_trade(
        rth=rth,
        entry_bar_idx=bar_idx,
        direction=direction,
        spy_entry=spy_entry,
        date_et=date_et,
        tier_name="SHOTGUN_SCALPER_TIER_2",
        level_label=_level_label(level),
        level_price=float(level["price"]),
    )


def _qualify_shotgun_tier3(
    *,
    bar: pd.Series,
    bar_idx: int,
    level: dict[str, Any],
    interaction: dict[str, Any],
    rth: pd.DataFrame,
    levels: list[dict[str, Any]],
    date_et: dt.date,
) -> Optional[dict[str, Any]]:
    """Tier 3: TRENDLINE_BREAK_RETEST proxy — clean BREAK of a ★★+ level with
    a prior touch in the last 30 bars (≥150 min) acts as a trendline-break proxy."""
    if interaction["type"] != "break":
        return None
    bar_time = _bar_time(bar)
    if bar_time is None or not _in_entry_window(bar_time):
        return None
    # Look back ≤30 bars for a prior touch of this level.
    lp = float(level["price"])
    lookback = rth.iloc[max(0, bar_idx - 30):bar_idx]
    if lookback.empty:
        return None
    touched = False
    for _, prev in lookback.iterrows():
        ph = float(prev["high"])
        pl = float(prev["low"])
        if abs(ph - lp) <= LEVEL_TOUCH_TOLERANCE or abs(pl - lp) <= LEVEL_TOUCH_TOLERANCE:
            touched = True
            break
    if not touched:
        return None

    direction = "PUT" if interaction["direction"] == "down" else "CALL"
    spy_entry = float(bar["close"])
    return _simulate_shotgun_trade(
        rth=rth,
        entry_bar_idx=bar_idx,
        direction=direction,
        spy_entry=spy_entry,
        date_et=date_et,
        tier_name="SHOTGUN_SCALPER_TIER_3",
        level_label=_level_label(level),
        level_price=lp,
    )


def _qualify_bearish_rejection(
    *,
    bar: pd.Series,
    bar_idx: int,
    level: dict[str, Any],
    interaction: dict[str, Any],
    rth: pd.DataFrame,
    levels: list[dict[str, Any]],
    date_et: dt.date,
) -> Optional[dict[str, Any]]:
    """BEARISH_REJECTION_RIDE_THE_RIBBON proxy: rejection at resistance, RTH 09:35+."""
    if interaction["type"] != "rejection":
        return None
    if interaction["direction"] != "down":
        return None
    bar_time = _bar_time(bar)
    if bar_time is None or not _in_entry_window(bar_time):
        return None
    if (level.get("type") or "").lower() != "resistance":
        return None

    spy_entry = float(bar["close"])
    return _simulate_ribbon_ride_trade(
        rth=rth,
        entry_bar_idx=bar_idx,
        direction="PUT",
        spy_entry=spy_entry,
        date_et=date_et,
        setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
        level_label=_level_label(level),
        level_price=float(level["price"]),
    )


def _qualify_bullish_reclaim(
    *,
    bar: pd.Series,
    bar_idx: int,
    level: dict[str, Any],
    interaction: dict[str, Any],
    rth: pd.DataFrame,
    levels: list[dict[str, Any]],
    date_et: dt.date,
) -> Optional[dict[str, Any]]:
    """BULLISH_RECLAIM_RIDE_THE_RIBBON proxy: reclaim/rejection at support, RTH 09:35+."""
    if interaction["type"] not in ("rejection", "reclaim"):
        return None
    if interaction["direction"] != "up":
        return None
    bar_time = _bar_time(bar)
    if bar_time is None or not _in_entry_window(bar_time):
        return None
    if (level.get("type") or "").lower() != "support":
        return None

    spy_entry = float(bar["close"])
    return _simulate_ribbon_ride_trade(
        rth=rth,
        entry_bar_idx=bar_idx,
        direction="CALL",
        spy_entry=spy_entry,
        date_et=date_et,
        setup_name="BULLISH_RECLAIM_RIDE_THE_RIBBON",
        level_label=_level_label(level),
        level_price=float(level["price"]),
    )


def _qualify_sniper_break(
    *,
    bar: pd.Series,
    bar_idx: int,
    level: dict[str, Any],
    interaction: dict[str, Any],
    rth: pd.DataFrame,
    levels: list[dict[str, Any]],
    date_et: dt.date,
) -> Optional[dict[str, Any]]:
    """SNIPER_LEVEL_BREAK proxy: clean 5m bar break of a ★★+ level with body
    ≥ $0.10 past the level. Volume gate is approximated against the trailing
    20-bar average."""
    if interaction["type"] != "break":
        return None
    bar_time = _bar_time(bar)
    if bar_time is None or not _in_entry_window(bar_time):
        return None
    stars = _level_stars(level)
    if stars < 2:
        return None

    # Volume gate.
    vol_baseline = _vol_baseline_20(rth, bar_idx)
    try:
        bar_vol = float(bar["volume"])
    except (KeyError, TypeError, ValueError):
        bar_vol = 0.0
    if vol_baseline > 0 and bar_vol < 1.5 * vol_baseline:
        return None

    direction = "PUT" if interaction["direction"] == "down" else "CALL"
    spy_entry = float(bar["close"])
    return _simulate_sniper_trade(
        rth=rth,
        entry_bar_idx=bar_idx,
        direction=direction,
        spy_entry=spy_entry,
        date_et=date_et,
        level_label=_level_label(level),
        level_price=float(level["price"]),
    )


# --- Trade simulators -----------------------------------------------------


def _simulate_shotgun_trade(
    *,
    rth: pd.DataFrame,
    entry_bar_idx: int,
    direction: str,
    spy_entry: float,
    date_et: dt.date,
    tier_name: str,
    level_label: str,
    level_price: float,
) -> Optional[dict[str, Any]]:
    """Simulate a SHOTGUN_SCALPER trade: OTM-1 strike, chandelier ladder,
    -20% premium stop, 12-min time stop, single-shot exit."""
    strike = _pick_strike(spy_entry, direction, "OTM-1")
    entry_premium, pricing_source = _entry_premium(
        date_et=date_et, strike=strike, direction=direction,
        spy_at_entry=spy_entry, bar=rth.iloc[entry_bar_idx],
        strike_class="OTM-1",
    )
    if entry_premium is None or entry_premium <= 0:
        return None

    delta = DELTA_PROXIES["OTM-1"]
    exit_px, exit_reason, hold_min = _simulate_chandelier_exit(
        rth=rth,
        entry_bar_idx=entry_bar_idx,
        entry_premium=entry_premium,
        delta=delta,
        direction=direction,
        spy_entry=spy_entry,
        stop_pct=SHOTGUN_PREMIUM_STOP_PCT,
        chandelier=SHOTGUN_CHANDELIER,
        fallback_target_pct=SHOTGUN_FALLBACK_TARGET_PCT,
        time_stop_min=SHOTGUN_TIME_STOP_MIN,
        target_cap_dollars=SHOTGUN_TARGET_CAP_DOLLARS,
    )
    pnl = round((exit_px - entry_premium) * SHOTGUN_QTY * 100, 2)
    confidence = "high" if exit_reason in ("primary_target", "chandelier_rung_3") else "medium"
    return {
        "setup": tier_name,
        "direction": direction,
        "strike": strike,
        "strike_class": "OTM-1",
        "qty": SHOTGUN_QTY,
        "would_be_entry_premium": round(entry_premium, 3),
        "would_be_exit_premium": round(exit_px, 3),
        "would_be_pnl_dollars": pnl,
        "would_be_hold_minutes": hold_min,
        "exit_reason": exit_reason,
        "pricing_source": pricing_source,
        "confidence": confidence,
        "level_price": level_price,
        "level_label": level_label,
        "why_missed": _missed_reason(tier_name),
    }


def _simulate_ribbon_ride_trade(
    *,
    rth: pd.DataFrame,
    entry_bar_idx: int,
    direction: str,
    spy_entry: float,
    date_et: dt.date,
    setup_name: str,
    level_label: str,
    level_price: float,
) -> Optional[dict[str, Any]]:
    """Simulate a RIBBON-RIDE trade: ATM strike, -8% premium stop, TP1 at +30%
    or chart-level, runner to +150% premium cap or EOD time stop."""
    strike = _pick_strike(spy_entry, direction, "ATM")
    entry_premium, pricing_source = _entry_premium(
        date_et=date_et, strike=strike, direction=direction,
        spy_at_entry=spy_entry, bar=rth.iloc[entry_bar_idx],
        strike_class="ATM",
    )
    if entry_premium is None or entry_premium <= 0:
        return None
    delta = DELTA_PROXIES["ATM"]
    exit_px, exit_reason, hold_min = _simulate_tp1_runner_exit(
        rth=rth,
        entry_bar_idx=entry_bar_idx,
        entry_premium=entry_premium,
        delta=delta,
        direction=direction,
        stop_pct=RIBBON_PREMIUM_STOP_PCT,
        tp1_pct=RIBBON_TP1_PREMIUM_PCT,
        runner_target_pct=RIBBON_RUNNER_TARGET_PCT,
        time_stop_min=RIBBON_TIME_STOP_MIN,
    )
    pnl = round((exit_px - entry_premium) * RIBBON_QTY * 100, 2)
    confidence = "high" if exit_reason in ("runner_target", "tp1") else "medium"
    return {
        "setup": setup_name,
        "direction": direction,
        "strike": strike,
        "strike_class": "ATM",
        "qty": RIBBON_QTY,
        "would_be_entry_premium": round(entry_premium, 3),
        "would_be_exit_premium": round(exit_px, 3),
        "would_be_pnl_dollars": pnl,
        "would_be_hold_minutes": hold_min,
        "exit_reason": exit_reason,
        "pricing_source": pricing_source,
        "confidence": confidence,
        "level_price": level_price,
        "level_label": level_label,
        "why_missed": _missed_reason(setup_name),
    }


def _simulate_sniper_trade(
    *,
    rth: pd.DataFrame,
    entry_bar_idx: int,
    direction: str,
    spy_entry: float,
    date_et: dt.date,
    level_label: str,
    level_price: float,
) -> Optional[dict[str, Any]]:
    """Simulate SNIPER: ATM strike, asymmetric stops, EOD time stop."""
    strike = _pick_strike(spy_entry, direction, "ATM")
    entry_premium, pricing_source = _entry_premium(
        date_et=date_et, strike=strike, direction=direction,
        spy_at_entry=spy_entry, bar=rth.iloc[entry_bar_idx],
        strike_class="ATM",
    )
    if entry_premium is None or entry_premium <= 0:
        return None
    delta = DELTA_PROXIES["ATM"]
    stop_pct = SNIPER_PREMIUM_STOP_PCT_BEAR if direction == "PUT" else SNIPER_PREMIUM_STOP_PCT_BULL
    exit_px, exit_reason, hold_min = _simulate_tp1_runner_exit(
        rth=rth,
        entry_bar_idx=entry_bar_idx,
        entry_premium=entry_premium,
        delta=delta,
        direction=direction,
        stop_pct=stop_pct,
        tp1_pct=0.40,
        runner_target_pct=1.50,
        time_stop_min=SNIPER_TIME_STOP_MIN,
    )
    pnl = round((exit_px - entry_premium) * SNIPER_QTY * 100, 2)
    return {
        "setup": "SNIPER_LEVEL_BREAK",
        "direction": direction,
        "strike": strike,
        "strike_class": "ATM",
        "qty": SNIPER_QTY,
        "would_be_entry_premium": round(entry_premium, 3),
        "would_be_exit_premium": round(exit_px, 3),
        "would_be_pnl_dollars": pnl,
        "would_be_hold_minutes": hold_min,
        "exit_reason": exit_reason,
        "pricing_source": pricing_source,
        "confidence": "high" if exit_reason in ("runner_target", "tp1") else "medium",
        "level_price": level_price,
        "level_label": level_label,
        "why_missed": _missed_reason("SNIPER_LEVEL_BREAK"),
    }


def _simulate_chandelier_exit(
    *,
    rth: pd.DataFrame,
    entry_bar_idx: int,
    entry_premium: float,
    delta: float,
    direction: str,
    spy_entry: float,
    stop_pct: float,
    chandelier: list[tuple[float, float]],
    fallback_target_pct: float,
    time_stop_min: int,
    target_cap_dollars: float,
) -> tuple[float, str, int]:
    """Walk subsequent 5m bars; return (exit_premium, reason, hold_min)."""
    stop_floor = entry_premium * (1 + stop_pct)
    locked_floor = stop_floor
    rung_idx = 0
    bars_per_min = 5  # 5m bars
    max_bars = max(1, math.ceil(time_stop_min / bars_per_min))
    sign = -1.0 if direction == "PUT" else 1.0

    for k in range(1, max_bars + 1):
        idx = entry_bar_idx + k
        if idx >= len(rth):
            break
        bar = rth.iloc[idx]
        try:
            bh = float(bar["high"])
            bl = float(bar["low"])
            bc = float(bar["close"])
        except (KeyError, TypeError, ValueError):
            break
        # Premium high/low derived from SPY low/high via direction-aware delta.
        if direction == "PUT":
            prem_high = entry_premium + delta * (spy_entry - bl)
            prem_low = entry_premium + delta * (spy_entry - bh)
        else:
            prem_high = entry_premium + delta * (bh - spy_entry)
            prem_low = entry_premium + delta * (bl - spy_entry)

        # Chandelier ratchet — bump floor based on premium high.
        gain = (prem_high - entry_premium) / entry_premium
        while rung_idx < len(chandelier) and gain >= chandelier[rung_idx][0]:
            new_floor = entry_premium * (1 + chandelier[rung_idx][1])
            if new_floor > locked_floor:
                locked_floor = new_floor
            rung_idx += 1

        # Check primary target (fallback at +fallback_target_pct premium, or
        # spot target_cap_dollars on the favorable side).
        if direction == "PUT":
            spot_target = spy_entry - target_cap_dollars
            spot_hit = bl <= spot_target
        else:
            spot_target = spy_entry + target_cap_dollars
            spot_hit = bh >= spot_target
        prem_target = entry_premium * (1 + fallback_target_pct)
        prem_hit = prem_high >= prem_target

        if spot_hit or prem_hit:
            return prem_target if prem_hit else (entry_premium + delta * target_cap_dollars), "primary_target", k * bars_per_min

        # Check stop (locked floor).
        if prem_low <= locked_floor:
            reason = "premium_stop" if locked_floor <= entry_premium else "chandelier_floor"
            return locked_floor, reason, k * bars_per_min

    # Time stop.
    last_idx = min(entry_bar_idx + max_bars, len(rth) - 1)
    bar = rth.iloc[last_idx]
    try:
        bc = float(bar["close"])
    except (KeyError, TypeError, ValueError):
        bc = spy_entry
    if direction == "PUT":
        exit_prem = entry_premium + delta * (spy_entry - bc)
    else:
        exit_prem = entry_premium + delta * (bc - spy_entry)
    # Honor locked_floor on time stop too.
    exit_prem = max(exit_prem, locked_floor)
    return exit_prem, "time_stop", time_stop_min


def _simulate_tp1_runner_exit(
    *,
    rth: pd.DataFrame,
    entry_bar_idx: int,
    entry_premium: float,
    delta: float,
    direction: str,
    stop_pct: float,
    tp1_pct: float,
    runner_target_pct: float,
    time_stop_min: int,
) -> tuple[float, str, int]:
    """Two-leg exit: 50% qty at TP1, rest rides to runner_target or stop."""
    stop_premium = entry_premium * (1 + stop_pct)
    tp1_premium = entry_premium * (1 + tp1_pct)
    runner_premium = entry_premium * (1 + runner_target_pct)
    bars_per_min = 5
    max_bars = max(1, math.ceil(time_stop_min / bars_per_min))

    tp1_hit = False
    for k in range(1, max_bars + 1):
        idx = entry_bar_idx + k
        if idx >= len(rth):
            break
        bar = rth.iloc[idx]
        try:
            bh = float(bar["high"])
            bl = float(bar["low"])
            bc = float(bar["close"])
        except (KeyError, TypeError, ValueError):
            break
        if direction == "PUT":
            # PUT premium peaks when SPY hits BAR LOW (worst for SPY = best for puts).
            spy_at_entry_local = float(rth.iloc[entry_bar_idx]["close"])
            prem_high = entry_premium + delta * (spy_at_entry_local - bl)
            prem_low = entry_premium + delta * (spy_at_entry_local - bh)
        else:
            spy_at_entry_local = float(rth.iloc[entry_bar_idx]["close"])
            prem_high = entry_premium + delta * (bh - spy_at_entry_local)
            prem_low = entry_premium + delta * (bl - spy_at_entry_local)

        if not tp1_hit and prem_high >= tp1_premium:
            tp1_hit = True
        if prem_high >= runner_premium:
            # Blended exit: 50% at TP1, 50% at runner_premium
            blended = 0.5 * tp1_premium + 0.5 * runner_premium
            return blended, "runner_target", k * bars_per_min
        if prem_low <= stop_premium:
            if tp1_hit:
                # 50% at TP1, 50% at stop
                blended = 0.5 * tp1_premium + 0.5 * max(stop_premium, entry_premium)
                return blended, "stop_after_tp1", k * bars_per_min
            return stop_premium, "premium_stop", k * bars_per_min

    # Time stop at last bar close.
    last_idx = min(entry_bar_idx + max_bars, len(rth) - 1)
    bar = rth.iloc[last_idx]
    try:
        bc = float(bar["close"])
    except (KeyError, TypeError, ValueError):
        bc = float(rth.iloc[entry_bar_idx]["close"])
    spy_at_entry_local = float(rth.iloc[entry_bar_idx]["close"])
    if direction == "PUT":
        exit_prem = entry_premium + delta * (spy_at_entry_local - bc)
    else:
        exit_prem = entry_premium + delta * (bc - spy_at_entry_local)
    if tp1_hit:
        blended = 0.5 * tp1_premium + 0.5 * exit_prem
        return blended, "time_stop_after_tp1", time_stop_min
    return exit_prem, "time_stop", time_stop_min


# --- Pricing helpers ------------------------------------------------------


def _pick_strike(spy_at_entry: float, direction: str, strike_class: str) -> int:
    base = int(round(spy_at_entry))
    if strike_class == "ATM":
        return base
    if strike_class == "OTM-1":
        return base - 1 if direction == "PUT" else base + 1
    if strike_class == "OTM-2":
        return base - 2 if direction == "PUT" else base + 2
    if strike_class == "ITM-2":
        return base + 2 if direction == "PUT" else base - 2
    return base


def _entry_premium(
    *,
    date_et: dt.date,
    strike: int,
    direction: str,
    spy_at_entry: float,
    bar: pd.Series,
    strike_class: str,
) -> tuple[Optional[float], str]:
    """Look up the option premium for (strike, direction) at bar.

    Returns (premium, pricing_source). Falls back to a BS-style estimate when
    the OPRA cache is unavailable.
    """
    side = "P" if direction == "PUT" else "C"
    if OPRA_AVAILABLE:
        try:
            symbol = option_symbol(date_et, strike, side)
            df = load_contract_bars(symbol)
            if df is not None and not df.empty:
                bar_ts = bar.get("timestamp_et")
                if isinstance(bar_ts, str):
                    bar_ts = pd.to_datetime(bar_ts)
                next_bar = bar_at_or_after(df, bar_ts + dt.timedelta(seconds=1))
                if next_bar is not None:
                    return float(next_bar.vwap), "opra_real"
                contained = bar_containing(df, bar_ts)
                if contained is not None:
                    return float(contained.vwap), "opra_real"
        except Exception:
            logger.exception("OPRA lookup failed for %s %s %s", date_et, strike, direction)

    # Fallback: BS-style estimate. Crude — uses |moneyness| and a fixed-IV proxy.
    moneyness = strike - spy_at_entry
    if direction == "PUT":
        intrinsic = max(0.0, strike - spy_at_entry)
    else:
        intrinsic = max(0.0, spy_at_entry - strike)
    # Time-decay scale: estimate $0.50-$2.00 typical for OTM-1 0DTE
    if strike_class == "ATM":
        time_value = 1.50
    elif strike_class == "OTM-1":
        time_value = 0.90
    elif strike_class == "OTM-2":
        time_value = 0.55
    elif strike_class == "ITM-2":
        time_value = 1.10
    else:
        time_value = 1.00
    # Reduce time value as moneyness deepens OTM.
    if direction == "PUT" and strike < spy_at_entry:
        time_value *= max(0.4, 1.0 - 0.2 * abs(moneyness))
    if direction == "CALL" and strike > spy_at_entry:
        time_value *= max(0.4, 1.0 - 0.2 * abs(moneyness))
    return round(intrinsic + time_value, 3), "bs_estimate"


def _vol_baseline_20(rth: pd.DataFrame, bar_idx: int) -> float:
    if bar_idx <= 0:
        return 0.0
    start = max(0, bar_idx - 20)
    prior = rth.iloc[start:bar_idx]
    try:
        return float(prior["volume"].mean())
    except Exception:
        return 0.0


# --- Engine reconciliation -----------------------------------------------


def _load_engine_trades(date_et: dt.date) -> tuple[int, float]:
    """Read journal/trades.csv for `date_et` and return (count, total_pnl)."""
    if not TRADES_CSV.exists():
        return 0, 0.0
    date_str = date_et.isoformat()
    count = 0
    pnl_sum = 0.0
    try:
        with TRADES_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("date") != date_str:
                    continue
                count += 1
                try:
                    pnl_sum += float(
                        (row.get("dollar_pnl") or "0").replace(",", "").replace("$", "")
                    )
                except (ValueError, AttributeError):
                    pass
    except Exception:
        logger.exception("failed to read %s", TRADES_CSV)
    return count, pnl_sum


# --- Utility --------------------------------------------------------------


def _bar_time(bar: pd.Series) -> Optional[dt.time]:
    ts = bar.get("timestamp_et")
    if ts is None:
        return None
    if isinstance(ts, str):
        try:
            ts = pd.to_datetime(ts)
        except Exception:
            return None
    if hasattr(ts, "time"):
        return ts.time()
    return None


def _format_bar_time(bar: pd.Series) -> str:
    t = _bar_time(bar)
    if t is None:
        return "??:?? ET"
    return f"{t.strftime('%H:%M')} ET"


def _missed_reason(setup_name: str) -> str:
    """Best-guess root cause for why the engine missed this setup."""
    if setup_name.startswith("SHOTGUN"):
        return "SHOTGUN_SCALPER not yet live (DRAFT WATCH-ONLY)"
    if setup_name == "SNIPER_LEVEL_BREAK":
        return "SNIPER DRAFT WATCH-ONLY; not in heartbeat live triggers"
    if "REJECTION_RIDE" in setup_name or "RECLAIM_RIDE" in setup_name:
        return "Heartbeat closed-bar gate or ribbon/VIX filter blocked entry"
    return "engine did not fire on this bar"


__all__ = ["scan_missed_setups"]
