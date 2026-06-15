"""ERL -> IRL watcher — liquidity-sweep into Fair-Value-Gap entry (Reddit ICT adoption).

Source: J-supplied post (r/FuturesTradingNQ, 2026-06-14). The author's second setup:
  "Price swept a key low (ERL), displaced into a fair value gap (IRL), and I entered the
   FVG ... looking for the expansion back toward buyside liquidity."

ERL = External Range Liquidity (stops resting beyond a key high/low — our named levels).
IRL = Internal Range Liquidity (the Fair Value Gap left by the displacement candle).

Mechanic (bullish; bearish mirrors):
  1. ERL sweep:    price wicks below a key SUPPORT level (grabs sellside liquidity) and reclaims.
  2. Displacement: a strong up-move off the sweep prints a bullish FVG (filters.detect_fvg).
  3. IRL entry:    price retraces INTO the FVG zone and holds (closes back above the gap floor).
  4. Target:       the next external level above entry (buyside liquidity). Stop: below the swept low.

0DTE adaptations (NON-NEGOTIABLE — futures edge dies at ATM otherwise):
  - Intraday-compressed only (5-min bars), NEVER the multi-hour swing the post held 5h26m.
  - ITM-2 strikes + chart-stop only: premium_stop=-0.99 (L51/L55/L74 — retrace-into-gap entries
    suffer the same first-bounce premium-stop misfire as level-reclaim entries; ATM 0DTE fails
    real-fills per L74). strike_offset=-2 is the production config to validate.
  - Regime: edge concentrates in trending high-vol (L73/L74). VIX is LOGGED for stratification,
    not hard-gated, so observations accumulate across regimes (matches new-watcher protocol).

Watch-only: does NOT place trades. Promotion requires OP-21 (N>=15 historical + walk-forward +
real-fills + 3 live J confirmations) + Rule 9 ratification.

Author: Gamma (interactive session 2026-06-14). Spec:
  strategy/candidates/2026-06-14-reddit-orb15-and-erl-irl-fvg-adoption.md
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..filters import detect_fvg, FVG


# ---- Thresholds ----
ENTRY_TIME_START: dt.time = dt.time(9, 45)   # need post-open structure (a sweep + displacement)
ENTRY_TIME_END: dt.time = dt.time(15, 0)     # intraday only; engine is flat by 15:50
SCAN_WINDOW_BARS: int = 12                    # look-back for the sweep->FVG->retrace sequence
SWEEP_LOOKBACK_BARS: int = 4                  # sweep must be at/just before the displacement
MIN_FVG_GAP_DOLLARS: float = 0.10             # displacement-strength floor
SWEEP_WICK_MIN: float = 0.10                  # level must be pierced by >= 10c (a real liquidity grab)
LEVEL_NEAR_GAP_DOLLARS: float = 0.75          # swept level must sit near/below the gap floor
GAP_RETRACE_TOL: float = 0.05                 # entry bar may undershoot gap floor by this much
STOP_BUFFER: float = 0.10                     # chart stop = swept extreme +/- this buffer
TP1_FALLBACK: float = 1.00                    # SPY-space TP1 if no external level beyond entry
RUNNER_FALLBACK: float = 2.50                 # SPY-space runner (v15 2.5x knob)

# ---- Default exit knobs (validated config goes to params on ratification) ----
DEFAULT_PREMIUM_STOP_PCT: float = -0.99       # chart-stop only (L51/L55/L74)
DEFAULT_STRIKE_OFFSET: int = -2               # ITM-2 (L74 ATM-fail rescue)
DEFAULT_QTY: int = 3


def _candidate_supports(levels_active, ref_price, side):
    """Levels eligible as the swept ERL: supports below ref (bullish) / resistances above (bearish)."""
    if side == "bullish":
        return [L for L in levels_active if L <= ref_price + LEVEL_NEAR_GAP_DOLLARS]
    return [L for L in levels_active if L >= ref_price - LEVEL_NEAR_GAP_DOLLARS]


def _find_sweep(prior_bars, lo_idx, hi_idx, levels, side, trigger_close):
    """Return (swept_level, swept_extreme) if a liquidity grab + reclaim occurred in [lo,hi]."""
    best = None
    for L in levels:
        for k in range(max(0, lo_idx), min(hi_idx + 1, len(prior_bars))):
            b = prior_bars.iloc[k]
            if side == "bullish":
                # wick pierced BELOW the support and price has reclaimed above it by trigger
                if float(b["low"]) < L - SWEEP_WICK_MIN and trigger_close > L:
                    lo = float(b["low"])
                    if best is None or lo < best[1]:
                        best = (L, lo)
            else:
                if float(b["high"]) > L + SWEEP_WICK_MIN and trigger_close < L:
                    hi = float(b["high"])
                    if best is None or hi > best[1]:
                        best = (L, hi)
    return best


def _next_external_targets(levels_active, entry, side):
    """tp1/runner from the nearest external levels beyond entry (buyside/sellside liquidity)."""
    if side == "bullish":
        above = sorted(L for L in levels_active if L > entry + 0.10)
        tp1 = above[0] if above else entry + TP1_FALLBACK
        runner = above[1] if len(above) > 1 else max(tp1 + 0.50, entry + RUNNER_FALLBACK)
    else:
        below = sorted((L for L in levels_active if L < entry - 0.10), reverse=True)
        tp1 = below[0] if below else entry - TP1_FALLBACK
        runner = below[1] if len(below) > 1 else min(tp1 - 0.50, entry - RUNNER_FALLBACK)
    return float(tp1), float(runner)


def detect_erl_irl(
    prior_bars: pd.DataFrame,
    bar_idx: int,
    levels_active: list,
    vix_now: float = 0.0,
    htf_15m_stack: Optional[str] = None,
) -> Optional[dict]:
    """Pure detector (no WatcherSignal dependency) — returns a result dict or None.

    Scans [bar_idx - SCAN_WINDOW_BARS, bar_idx-1] for a fresh FVG, confirms an ERL sweep
    fed the displacement, and confirms the trigger bar (bar_idx) retraced into the gap and held.
    """
    if bar_idx < 4 or bar_idx >= len(prior_bars) or not levels_active:
        return None
    trig = prior_bars.iloc[bar_idx]
    t_open, t_high = float(trig["open"]), float(trig["high"])
    t_low, t_close = float(trig["low"]), float(trig["close"])

    for side, want_bull in (("bullish", True), ("bearish", False)):
        # 1) most-recent fresh FVG in the window (formed before the trigger bar)
        lo_j = max(2, bar_idx - SCAN_WINDOW_BARS)
        fvg: Optional[FVG] = None
        for j in range(bar_idx - 1, lo_j - 1, -1):
            cand = detect_fvg(prior_bars, j, side, MIN_FVG_GAP_DOLLARS)
            if cand is not None:
                fvg = cand
                break
        if fvg is None:
            continue

        # 2) trigger bar must retrace INTO the gap and hold (bullish: dip to gap, close back above floor + green)
        if want_bull:
            entered_gap = t_low <= fvg.gap_top and t_low >= fvg.gap_bottom - GAP_RETRACE_TOL
            held = t_close >= fvg.gap_bottom and t_close > t_open
        else:
            entered_gap = t_high >= fvg.gap_bottom and t_high <= fvg.gap_top + GAP_RETRACE_TOL
            held = t_close <= fvg.gap_top and t_close < t_open
        if not (entered_gap and held):
            continue

        # 3) ERL sweep fed the displacement (at/just before the FVG formation bar)
        sweep = _find_sweep(
            prior_bars,
            fvg.formed_at_idx - SWEEP_LOOKBACK_BARS,
            fvg.formed_at_idx,
            _candidate_supports(levels_active, fvg.gap_bottom if want_bull else fvg.gap_top, side),
            side,
            t_close,
        )
        if sweep is None:
            continue
        swept_level, swept_extreme = sweep

        # 4) build entry/stop/targets
        entry = t_close
        if want_bull:
            stop = swept_extreme - STOP_BUFFER
            direction = "long"
        else:
            stop = swept_extreme + STOP_BUFFER
            direction = "short"
        tp1, runner = _next_external_targets(levels_active, entry, side)

        # confidence: displacement strength + VIX regime (trending high-vol = best per L73/L74)
        gap_tier = fvg.gap_size
        vix_trending = vix_now >= 18.0
        if gap_tier >= 0.40 and vix_trending:
            confidence = "high"
        elif gap_tier >= 0.20 or vix_trending:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "direction": direction,
            "entry": float(entry),
            "stop": float(stop),
            "tp1": float(tp1),
            "runner": float(runner),
            "confidence": confidence,
            "fvg": fvg,
            "swept_level": float(swept_level),
            "swept_extreme": float(swept_extreme),
            "vix_now": float(vix_now),
            "htf_15m_stack": htf_15m_stack,
        }
    return None


def detect_erl_irl_setup(ctx) -> Optional[WatcherSignal]:
    """BarContext wrapper. Watch-only. Returns a WatcherSignal or None."""
    bar_t = ctx.timestamp_et.time()
    if bar_t < ENTRY_TIME_START or bar_t > ENTRY_TIME_END:
        return None

    res = detect_erl_irl(
        prior_bars=ctx.prior_bars,
        bar_idx=ctx.bar_idx,
        levels_active=list(ctx.levels_active or []),
        vix_now=float(getattr(ctx, "vix_now", 0.0) or 0.0),
        htf_15m_stack=getattr(ctx, "htf_15m_stack", None),
    )
    if res is None:
        return None

    fvg: FVG = res["fvg"]
    reason = (
        f"ERL->IRL {res['direction']}: swept {res['swept_level']:.2f} "
        f"(grab @ {res['swept_extreme']:.2f}) -> {fvg.direction} FVG "
        f"[{fvg.gap_bottom:.2f},{fvg.gap_top:.2f}] gap={fvg.gap_size:.2f} -> retrace entry "
        f"{res['entry']:.2f}, target {res['tp1']:.2f}, vix={res['vix_now']:.1f}"
    )
    return WatcherSignal(
        watcher_name="erl_irl_watcher",
        setup_name="ERL_IRL_SWEEP_FVG",
        direction=res["direction"],
        entry_price=res["entry"],
        stop_price=res["stop"],
        tp1_price=res["tp1"],
        runner_price=res["runner"],
        confidence=res["confidence"],
        reason=reason,
        triggers_fired=["ERL_SWEEP", "IRL_FVG_DISPLACEMENT", "FVG_RETRACE_HELD"],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "fvg_direction": fvg.direction,
            "fvg_gap_bottom": fvg.gap_bottom,
            "fvg_gap_top": fvg.gap_top,
            "fvg_gap_size": fvg.gap_size,
            "swept_level": res["swept_level"],
            "swept_extreme": res["swept_extreme"],
            "vix_now": res["vix_now"],
            "htf_15m_stack": res["htf_15m_stack"],
            "premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "strike_offset": DEFAULT_STRIKE_OFFSET,
            "default_qty": DEFAULT_QTY,
            "op21_live_confirmed": 0, "op21_live_required": 3,
            "spec_file": "strategy/candidates/2026-06-14-reddit-orb15-and-erl-irl-fvg-adoption.md",
        },
    )
