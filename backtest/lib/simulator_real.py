"""Bracket-order simulation using REAL OPRA option bars.

Mirror of `simulator.py` but every premium reference comes from
`backtest/data/options/{symbol}.csv` (real fills) instead of Black-Scholes.

Fill conventions (NO LOOK-AHEAD):
  - Trigger fires on the CLOSE of the trigger bar (e.g., bar at 10:25:00 covers
    10:25-10:30 and closes at 10:30:00).
  - Entry fills on the NEXT 5-min bar after the trigger bar — at that bar's open
    price plus an entry-slippage buffer (defaults to $0.02 per contract = bid/ask
    half-spread on liquid 0DTE ATM options).
  - This means MIN HOLD = 5 minutes (one full bar after entry).
  - Stop touched (bar.low <= stop): fill at stop_premium (limit-stop fills here).
  - TP1 touched (bar.high >= tp1): fill at tp1_premium (limit fills exactly).
  - Market exits (level stop, ribbon flip, time stop): fill at bar.close minus
    exit_slippage ($0.02 default — we lose the half-spread on the way out).

Conservative: same-bar stop+TP1 conflict → stop fills first.

Slippage parameters (configurable per call):
  - entry_slippage: added to entry fill (we pay the ASK side of bid/ask spread).
  - exit_slippage: subtracted from market-exit fills (we hit the BID).
  - Limit-order exits (TP1 hit, BE stop hit, premium stop hit) have NO slippage —
    they fill exactly at the bracket level.

Differences vs BS simulator:
  - max_adverse_premium / max_favorable_premium reflect actual bar lows/highs.
  - Strike comes from auto-detected entry strike — round(spot, $1) like live engine.
  - Entry price is REAL — no IV proxy, no theta model, no put-call parity.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .option_pricing_real import (
    OptionBar,
    bar_at_or_after,
    bar_containing,
    load_contract_bars,
    option_symbol,
    quote_at_index,
)
from .ribbon import RibbonState
from .simulator import (
    DEFAULT_QTY,
    PREMIUM_STOP_PCT,
    RUNNER_MAX_PREMIUM_PCT,
    TIME_STOP_ET,
    TP1_PREMIUM_PCT,
    TP1_QTY_FRACTION,
    ExitReason,
    TradeFill,
)


def _strike_from_spot(spot: float) -> int:
    """ATM strike = round(spot) to nearest dollar."""
    return int(round(spot))


def _ribbon_at(ribbon_df: Optional[pd.DataFrame], idx: int) -> Optional[RibbonState]:
    if ribbon_df is None or idx < 0 or idx >= len(ribbon_df):
        return None
    row = ribbon_df.iloc[idx]
    if row["stack"] == "WARMUP" or pd.isna(row["fast"]):
        return None
    return RibbonState(
        fast=float(row["fast"]),
        pivot=float(row["pivot"]),
        slow=float(row["slow"]),
        spread_cents=float(row["spread_cents"]),
        stack=str(row["stack"]),
    )


# Default slippage tuned for SPY 0DTE ATM options: typical spread 0.04-0.10,
# half-spread ≈ 0.02-0.05. We use $0.02 for both sides — slightly aggressive but
# defensible for OPRA-feed liquidity at common strikes. Tune with `entry_slippage`
# and `exit_slippage` kwargs on simulate_trade_real.
DEFAULT_ENTRY_SLIPPAGE = 0.02
DEFAULT_EXIT_SLIPPAGE = 0.02


# ── Stepped profit-lock rungs (T50b 2026-05-13, ported from simulator_real_trailing.py)
# (HWM_multiple, floor_multiple). MUST be ascending. Used when profit_lock_mode='stepped'.
STEPPED_RUNGS: list[tuple[float, float]] = [
    (1.20, 1.10),  # +20% HWM → lock +10%
    (1.50, 1.25),  # +50% HWM → lock +25%
    (2.00, 1.50),  # +100% HWM → lock +50%
    (3.00, 2.00),  # +200% HWM → lock +100%
]


def _regime_trail_pct(entry_vix: float, vix_map: Optional[dict], scalar_fallback: float) -> float:
    """Resolve a regime-conditional trail % from a {vix_ceiling: trail_pct} map.

    Ascending ceilings; the first ceiling >= entry_vix wins (so the map reads as
    "VIX up to X -> use this trail"). Falls through to `scalar_fallback` when the map
    is None/empty, when entry_vix <= 0 (VIX unknown), or when entry_vix exceeds every
    ceiling. Vol-scaled exit (Kim-Tse-Wald): wider trail in high vol, tighter in calm.
    """
    if not vix_map or entry_vix <= 0:
        return scalar_fallback
    # Tolerant of int/float/str keys.
    pairs = sorted((float(k), float(v)) for k, v in vix_map.items())
    for ceiling, trail in pairs:
        if entry_vix <= ceiling:
            return trail
    return scalar_fallback


def _stepped_floor(entry_premium: float, hwm: float) -> Optional[float]:
    """Return the highest applicable stepped floor, or None if HWM hasn't reached
    the first rung. Assumes STEPPED_RUNGS is ascending."""
    if entry_premium <= 0 or hwm <= 0:
        return None
    ratio = hwm / entry_premium
    floor: Optional[float] = None
    for rung_hwm, rung_floor in STEPPED_RUNGS:
        if ratio >= rung_hwm:
            floor = entry_premium * rung_floor
        else:
            break
    return floor


# ── Tiered exit primitives (CLAUDE.md operating principle 11) ────────────────

def _bar_geometry(o, h, l, c):
    rng = h - l
    if rng <= 0:
        return {"body_pct": 0, "upper_wick": 0, "lower_wick": 0,
                "is_red": False, "is_green": False, "rng": 0}
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    return {
        "body_pct": body / rng,
        "upper_wick": upper / rng,
        "lower_wick": lower / rng,
        "is_red": c < o,
        "is_green": c > o,
        "rng": rng,
    }


def _is_hammer(spy_bar):
    g = _bar_geometry(spy_bar["open"], spy_bar["high"], spy_bar["low"], spy_bar["close"])
    return (
        (g["is_green"] or g["body_pct"] < 0.10)  # green or doji-body
        and g["lower_wick"] >= 0.50
        and g["upper_wick"] <= 0.20
        and g["body_pct"] <= 0.30
    )


def _is_shooting_star(spy_bar):
    g = _bar_geometry(spy_bar["open"], spy_bar["high"], spy_bar["low"], spy_bar["close"])
    return (
        (g["is_red"] or g["body_pct"] < 0.10)
        and g["upper_wick"] >= 0.50
        and g["lower_wick"] <= 0.20
        and g["body_pct"] <= 0.30
    )


def _is_high_vol_break(spy_bar, vol_baseline, side):
    """High-conviction continuation candle for TP1 — 2x vol + 60% body in trade direction."""
    if vol_baseline <= 0 or spy_bar["volume"] < 2.0 * vol_baseline:
        return False
    g = _bar_geometry(spy_bar["open"], spy_bar["high"], spy_bar["low"], spy_bar["close"])
    if g["body_pct"] < 0.60:
        return False
    return g["is_red"] if side == "P" else g["is_green"]


def _is_round_number(level: float, tol: float = 0.05) -> bool:
    """True if level is within `tol` of a whole dollar — likely a psychological round
    number, not a chart-defined support/resistance. Per CLAUDE.md operating principle 5,
    round numbers are awareness-only, not trigger sources."""
    return abs(level - round(level)) < tol


def _next_level_past_entry(entry_spot, levels, side, max_distance=10.0,
                            min_distance=1.50, exclude_round=True):
    """First chart-defined level past entry_spot in trade direction.

    Filters out:
      - Levels too close to entry (< min_distance) — entry-bar noise
      - Round numbers ($X.00 ± 0.05) — psychological only, not chart-defined
      - Levels too far (> max_distance) — irrelevant for this trade
    """
    if not levels:
        return None
    candidates = list(levels)
    if exclude_round:
        candidates = [L for L in candidates if not _is_round_number(L)]
    if side == "P":
        below = sorted(
            [L for L in candidates
             if L < entry_spot - min_distance and entry_spot - L <= max_distance],
            reverse=True,
        )
        return below[0] if below else None
    else:
        above = sorted(
            [L for L in candidates
             if L > entry_spot + min_distance and L - entry_spot <= max_distance],
        )
        return above[0] if above else None


def _is_runner_exit_signal(spy_bar, vol_baseline, levels_carry, levels_active, side,
                            tier="conservative"):
    """3-condition stack: reversal candle + volume + at level.

    tier="conservative": volume >= 1.5x AND at any Active OR Carry level
    tier="aggressive":   volume >= 2.0x AND at Carry-tier level only
    """
    vol_mult = 1.5 if tier == "conservative" else 2.0
    if vol_baseline <= 0 or spy_bar["volume"] < vol_mult * vol_baseline:
        return False
    if side == "P":
        if not _is_hammer(spy_bar):
            return False
    else:
        if not _is_shooting_star(spy_bar):
            return False
    levels_to_check = (
        list(levels_active) + list(levels_carry) if tier == "conservative"
        else list(levels_carry)
    )
    close_px = float(spy_bar["close"])
    return any(abs(close_px - L) <= 0.30 for L in levels_to_check)


def simulate_trade_real(
    entry_bar_idx: int,
    entry_bar: pd.Series,
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    rejection_level: float,
    triggers_fired: list[str],
    side: str = "P",
    qty: int = DEFAULT_QTY,
    setup: str = "BEARISH_REJECTION_RIDE_THE_RIBBON",
    entry_slippage: float = DEFAULT_ENTRY_SLIPPAGE,
    exit_slippage: float = DEFAULT_EXIT_SLIPPAGE,
    levels_active: Optional[list[float]] = None,
    levels_carry: Optional[list[float]] = None,
    use_tiered_exits: bool = True,
    strike_override: Optional[int] = None,
    premium_stop_pct: float = -0.08,    # RATIFIED 2026-05-08 v14 — was -0.10; -8% strictly better (+$356, smaller DD)
    strike_offset: int = -2,    # RATIFIED 2026-05-07 sweep — ITM-2 (strike $2 above spot for puts)
    profit_lock_threshold_pct: float = 0.0,  # NEW 2026-05-13 T41 (parity with simulator.py): 0=off; e.g. 0.10 = arm at +10% favorable
    profit_lock_stop_offset_pct: float = 0.0,  # NEW 2026-05-13 T41: where to raise stop when armed (e.g. 0.05 = +5% above entry premium)
    profit_lock_mode: str = "fixed",  # NEW 2026-05-13 T50b: "fixed" | "trailing" | "stepped". Trailing = chandelier-style w/ trail_pct
    profit_lock_trail_pct: float = 0.0,  # NEW T50b: 0.20 = chandelier 20% off HWM (only used when mode='trailing')
    # --- REGIME-CONDITIONAL / UNDERLYING CHANDELIER (2026-06-19, vol-scaled exit) -------
    # Kim-Tse-Wald (JFE): trend-following's edge is volatility-SCALED risk management — the
    # trailing stop should WIDEN in high vol and TIGHTEN in calm so it does not choke a winner
    # during the volatile final leg. Two opt-in extensions to the v15 chandelier, BOTH default
    # OFF (byte-for-byte identical to prior behavior when unset):
    #
    #  (1) profit_lock_trail_basis: "premium" (current v15 — trail off option-premium HWM) OR
    #      "underlying" (the research's prescription — trail off the UNDERLYING SPY move; for a
    #      put the favorable extreme is the session LOW, exit when SPY rallies trail-distance
    #      back up off that low). Underlying trail is a separate all-units profit-lock exit that
    #      shares the SAME arming gate as the premium chandelier.
    #  (2) profit_lock_trail_pct_by_vix / profit_lock_trail_underlying_pct_by_vix: regime maps
    #      {vix_ceiling: trail_pct} evaluated against entry_vix (ascending ceilings; first
    #      ceiling >= entry_vix wins; falls through to the scalar trail_pct / underlying_pct).
    #      This makes the trail WIDER when entry VIX is high, TIGHTER when calm.
    #
    # entry_vix must be supplied for the regime maps to bind (the real-fills path otherwise
    # logs VIX post-hoc). When entry_vix<=0 and a map is given, the scalar fallback is used.
    profit_lock_trail_basis: str = "premium",
    profit_lock_trail_underlying_pct: float = 0.0,   # underlying trail as fraction of entry_spot, e.g. 0.004 = 0.4% of SPY
    profit_lock_trail_pct_by_vix: Optional[dict] = None,            # {vix_ceiling(float)->trail_pct(float)}
    profit_lock_trail_underlying_pct_by_vix: Optional[dict] = None,  # {vix_ceiling(float)->underlying_pct(float)}
    entry_vix: float = 0.0,
    # --- RIBBON_FLIP_PRICE_CONFIRM 2026-06-16 ---
    # When True: only exit on ribbon flip-back if SPY has also moved past entry_spot
    # (for puts: close >= entry_spot; for calls: close <= entry_spot). Prevents premature
    # exits when ribbon flips to opposite stack during noise but price is still in favor.
    # Root cause of 5/01 +$3 vs J's +$470: ribbon flipped BULL at 13:45 (10 min in)
    # while SPY was still below 722.81 entry — engine exited flat, J held to +$470.
    # Default False = existing behavior (no production impact). Ratify Rule 9 before enabling.
    ribbon_flip_price_confirm: bool = False,
    tp1_qty_fraction: float = TP1_QTY_FRACTION,           # L108 2026-06-17: was hardcoded 0.667; prod=0.50
    runner_target_premium_pct: float = RUNNER_MAX_PREMIUM_PCT,  # L109 2026-06-17: was hardcoded 3.0; prod=2.5
    tp1_premium_pct: float = TP1_PREMIUM_PCT,             # L110 2026-06-17: was hardcoded 0.30; prod=0.30 (matches, future-proof)
    time_stop_et: dt.time = TIME_STOP_ET,                  # L110 2026-06-17: was hardcoded 15:50; prod=15:50 (matches, future-proof)
    # L113 2026-06-17: level-stop chart buffer. Was hardcoded 0.50 (see comment at usage site).
    # prod=0.50. Now wirable so sweep can verify and test variations.
    level_stop_buffer_dollars: float = 0.50,
    # --- TIME-CONDITIONAL EARLY EXIT (Game Plan 2, 2026-06-19) -------------------
    # Step off the back-loaded 0DTE theta cliff (decay ~2%/hr at open -> >15%/hr after
    # 14:00, sharp drop ~15:30 ET): force-close any STAGNANT / NON-FAVORED position at
    # `early_cutoff_et`, while letting positions in strong favor ride to the existing
    # exits (chandelier / level / ribbon / 15:50 time stop). This is the AQR "let the
    # winner run, cut the laggard" shape applied to the theta clock — NOT a blanket
    # earlier guillotine.
    #
    # "In favor" at the cutoff = TP1 already filled OR current bar premium >=
    #   entry_premium * (1 + early_cutoff_min_favor_pct). If neither holds, the position
    #   is cut at market (bar.close - exit_slippage), reason EXIT_ALL_TIME_STOP.
    #
    # Default early_cutoff_et=None => OFF => byte-for-byte identical to prior behavior
    # (no production impact; opt-in only, mirrors every other knob added above). Rule 9:
    # research-only until ratified.
    early_cutoff_et: Optional[dt.time] = None,
    early_cutoff_min_favor_pct: float = 0.0,
) -> Optional[TradeFill]:
    """Simulate a bracket trade with real option fills.

    Args:
        entry_bar_idx: index in spy_df where the trigger fired (the just-closed bar).
        entry_bar: the trigger bar's row from spy_df.
        spy_df: full SPY 5-min DataFrame.
        ribbon_df: aligned ribbon DataFrame.
        rejection_level: chart level rejected on entry bar (used for level-stop check).
        triggers_fired: which filter-10 triggers contributed.
        side: "P" for puts (bearish), "C" for calls (bullish).
        qty: contracts.
        setup: setup name for the TradeFill record.

    Returns None if the option contract bars aren't cached (caller should fall back
    to BS simulator or skip the trade and report).
    """
    entry_time = entry_bar["timestamp_et"]
    # Normalize to TZ-naive Python datetime (the SPY CSV is TZ-aware -04:00)
    if hasattr(entry_time, "tz_localize"):
        if entry_time.tz is not None:
            entry_time = entry_time.tz_localize(None)
        entry_time = entry_time.to_pydatetime()
    elif hasattr(entry_time, "tzinfo") and entry_time.tzinfo is not None:
        entry_time = entry_time.replace(tzinfo=None)

    entry_spot = float(entry_bar["close"])
    if strike_override is not None:
        strike = strike_override
    else:
        # Apply strike_offset for ITM/OTM tests.
        # For puts: ITM = strike ABOVE spot; OTM = strike BELOW spot.
        # For calls: ITM = strike BELOW spot; OTM = strike ABOVE spot.
        atm = _strike_from_spot(entry_spot)
        if side == "P":
            strike = atm - strike_offset    # offset -1 → strike+1 (ITM-1 for puts)
        else:
            strike = atm + strike_offset
    symbol = option_symbol(entry_time.date(), strike, side)

    opt_df = load_contract_bars(symbol)
    if opt_df is None:
        return None  # not cached — caller decides what to do

    # Normalize option bars to TZ-naive too
    opt_df = opt_df.copy()
    if opt_df["timestamp_et"].dt.tz is not None:
        opt_df["timestamp_et"] = opt_df["timestamp_et"].dt.tz_localize(None)

    # Entry: NEXT bar after the trigger bar (no look-ahead).
    # Trigger bar timestamp = bar START. Trigger fires at bar CLOSE.
    # Earliest realistic fill = first trade of the next 5-min bar.
    next_bar_start = entry_time + dt.timedelta(minutes=5)
    entry_bar_opt = bar_at_or_after(opt_df, next_bar_start)
    if entry_bar_opt is None or entry_bar_opt.open <= 0:
        return None

    # Real broker fills the BUY at ASK. We approximate ASK as bar.open + half-spread.
    raw_open = entry_bar_opt.open
    entry_premium = raw_open + entry_slippage
    stop_premium = entry_premium * (1.0 + premium_stop_pct)   # configurable premium stop
    tp1_premium_fallback = entry_premium * (1.0 + tp1_premium_pct)     # L110: was TP1_PREMIUM_PCT hardcode
    runner_target_premium = entry_premium * (1.0 + runner_target_premium_pct)  # L109: was RUNNER_MAX_PREMIUM_PCT hardcode

    # Identify the FIRST chart-level past entry (for chart-level TP1)
    levels_active = list(levels_active or [])
    levels_carry = list(levels_carry or [])
    chart_tp1_level = _next_level_past_entry(entry_spot, levels_active + levels_carry, side)

    fill = TradeFill(
        setup=setup,
        entry_time_et=entry_time,
        entry_spot=entry_spot,
        strike=strike,
        qty=qty,
        entry_premium=entry_premium,
        entry_delta=0.0,        # no Greeks in real-fill mode (would need separate API)
        entry_iv=0.0,
        entry_vix=0.0,
        rejection_level=rejection_level,
        triggers_fired=triggers_fired,
        side=side,
    )
    fill.max_adverse_premium = entry_premium
    fill.max_favorable_premium = entry_premium

    tp1_filled = False
    runner_stop_premium = stop_premium
    # NEW 2026-05-13 T41: profit-lock parity with simulator.py. When best_premium
    # reaches entry*(1+threshold), raise stop floor to entry*(1+offset) — winners
    # never go negative. Mirrors lines 210-243 of simulator.py. Critical for
    # v14_enhanced doctrine intent which depends on profit-lock.
    profit_lock_armed = False
    profit_lock_arm_floor: Optional[float] = None  # T50b: only set when armed; trailing mode reads as min-anchor

    # Vol-scaled (regime-conditional) chandelier resolution — done once at entry (2026-06-19).
    # entry_vix is the regime key; maps fall through to the scalar knobs when unset / VIX unknown.
    eff_trail_pct = _regime_trail_pct(entry_vix, profit_lock_trail_pct_by_vix, profit_lock_trail_pct)
    eff_underlying_pct = _regime_trail_pct(
        entry_vix, profit_lock_trail_underlying_pct_by_vix, profit_lock_trail_underlying_pct)
    use_underlying_trail = (
        profit_lock_trail_basis == "underlying"
        and profit_lock_mode == "trailing"
        and eff_underlying_pct > 0
    )
    # Underlying favorable-extreme tracker (puts: lowest low; calls: highest high) and the
    # absolute SPY trail distance ($ off entry_spot * pct). Only meaningful when armed.
    underlying_extreme: Optional[float] = None
    underlying_trail_dist = entry_spot * eff_underlying_pct

    # Tier the runner allocation per CLAUDE.md operating principle 11.
    # qty=3:  tp1=2, runner=1 (single conservative)
    # qty=4:  tp1=2, runner=2 (1 conservative + 1 aggressive)
    # qty=10: tp1=6, runner=4 (2 conservative + 2 aggressive)
    tp1_qty = int(qty * tp1_qty_fraction)
    runner_qty = qty - tp1_qty
    if use_tiered_exits and runner_qty >= 2:
        aggressive_remaining = runner_qty // 2
        conservative_remaining = runner_qty - aggressive_remaining
    else:
        conservative_remaining = runner_qty
        aggressive_remaining = 0

    # Aggregate runner exit data — we record one summary "runner_exit_*"
    # but track separate exit prices for the conservative + aggressive halves
    # so the TradeFill's exit_reason tells the dominant story.
    cons_exit_premium: Optional[float] = None
    cons_exit_time = None
    aggr_exit_premium: Optional[float] = None
    aggr_exit_time = None

    # Find the option-bar index matching entry, then walk forward.
    entry_idx_opt = None
    for k in range(len(opt_df)):
        if opt_df.iloc[k]["timestamp_et"] == entry_bar_opt.timestamp_et:
            entry_idx_opt = k
            break
    if entry_idx_opt is None:
        return None

    spy_idx = entry_bar_idx + 2
    opt_idx = entry_idx_opt + 1
    fill.entry_time_et = entry_bar_opt.timestamp_et

    # 20-bar SPY volume baseline at each step for high-vol-break detection.
    # Compute on demand using a window over spy_df.
    def _vol_baseline_at(idx):
        start = max(0, idx - 20)
        if start >= idx:
            return 0.0
        return float(spy_df.iloc[start:idx]["volume"].mean())

    while opt_idx < len(opt_df) and spy_idx < len(spy_df):
        spy_bar = spy_df.iloc[spy_idx]
        spy_time = spy_bar["timestamp_et"]
        if hasattr(spy_time, "tz_localize"):
            if spy_time.tz is not None:
                spy_time = spy_time.tz_localize(None)
            spy_time = spy_time.to_pydatetime()
        elif hasattr(spy_time, "tzinfo") and spy_time.tzinfo is not None:
            spy_time = spy_time.replace(tzinfo=None)
        opt_bar = quote_at_index(opt_df, opt_idx)
        if opt_bar is None:
            opt_idx += 1
            spy_idx += 1
            continue
        if spy_time.date() != entry_time.date():
            break

        # MAE / MFE
        if opt_bar.low < fill.max_adverse_premium:
            fill.max_adverse_premium = opt_bar.low
        if opt_bar.high > fill.max_favorable_premium:
            fill.max_favorable_premium = opt_bar.high

        worst_premium = opt_bar.low
        best_premium = opt_bar.high

        # Underlying favorable-extreme tracker (puts: lowest SPY low; calls: highest SPY
        # high). Updated every bar so the underlying chandelier (if enabled) trails the
        # SPY move per Kim-Tse-Wald. No-op for the default premium basis.
        if use_underlying_trail:
            if side == "P":
                lo = float(spy_bar["low"])
                underlying_extreme = lo if underlying_extreme is None else min(underlying_extreme, lo)
            else:
                hi = float(spy_bar["high"])
                underlying_extreme = hi if underlying_extreme is None else max(underlying_extreme, hi)

        # ── Profit-lock block (T41 fixed mode + T50b trailing/stepped modes) ──
        # T50 verdict 2026-05-13: trailing mode w/ trail_pct=0.20 wins on aggregate
        # AND captures more big-day upside vs fixed +5%/+10% (which caps ride-the-
        # ribbon winners at +10%). 5/13 738C trade hypothetical: trailing 20% rides
        # to ~$4.34 (+107%) vs fixed PL stops at ~$2.23 (+6%) vs no-PL actual +159%.
        hwm = fill.max_favorable_premium  # already updated above
        if profit_lock_threshold_pct > 0:
            arm_premium = entry_premium * (1.0 + profit_lock_threshold_pct)
            if not profit_lock_armed and best_premium >= arm_premium:
                profit_lock_armed = True
                profit_lock_arm_floor = entry_premium * (1.0 + profit_lock_stop_offset_pct)
                if profit_lock_arm_floor > runner_stop_premium:
                    runner_stop_premium = profit_lock_arm_floor

            if profit_lock_armed:
                if profit_lock_mode == "fixed":
                    pass  # arm_floor already applied above; no further movement
                elif profit_lock_mode == "trailing" and not use_underlying_trail:
                    trail_floor = hwm * (1.0 - eff_trail_pct)
                    candidate = max(profit_lock_arm_floor or 0.0, trail_floor)
                    if candidate > runner_stop_premium:
                        runner_stop_premium = candidate
                elif profit_lock_mode == "stepped":
                    stepped = _stepped_floor(entry_premium, hwm)
                    if stepped is not None:
                        candidate = max(profit_lock_arm_floor or 0.0, stepped)
                        if candidate > runner_stop_premium:
                            runner_stop_premium = candidate
        elif profit_lock_mode in ("trailing", "stepped"):
            # Allow trailing/stepped without explicit arm threshold — useful for
            # pure-trail variants. Arm at first profitable bar, anchor at break-even.
            if not profit_lock_armed and best_premium > entry_premium:
                profit_lock_armed = True
                profit_lock_arm_floor = entry_premium  # BE anchor
            if profit_lock_armed:
                if profit_lock_mode == "trailing" and not use_underlying_trail:
                    trail_floor = hwm * (1.0 - eff_trail_pct)
                    candidate = max(profit_lock_arm_floor or 0.0, trail_floor)
                    if candidate > runner_stop_premium:
                        runner_stop_premium = candidate
                elif profit_lock_mode == "stepped":
                    stepped = _stepped_floor(entry_premium, hwm)
                    if stepped is not None and stepped > runner_stop_premium:
                        runner_stop_premium = stepped
        # ── /profit-lock block ──────────────────────────────────────────────────

        # ── UNDERLYING CHANDELIER exit (2026-06-19, vol-scaled per Kim-Tse-Wald) ──
        # When trail_basis="underlying", trail the SPY MOVE not the option premium: once
        # the profit-lock is armed, exit ALL remaining units when SPY retraces
        # `underlying_trail_dist` ($ = entry_spot * eff_underlying_pct) off the favorable
        # extreme (puts: rally back up off the session low; calls: drop off the high).
        # OFF unless use_underlying_trail (basis='underlying' + mode='trailing' + pct>0) —
        # no production impact. Evaluated before the premium/time/level/ribbon exits below
        # so the underlying trail is the governing profit-lock when enabled.
        if use_underlying_trail and profit_lock_armed and underlying_extreme is not None:
            if side == "P":
                trail_trigger = underlying_extreme + underlying_trail_dist
                underlying_retraced = float(spy_bar["high"]) >= trail_trigger
            else:
                trail_trigger = underlying_extreme - underlying_trail_dist
                underlying_retraced = float(spy_bar["low"]) <= trail_trigger
            if underlying_retraced:
                exit_px = max(0.01, opt_bar.close - exit_slippage)
                fill.runner_exit_time_et = spy_time
                fill.runner_exit_premium = exit_px
                fill.exit_reason = (ExitReason.TP1_THEN_RUNNER_TIME if tp1_filled
                                    else ExitReason.EXIT_ALL_PREMIUM_STOP)
                break

        time_stop_now = spy_time.time() >= time_stop_et
        vol_baseline = _vol_baseline_at(spy_idx)

        # ── TIME-CONDITIONAL EARLY EXIT (Game Plan 2) ───────────────────
        # Cut STAGNANT / NON-FAVORED positions at the cutoff to step off the
        # theta cliff; let in-favor positions ride to the normal exits. OFF when
        # early_cutoff_et is None (default) — no production impact. Evaluated
        # BEFORE the 15:50 time stop so a 15:00/15:15/15:30 cutoff binds first;
        # it never fires AT/after the hard time stop (that path already exits).
        if early_cutoff_et is not None and not time_stop_now and spy_time.time() >= early_cutoff_et:
            # In favor = TP1 already banked OR this bar's premium has reached the
            # favor threshold above entry. best_premium = current bar high (the
            # generous read — only genuinely stagnant positions get cut).
            in_favor = tp1_filled or (
                best_premium >= entry_premium * (1.0 + early_cutoff_min_favor_pct)
            )
            if not in_favor:
                # Force-close everything still open at market. Mirrors the pre/post-TP1
                # time-stop fill convention (bar.close minus exit slippage).
                exit_px = max(0.01, opt_bar.close - exit_slippage)
                if not tp1_filled:
                    fill.runner_exit_time_et = spy_time
                    fill.runner_exit_premium = exit_px
                    fill.exit_reason = ExitReason.EXIT_ALL_TIME_STOP
                else:
                    # TP1 already filled means in_favor=True, so this branch is
                    # unreachable; kept defensive for clarity.
                    fill.runner_exit_time_et = spy_time
                    fill.runner_exit_premium = exit_px
                    fill.exit_reason = ExitReason.TP1_THEN_RUNNER_TIME
                break

        # ── Pre-TP1 hard exits (apply to all units before TP1) ──────────
        if not tp1_filled:
            # Premium stop -50% → exit all
            if worst_premium <= runner_stop_premium:
                fill.runner_exit_time_et = spy_time
                fill.runner_exit_premium = runner_stop_premium
                fill.exit_reason = ExitReason.EXIT_ALL_PREMIUM_STOP
                break

            # Time stop pre-TP1 → exit all at market
            if time_stop_now:
                fill.runner_exit_time_et = spy_time
                fill.runner_exit_premium = max(0.01, opt_bar.close - exit_slippage)
                fill.exit_reason = ExitReason.EXIT_ALL_TIME_STOP
                break

            # Ribbon flip back → exit all at market.
            # REVISED 2026-05-07: stack inversion alone catches noise; close>Slow alone
            # catches small overshoots. The right rule is OPPOSITE-STACK + spread >= 30c.
            # Same 30c threshold filter 6 uses for entry — sub-30c is chop, no real
            # bias. On 5/1 the stack went BEAR→MIXED→BEAR while spread compressed to
            # 24c; J's TV showed the same chop but he correctly held. The opposite-side
            # full stack at 30c spread = real invalidation: bulls (for puts) have
            # taken control with conviction.
            ribbon_state = _ribbon_at(ribbon_df, spy_idx)
            opposite_stack = "BULL" if side == "P" else "BEAR"
            spy_close_now = float(spy_bar["close"])
            # Buffer matches LEVEL_STOP_BUFFER (0.50): ribbon flip-back can only fire
            # once SPY has moved $0.50 past entry — prevents premature exit on
            # 5/01-style congestion (722.84 vs 722.81 entry, just $0.03 above).
            RIBBON_FLIP_PRICE_BUFFER = 0.50
            price_reversal_confirmed = (
                (side == "P" and spy_close_now >= entry_spot + RIBBON_FLIP_PRICE_BUFFER)
                or (side == "C" and spy_close_now <= entry_spot - RIBBON_FLIP_PRICE_BUFFER)
            )
            if (
                ribbon_state is not None
                and ribbon_state.stack == opposite_stack
                and ribbon_state.spread_cents >= 30.0
                and (not ribbon_flip_price_confirm or price_reversal_confirmed)
            ):
                fill.runner_exit_time_et = spy_time
                fill.runner_exit_premium = max(0.01, opt_bar.close - exit_slippage)
                fill.exit_reason = ExitReason.EXIT_ALL_RIBBON_FLIP_BACK
                break

            # Level stop — moderate buffer ($0.50) without ribbon condition.
            # Tradeoff resolution after testing 2026-05-07:
            #   - Tight (<= $0.10): kills J's 4/29-style trades that drift $0.50 on
            #     conviction-test bars before the move launches.
            #   - Loose ($0.50): J-quality entries pass through; engine bad-entry
            #     trades hit deeper losses (-50% premium stop) without this safety net.
            #   - $0.50 + ribbon-condition: too restrictive — fails the J replay test.
            # $0.50 buffer alone is the middle ground. If R-BT-08 (entry timing)
            # closes the bad-entry gap, we can drop this.
            # Guard None rejection_level (entry from ribbon_flip-only trigger)
            level_breached = (
                rejection_level is not None
                and (
                    (side == "P" and float(spy_bar["close"]) > rejection_level + level_stop_buffer_dollars)
                    or (side == "C" and float(spy_bar["close"]) < rejection_level - level_stop_buffer_dollars)
                )
            )
            if level_breached:
                fill.runner_exit_time_et = spy_time
                fill.runner_exit_premium = max(0.01, opt_bar.close - exit_slippage)
                fill.exit_reason = ExitReason.EXIT_ALL_LEVEL_STOP
                break

            # ── NEW TP1 logic ────────────────────────────────────────────
            # Per CLAUDE.md operating principle 11: TP1 fires on chart-level
            # reach OR premium fallback. Vol-break alone is NOT a TP1 trigger
            # (it can happen mid-trend before price has actually moved).
            # Vol-break could be a tightening signal at the level — but for
            # simplicity we keep TP1 to two clean triggers.
            tp1_fire_reason = None
            tp1_fire_premium = None

            # (A) Chart-level TP1 — SPY price hit the next chart-defined level past entry
            if chart_tp1_level is not None:
                hit_level = (
                    (side == "P" and float(spy_bar["low"]) <= chart_tp1_level + 0.30)
                    or (side == "C" and float(spy_bar["high"]) >= chart_tp1_level - 0.30)
                )
                if hit_level:
                    tp1_fire_reason = "chart_level"
                    tp1_fire_premium = max(0.01, opt_bar.close - exit_slippage)

            # (B) Premium fallback +30% — for slow days where price never hits a level
            if tp1_fire_reason is None and best_premium >= tp1_premium_fallback:
                tp1_fire_reason = "premium_fallback"
                tp1_fire_premium = tp1_premium_fallback

            if tp1_fire_reason is not None:
                tp1_filled = True
                fill.tp1_time_et = spy_time
                fill.tp1_premium = tp1_fire_premium
                runner_stop_premium = entry_premium  # BE stop on runners
                # Skip same-bar runner-exit checks
                spy_idx += 1
                opt_idx += 1
                continue

            spy_idx += 1
            opt_idx += 1
            continue

        # ── Post-TP1: runner exits, tier by tier ────────────────────────
        # Same revised ribbon rule: opposite stack + spread >= 30c.
        # Stack alone flickers MIXED on chop; this requires real conviction.
        ribbon_state = _ribbon_at(ribbon_df, spy_idx)
        opposite_stack = "BULL" if side == "P" else "BEAR"
        ribbon_invalidated = (
            ribbon_state is not None
            and ribbon_state.stack == opposite_stack
            and ribbon_state.spread_cents >= 30.0
        )

        # Conservative runner exit triggers (priority order):
        if conservative_remaining > 0:
            cons_exit_now = False
            cons_price = None
            # Reversal candle + 1.5x vol + at any Active/Carry level
            if _is_runner_exit_signal(spy_bar, vol_baseline, levels_carry, levels_active,
                                       side, tier="conservative"):
                cons_exit_now = True
                cons_price = max(0.01, opt_bar.close - exit_slippage)
            # Ribbon flip back
            elif ribbon_invalidated:
                cons_exit_now = True
                cons_price = max(0.01, opt_bar.close - exit_slippage)
            # BE stop hit
            elif worst_premium <= runner_stop_premium:
                cons_exit_now = True
                cons_price = runner_stop_premium
            # Time stop
            elif time_stop_now:
                cons_exit_now = True
                cons_price = max(0.01, opt_bar.close - exit_slippage)

            if cons_exit_now:
                cons_exit_premium = cons_price
                cons_exit_time = spy_time
                conservative_remaining = 0

        # Aggressive runner exit triggers (Carry level only, 2x vol)
        if aggressive_remaining > 0:
            aggr_exit_now = False
            aggr_price = None
            if _is_runner_exit_signal(spy_bar, vol_baseline, levels_carry, levels_active,
                                       side, tier="aggressive"):
                aggr_exit_now = True
                aggr_price = max(0.01, opt_bar.close - exit_slippage)
            elif ribbon_invalidated:
                aggr_exit_now = True
                aggr_price = max(0.01, opt_bar.close - exit_slippage)
            elif best_premium >= runner_target_premium:
                aggr_exit_now = True
                aggr_price = runner_target_premium
            elif worst_premium <= runner_stop_premium:
                aggr_exit_now = True
                aggr_price = runner_stop_premium
            elif time_stop_now:
                aggr_exit_now = True
                aggr_price = max(0.01, opt_bar.close - exit_slippage)

            if aggr_exit_now:
                aggr_exit_premium = aggr_price
                aggr_exit_time = spy_time
                aggressive_remaining = 0

        # Both runners closed → exit loop
        if conservative_remaining == 0 and aggressive_remaining == 0:
            # Determine the dominant exit reason for the TradeFill record
            if cons_exit_premium is not None and aggr_exit_premium is not None:
                # Use the LATER of the two exits as the "runner exit time"
                fill.runner_exit_time_et = max(cons_exit_time, aggr_exit_time)
                # Weighted-average exit premium for reporting
                cons_qty_n = max(1, runner_qty // 2 if use_tiered_exits and runner_qty >= 2 else runner_qty)
                aggr_qty_n = max(0, runner_qty - cons_qty_n)
                if aggr_qty_n > 0:
                    fill.runner_exit_premium = (
                        (cons_exit_premium * cons_qty_n + aggr_exit_premium * aggr_qty_n)
                        / (cons_qty_n + aggr_qty_n)
                    )
                else:
                    fill.runner_exit_premium = cons_exit_premium
            else:
                fill.runner_exit_time_et = cons_exit_time or aggr_exit_time
                fill.runner_exit_premium = cons_exit_premium or aggr_exit_premium
            # Reason: choose based on conditions present
            if ribbon_invalidated:
                fill.exit_reason = ExitReason.TP1_THEN_RUNNER_RIBBON
            elif time_stop_now:
                fill.exit_reason = ExitReason.TP1_THEN_RUNNER_TIME
            elif aggr_exit_premium is not None and aggr_exit_premium >= runner_target_premium - 0.01:
                fill.exit_reason = ExitReason.TP1_THEN_RUNNER_TARGET
            else:
                fill.exit_reason = ExitReason.TP1_THEN_RUNNER_RIBBON  # signal-driven exit
            break

        spy_idx += 1
        opt_idx += 1

    # Loop fell through (rare)
    if fill.exit_reason is None:
        last_idx = min(opt_idx, len(opt_df) - 1)
        last_opt = quote_at_index(opt_df, last_idx)
        last_spy_idx = min(spy_idx, len(spy_df) - 1)
        last_spy_time = spy_df.iloc[last_spy_idx]["timestamp_et"]
        fill.runner_exit_time_et = last_spy_time
        fill.runner_exit_premium = (
            max(0.01, last_opt.close - exit_slippage) if last_opt
            else entry_premium * 0.5
        )
        fill.exit_reason = ExitReason.EXIT_ALL_TIME_STOP

    fill.dollar_pnl = _compute_pnl(fill, qty, tp1_qty_fraction=tp1_qty_fraction)
    fill.pct_return_on_premium = (
        fill.dollar_pnl / (entry_premium * qty * 100.0) if entry_premium > 0 else 0.0
    )
    if fill.runner_exit_time_et:
        exit_t = fill.runner_exit_time_et
        # Normalize to tz-naive (entry_time was already normalized to tz-naive above)
        if hasattr(exit_t, "tz_localize") and exit_t.tz is not None:
            exit_t = exit_t.tz_localize(None).to_pydatetime()
        elif hasattr(exit_t, "tzinfo") and exit_t.tzinfo is not None:
            exit_t = exit_t.replace(tzinfo=None)
        delta_min = (exit_t - entry_time).total_seconds() / 60.0
        fill.hold_minutes = int(round(delta_min))
        fill.bars_held = int(round(delta_min / 5.0))
    return fill


def _compute_pnl(fill: TradeFill, qty: int, tp1_qty_fraction: float = TP1_QTY_FRACTION) -> float:
    """TP1 partial-out math.

    runner_exit_premium is the WEIGHTED AVERAGE across conservative + aggressive
    runners (when tiered) — see simulate_trade_real for the weighting.
    """
    if fill.runner_exit_premium is None:
        return 0.0
    if fill.tp1_filled():
        tp1_qty = int(qty * tp1_qty_fraction)
        runner_qty = qty - tp1_qty
        tp1_pnl = (fill.tp1_premium - fill.entry_premium) * tp1_qty * 100.0
        runner_pnl = (fill.runner_exit_premium - fill.entry_premium) * runner_qty * 100.0
        return tp1_pnl + runner_pnl
    return (fill.runner_exit_premium - fill.entry_premium) * qty * 100.0
