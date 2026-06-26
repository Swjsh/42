"""DTE x STOP-CONSTRUCTION MATRIX — the lever the diagonal failure surfaced.

THE FINDING that motivates this (analysis/recommendations/dte-expansion.json + the diagonal
note): edge #1 vwap_continuation at 1DTE adds ~+$23/tr OOS (theta-room, held_overnight 0% on
the live tier) but its maxDD DOUBLES (-$939 -> -$1944) for ONE reason only — the live -8%
PERCENT stop, applied to the BIGGER 1DTE premium, is a BIGGER DOLLAR loss per stop-out. Every
prior DTE test used the -8% percent stop. The unexplored lever is the STOP CONSTRUCTION.

THE HYPOTHESIS: a stop that caps the DOLLAR loss (not the percent) at the 0DTE level should
kill the maxDD-doubling, turning the +$23/tr lift into a CLEAN win (same downside dollars, more
upside from gentler theta). The interaction is real and asymmetric: chart-stop-only was BAD at
0DTE (8x deeper maxDD — the -8% truncation IS the 0DTE risk management; recency stop-variant A/B)
but may be VIABLE at 1-2DTE (the option retains value at a structural-stop exit instead of being
annihilated by same-day theta). So we test the DTE x STOP MATRIX, not stops in isolation.

THE 4 STOP CONSTRUCTIONS (each applied at 0/1/2 DTE):
  (a) PERCENT (-8%)        — the live default. Premium stop = entry*(1 - 0.08). [BASELINE]
  (b) DOLLAR-ANCHORED      — exit when the position's DOLLAR loss hits a fixed $ threshold.
                             The threshold is CALIBRATED = the 0DTE MEDIAN per-trade dollar
                             loss at the live tier (computed from the 0DTE -8% run), then the
                             SAME $ threshold is applied at 1DTE and 2DTE. Caps the realized
                             loss at ~the threshold regardless of the bigger 1DTE premium.
  (c) CHART/LEVEL          — a PRICE stop only: exit when SPY closes past the structural
                             rejection_level (+/- buffer). The SAME underlying move triggers it
                             at any DTE -> at 1-2DTE the option still holds value at that bar
                             (pure upside vs the annihilated 0DTE). Premium stop disabled.
  (d) PERCENT-SCALED       — per-DTE percent set so the EXPECTED dollar-loss == the 0DTE
                             dollar-loss: pct_dte = -0.08 * (median_0dte_entry_premium /
                             median_dte_entry_premium). Reproduces exactly -8% at 0DTE.

CLEAN-WIN BAR (a 1DTE/2DTE cell with a stop construction): (1) keeps materially MORE OOS
dollars than the 0DTE -8% baseline at the same tier (the lift survives), (2) maxDD not
materially worse than 0DTE's -8% baseline (within MAXDD_MATERIAL_WORSEN_PCT, ~15-25%),
(3) book Sortino >= 0DTE -8% baseline's, (4) clears the canonical structural bar (incl L173
OOS-alone drop-top5), (5) worst day inside the per-account kill switch. HONEST: a tighter
dollar/percent stop may stop out MORE often (cutting the lift like the diagonal did) — the
matrix quantifies the NET; the chart-stop may or may not transfer to 1DTE (it failed at 0DTE).

WHAT THIS REUSES BYTE-FOR-BYTE (Sunday SAFE-research guard — NO watcher / params / risk_gate /
orchestrator / heartbeat / simulator_real edits, NO orders, NO commit; RESEARCH SIM ONLY):
  - the VALIDATED DTE sim machinery from _dte_expansion_sim: the per-DTE OPRA loader
    (load_dte_contract_bars / _bar_at_or_after / _quote_at_index), the expiry index
    (_build_expiry_index / _expiry_for_entry / _nearest_cached_strike_dte), the SPY
    open/close lookup + sessions-between (overnight gap + expiry settlement), DteFill,
    the metrics + L173 concentration gates + clears_bar, and the family registry.
  - the #1 detector byte-for-byte (FAMILIES["vwap_continuation"] = _edgehunt_vwap_continuation).
  - the L175 risk-adjusted machinery (per_trade_dist / book_risk / MAXDD_MATERIAL_WORSEN_PCT)
    from _b10_exit_variance — same gate the recency stop-variant A/B used.

The ONLY new code is the GENERALIZED day-T management loop (simulate_dte_trade_stop) that swaps
the single premium-percent check for a pluggable stop construction. Its day-T fill conventions,
overnight gap, and expiry settlement are copied LINE-FOR-LINE from _dte_expansion_sim.simulate_dte_trade
(the divergence is only WHICH stop fires) so fills do not drift (C14).

Pure Python, $0. No live orders. Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_dte_stop_construction.py [--smoke] [--validate]
  [--family vwap_continuation] [--tier ITM-2|ATM|...]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Reuse the VALIDATED DTE sim machinery byte-for-byte (loader, expiry index, settlement,
# metrics, gates, families). Only the day-T stop check is generalized below.
from autoresearch import _dte_expansion_sim as base  # noqa: E402
from autoresearch._dte_expansion_sim import (  # noqa: E402
    DteFill,
    DTE_DIRS,
    QTY,
    OOS_YEAR,
    DEFAULT_ENTRY_SLIPPAGE,
    DEFAULT_EXIT_SLIPPAGE,
    load_dte_contract_bars,
    _bar_at_or_after,
    _quote_at_index,
    _nearest_cached_strike_dte,
    _build_expiry_index,
    _expiry_for_entry,
    _spy_day_open_close,
    _sessions_between,
    metrics as dte_metrics,
    clears_bar,
    FAMILIES,
)
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _strike_from_spot,
    Signal,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
)
# Edge #4 vix_regime_dayside — byte-for-byte detector + VIX prep + chart-stop, reused verbatim
# (NO edits to _b5_vix_regime_dayside). The harness only ADAPTS its OptSig output into the
# uniform Signal shape the DTE sim consumes; the detector body, the VIX-regime classification,
# the day-trend-side selection, and the swing chart-stop are all untouched.
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    detect_opt_signals as _detect_vix_regime_dayside,
    causal_vix_median as _vix_causal_median,
    vix_slope as _vix_slope,
    _swing_stop as _vix_swing_stop,
    VIX_MEDIAN_BARS as _VIX_MEDIAN_BARS,
    VIX_SLOPE_BARS as _VIX_SLOPE_BARS,
)
# L175 risk-adjusted machinery (same as the recency stop-variant A/B).
from autoresearch._b10_exit_variance import (  # noqa: E402
    per_trade_dist,
    book_risk,
    MAXDD_MATERIAL_WORSEN_PCT,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.option_pricing_real import option_symbol  # noqa: E402
# The order-ADMISSION layer (the graduated cap). The realizable book is the cap-aware
# default; a caller can pass enforce_cap=False for the OLD cap-blind book (comparison only).
from lib.cap_admission import admit_book, AdmissionResult  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "dte-stop-construction.json"

# Strike tiers (neg=ITM, pos=OTM — verified in _dte_expansion_sim). Live #1 tier = ITM-2.
# OTM-1/-2 added for the affordable-survivor validation: a CHEAPER strike fits the per-account
# notional cap (Safe $600 / Bold $824) at 1DTE where the ITM/ATM tiers are blocked >90%.
TIERS = {"OTM-2": 2, "OTM-1": 1, "ATM": 0, "ITM-1": -1, "ITM-2": -2}
LIVE_TIER = "ITM-2"           # vwap_continuation lives ITM-2 / -8% (CLAUDE.md account context)
DTES = (0, 1, 2)
TP1_PREMIUM_PCT = 0.30        # v15 fallback target (same as the base sim)
BASELINE_PCT = -0.08          # the live percent stop

# Per-account kill switches (CLAUDE.md): Safe-2 -30% of $2K start = -$600/day; Bold -50% of
# ~$1.67K = ~-$835/day. The worst-day check uses the Bold limit for the aggressive ITM-2 tier
# but we report against BOTH so the verdict states which account the cell is safe for.
KILL_SWITCH = {"safe": -600.0, "bold": -835.0}

# ── EDGE #4 vix_regime_dayside — the ROBUST CLEARING config (from the b5 scorecard's
#    robust_clearing_cell: largest-OOS-N (cell,tier) that clears all 8 gates). Pinned here so
#    this harness reproduces the exact dormant edge (ATM Safe-2). Fallback matches _b9_portfolio.
VIX_REGIME_ROBUST = {"slope_rule": "not_rising", "low_margin": 0.25}
VIX_REGIME_LIVE_TIER = "ATM"   # #4 is ATM-only (Safe-2); CLAUDE.md account context


def _b5_robust_config() -> dict:
    """Read the b5 scorecard's robust_clearing_cell (slope_rule + low_margin), exactly as
    _b9_portfolio does, so we pin #4 at the SAME config the dormant edge is defined at.
    Falls back to VIX_REGIME_ROBUST if the scorecard is unavailable."""
    b5_path = ROOT / "analysis" / "recommendations" / "b5-vix-regime-dayside.json"
    try:
        b5 = json.loads(b5_path.read_text(encoding="utf-8"))
        rb = b5.get("headline", {}).get("robust_clearing_cell")
        if rb and rb.get("slope_rule") is not None and rb.get("low_margin") is not None:
            return {"slope_rule": rb["slope_rule"], "low_margin": rb["low_margin"],
                    "source": "b5 robust_clearing_cell"}
    except (OSError, ValueError, KeyError):
        pass
    return {**VIX_REGIME_ROBUST, "source": "default (b5 robust cell unavailable)"}


def _detect_vix_regime_dayside_family(days, vix, spy, ribbon=None):
    """Family adapter for #4 vix_regime_dayside. Reconstructs the VIX regime feed (B2 pinned
    reconstruction: causal trailing median + 5-bar slope) from the aligned VIX, runs the
    BYTE-FOR-BYTE #4 detector at its robust config (slope_rule/low_margin from the b5
    scorecard), and re-shapes each OptSig(gidx, date, side) into the uniform Signal the DTE
    sim consumes — with stop_level = the SAME 12-bar swing chart-stop the live #4 uses
    (_b5._swing_stop, verbatim). No edits to the detector, the VIX prep, or the chart-stop."""
    vix_g = np.asarray(vix, dtype=float)
    vix_med_g = _vix_causal_median(vix_g, _VIX_MEDIAN_BARS)
    vix_slp_g = _vix_slope(vix_g, _VIX_SLOPE_BARS)
    cfg = _b5_robust_config()
    opt_sigs = _detect_vix_regime_dayside(
        days, spy, vix_g, vix_med_g, vix_slp_g, cfg["low_margin"], cfg["slope_rule"])
    out = []
    for s in opt_sigs:
        out.append(Signal(
            bar_idx=int(s.gidx), side=s.side,
            stop_level=round(_vix_swing_stop(spy, s.gidx, s.side), 2),
            note="vix_regime_dayside"))
    return out


# Local family registry = base FAMILIES (byte-for-byte detectors) + #4 adapter. The base
# dict is untouched; we only ADD #4 so --family can dispatch to it here.
FAMILIES_EXT = {**FAMILIES, "vix_regime_dayside": _detect_vix_regime_dayside_family}


# ─────────────────────────────────────────────────────────────────────────────
# STOP CONSTRUCTIONS
# ─────────────────────────────────────────────────────────────────────────────
# A stop construction decides, for a given option bar, whether to exit and at what premium.
# It receives the per-trade context (entry premium, the chart rejection_level, side, strike,
# qty) and the construction's calibrated parameter, and is checked on each day-T bar in the
# SAME order as the base sim: premium/dollar stop first (conservative), then chart/level stop,
# then TP1. Each construction below produces the (premium_stop_floor, use_chart, use_tp1) that
# the generalized loop consumes — keeping the loop identical to the base sim's.
#
#  (a) "percent"        param = pct  (e.g. -0.08); premium floor = entry*(1+pct); chart on; tp1 on.
#  (b) "dollar"         param = $thresh (per-trade dollar-loss cap); premium floor derived so the
#                       realized dollar loss at the floor == -thresh: floor = entry - thresh/(qty*100);
#                       chart on; tp1 on. SAME $thresh at every DTE.
#  (c) "chart"          premium floor = effectively disabled (entry*0.01 == -99%); chart on; tp1 on.
#                       => a PRICE stop only; the option retains value at the chart-stop bar.
#  (d) "percent_scaled" param = per-DTE pct (calibrated so dollar-loss == 0DTE dollar-loss);
#                       premium floor = entry*(1+pct_dte); chart on; tp1 on. == -8% at 0DTE.


def _premium_floor_for(construction: str, entry_premium: float, param: float, qty: int) -> float:
    """The premium level at which the (premium/dollar) stop fires for this construction.

    Returns the absolute premium floor (a touched bar.low <= floor -> stop fill at floor).
    chart-only returns a near-zero floor (premium stop effectively off; chart governs)."""
    if construction in ("percent", "percent_scaled"):
        return entry_premium * (1.0 + param)         # param is a negative pct
    if construction == "dollar":
        # Cap the realized dollar loss at $param: loss at floor = (entry-floor)*qty*100 == param.
        floor = entry_premium - (param / (qty * 100.0))
        return max(0.01, floor)
    if construction == "chart":
        return entry_premium * 0.01                  # -99% backstop == chart-stop-only
    raise ValueError(construction)


# ─────────────────────────────────────────────────────────────────────────────
# GENERALIZED DTE TRADE — day-T fill conventions / overnight gap / expiry settlement
# copied LINE-FOR-LINE from _dte_expansion_sim.simulate_dte_trade; the ONLY change is the
# stop check uses the pluggable premium floor (so dollar/percent-scaled/chart all flow
# through the identical loop and identical settlement).
# ─────────────────────────────────────────────────────────────────────────────
def simulate_dte_trade_stop(
    sg: Signal,
    spy: pd.DataFrame,
    day_open_close: dict[dt.date, tuple[float, float]],
    dte: int,
    *,
    strike: int,
    expiry: dt.date,
    side: str,
    construction: str,
    stop_param: float,
    qty: int = QTY,
    tp1_premium_pct: float = TP1_PREMIUM_PCT,
    entry_slippage: float = DEFAULT_ENTRY_SLIPPAGE,
    exit_slippage: float = DEFAULT_EXIT_SLIPPAGE,
) -> Optional[DteFill]:
    bar = spy.iloc[sg.bar_idx]
    entry_time = bar["timestamp_et"]
    if hasattr(entry_time, "to_pydatetime"):
        entry_time = entry_time.to_pydatetime()
    entry_day = entry_time.date()
    entry_spot = float(bar["close"])
    atm = _strike_from_spot(entry_spot)

    opt_df = load_dte_contract_bars(option_symbol(expiry, strike, side), dte)
    if opt_df is None:
        return None

    # Entry: NEXT 5-min bar open after the trigger bar (no look-ahead). Verbatim convention.
    next_bar_start = entry_time + dt.timedelta(minutes=5)
    entry_bar_opt = _bar_at_or_after(opt_df, next_bar_start)
    if entry_bar_opt is None or entry_bar_opt.open <= 0:
        return None
    entry_premium = entry_bar_opt.open + entry_slippage
    if entry_premium <= 0:
        return None

    # PLUGGABLE STOP: derive the premium floor from the construction (the ONLY divergence
    # from simulate_dte_trade, which hard-codes entry*(1+premium_stop_pct)).
    stop_premium = _premium_floor_for(construction, entry_premium, stop_param, qty)
    tp1_premium = entry_premium * (1.0 + tp1_premium_pct)
    rejection_level = sg.stop_level
    level_buf = 0.50  # simulator_real LEVEL_STOP_BUFFER

    entry_idx_opt = None
    for k in range(len(opt_df)):
        if opt_df.iloc[k]["timestamp_et"] == entry_bar_opt.timestamp_et:
            entry_idx_opt = k
            break
    if entry_idx_opt is None:
        return None

    spy_idx = sg.bar_idx + 2
    opt_idx = entry_idx_opt + 1

    exit_premium: Optional[float] = None
    exit_reason: Optional[str] = None

    while opt_idx < len(opt_df) and spy_idx < len(spy):
        spy_bar = spy.iloc[spy_idx]
        spy_time = spy_bar["timestamp_et"]
        if hasattr(spy_time, "to_pydatetime"):
            spy_time = spy_time.to_pydatetime()
        if spy_time.date() != entry_day:
            break
        opt_bar = _quote_at_index(opt_df, opt_idx)
        if opt_bar is None:
            opt_idx += 1
            spy_idx += 1
            continue
        if opt_bar.timestamp_et.date() != entry_day:
            break

        worst_premium = opt_bar.low
        best_premium = opt_bar.high

        # (1) Premium/dollar stop (conservative: checked before TP on the same bar).
        #     For the chart construction the floor is ~0 so this effectively never fires.
        if worst_premium <= stop_premium:
            exit_premium = stop_premium
            exit_reason = "PREMIUM_STOP" if construction in ("percent", "percent_scaled") \
                else ("DOLLAR_STOP" if construction == "dollar" else "PREMIUM_STOP")
            break
        # (2) Chart/level stop on SPY close past rejection_level + buffer -> market exit.
        #     This is the PRICE stop the chart construction relies on; it is ON for all.
        if rejection_level is not None:
            breached = (
                (side == "P" and float(spy_bar["close"]) > rejection_level + level_buf)
                or (side == "C" and float(spy_bar["close"]) < rejection_level - level_buf)
            )
            if breached:
                exit_premium = max(0.01, opt_bar.close - exit_slippage)
                exit_reason = "LEVEL_STOP"
                break
        # (3) TP1 premium fallback -> fill exactly at the bracket level.
        if best_premium >= tp1_premium:
            exit_premium = tp1_premium
            exit_reason = "TP1_PREMIUM"
            break

        opt_idx += 1
        spy_idx += 1

    held_overnight = exit_reason is None
    gap_pts = 0.0

    if held_overnight:
        entry_close_spy = day_open_close.get(entry_day, (entry_spot, entry_spot))[1]
        sess = _sessions_between(day_open_close, entry_day, expiry)
        gap_through = False
        prev_close = entry_close_spy
        for sd in sess:
            o, c = day_open_close[sd]
            g = (prev_close - o) if side == "P" else (o - prev_close)
            gap_pts += g
            if rejection_level is not None and not gap_through:
                if (side == "P" and o > rejection_level + level_buf) or \
                   (side == "C" and o < rejection_level - level_buf):
                    intrinsic = max(0.0, (strike - o) if side == "P" else (o - strike))
                    exit_premium = max(0.0, intrinsic - exit_slippage)
                    exit_reason = "GAP_THROUGH_STOP"
                    gap_through = True
                    break
            prev_close = c

        if not gap_through:
            exp_close = day_open_close.get(expiry)
            if exp_close is None:
                return None
            sc = exp_close[1]
            intrinsic = max(0.0, (strike - sc) if side == "P" else (sc - strike))
            exit_premium = intrinsic
            exit_reason = "EXPIRY_SETTLEMENT"

    if exit_premium is None or exit_reason is None:
        return None

    dollar_pnl = (exit_premium - entry_premium) * qty * 100.0
    pct = dollar_pnl / (entry_premium * qty * 100.0) if entry_premium > 0 else 0.0
    return DteFill(
        date=str(entry_day), side=side, strike=int(strike), atm=int(atm),
        strike_off=int(strike - atm), expiry=str(expiry), dte=dte,
        entry_premium=round(entry_premium, 4), exit_premium=round(exit_premium, 4),
        dollar_pnl=round(dollar_pnl, 2), pct_return=round(pct, 5),
        exit_reason=exit_reason, held_overnight=held_overnight,
        gap_pts=round(gap_pts, 3), note=sg.note,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CELL RUNNER — one (dte, tier, construction) cell over all signals.
# Also records the per-trade ENTRY premium (needed to calibrate dollar + percent-scaled).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CellResult:
    rows: list
    cov: dict
    entry_premiums: list   # per filled trade (for calibration introspection)


def run_cell(signals, spy, day_open_close, dte, *, strike_offset, construction, stop_param):
    rows = []
    entry_premiums = []
    n_total = len(signals)
    n_filled = n_miss = n_none = n_no_exp = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date() if hasattr(bar["timestamp_et"], "date") \
            else bar["timestamp_et"].to_pydatetime().date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        res = _nearest_cached_strike_dte(d, target, sg.side, dte)
        if res is None:
            if _expiry_for_entry(d, dte) is None:
                n_no_exp += 1
            else:
                n_miss += 1
            continue
        strike, expiry = res
        fill = simulate_dte_trade_stop(
            sg, spy, day_open_close, dte, strike=strike, expiry=expiry, side=sg.side,
            construction=construction, stop_param=stop_param, qty=QTY,
            tp1_premium_pct=TP1_PREMIUM_PCT,
        )
        if fill is None:
            n_none += 1
            continue
        n_filled += 1
        rows.append(fill)
        entry_premiums.append(fill.entry_premium)
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_miss,
           "no_expiry_listed": n_no_exp, "sim_none": n_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return CellResult(rows=rows, cov=cov, entry_premiums=entry_premiums)


# ─────────────────────────────────────────────────────────────────────────────
# CALIBRATION — derive the dollar threshold + the per-DTE percent-scaled pct from the
# 0DTE -8% run at the LIVE tier (these are the constructions' calibrated parameters).
# ─────────────────────────────────────────────────────────────────────────────
def calibrate(signals, spy, day_open_close, tier_offset) -> dict:
    """Run the 0DTE -8% baseline at the live tier, then derive:
      - dollar_thresh   = MEDIAN per-trade DOLLAR LOSS (abs) on the 0DTE -8% losers.
      - median_0dte_prem = median ENTRY premium at 0DTE (for percent-scaled ratio).
      - median_dte_prem[d] = median ENTRY premium at each DTE (for percent-scaled ratio).
    """
    base0 = run_cell(signals, spy, day_open_close, 0,
                     strike_offset=tier_offset, construction="percent", stop_param=BASELINE_PCT)
    losses = [-r.dollar_pnl for r in base0.rows if r.dollar_pnl < 0]   # positive magnitudes
    dollar_thresh = float(np.median(losses)) if losses else 0.0
    median_0dte_prem = float(np.median(base0.entry_premiums)) if base0.entry_premiums else 0.0

    median_dte_prem = {}
    for d in DTES:
        cell = run_cell(signals, spy, day_open_close, d,
                        strike_offset=tier_offset, construction="percent", stop_param=BASELINE_PCT)
        median_dte_prem[d] = float(np.median(cell.entry_premiums)) if cell.entry_premiums else 0.0

    pct_scaled = {}
    for d in DTES:
        if median_dte_prem.get(d, 0) > 0 and median_0dte_prem > 0:
            pct_scaled[d] = round(BASELINE_PCT * (median_0dte_prem / median_dte_prem[d]), 4)
        else:
            pct_scaled[d] = BASELINE_PCT
    return {
        "tier_offset": tier_offset,
        "dollar_thresh": round(dollar_thresh, 2),
        "n_0dte_losers": len(losses),
        "median_0dte_entry_premium": round(median_0dte_prem, 4),
        "median_dte_entry_premium": {str(k): round(v, 4) for k, v in median_dte_prem.items()},
        "percent_scaled_pct": {str(k): v for k, v in pct_scaled.items()},
    }


# ─────────────────────────────────────────────────────────────────────────────
# RISK METRICS for the clean-win bar (book Sortino / maxDD / worst-day vs kill switch).
# Reuses per_trade_dist / book_risk byte-for-byte (accept any object with .date and a pnl
# attribute — DteFill has .dollar_pnl, so we wrap a tiny shim with .pnl).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class _PnlRow:
    date: str
    pnl: float


def _book_metrics(rows) -> dict:
    if not rows:
        return {"n": 0}
    shim = [_PnlRow(date=r.date, pnl=r.dollar_pnl) for r in rows]
    pt = per_trade_dist(shim)
    bk = book_risk(shim)
    return {
        "n": pt["n"],
        "exp_per_trade": pt["mean"],
        "total": pt["total"],
        "sharpe_per_trade": pt["sharpe_per_trade"],
        "worst_trade": pt["worst_trade"],
        "book_maxDD": bk.get("max_drawdown"),
        "book_worst_day": bk.get("worst_day"),
        "book_sortino_ann": bk.get("sortino_annualized"),
        "book_sharpe_ann": bk.get("sharpe_annualized"),
    }


def _oos_total(rows) -> float:
    return round(float(sum(r.dollar_pnl for r in rows if int(r.date[:4]) == OOS_YEAR)), 2)


# ─────────────────────────────────────────────────────────────────────────────
# BOOK AGGREGATION — the DEFAULT cap-aware realizable book for the sweep.
# A cell's raw fills (from run_cell) are the per-trade list; this is where they become
# a realizable BOOK. By DEFAULT (enforce_cap=True) the per-account order-admission cap
# (lib.cap_admission, calling the LIVE risk_gate) is applied: a fill the live engine would
# BLOCK is EXCLUDED ($0), never qty-reduced. enforce_cap=False returns the OLD cap-blind
# book BYTE-IDENTICAL to the pre-cap behaviour (every fill admitted) — comparison only.
# The cap is an ORDER gate, not a fill price: per-fill economics are untouched
# (simulator_real / the DTE sim stay behavior-unchanged).
# ─────────────────────────────────────────────────────────────────────────────
def aggregate_book(rows, account: str, equity: float, qty: int,
                   *, enforce_cap: bool = True) -> AdmissionResult:
    """Turn a cell's raw fills into the realizable (cap-admitted by default) book.

    The single book-aggregation entry point for the DTE harness + its overlays. Returns
    the full AdmissionResult (admitted / blocked / block_rate / block_codes / enforce_cap)
    so callers can both score the realizable book AND report the block profile."""
    return admit_book(rows, account, equity, qty, enforce_cap=enforce_cap)


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION — deterministic self-tests for each construction.
# ─────────────────────────────────────────────────────────────────────────────
def validate() -> list[str]:
    msgs: list[str] = []

    # First inherit the base sim's settlement/gap/expiry checks (so the reused machinery
    # is asserted here too, not just in the parent module).
    for m in base.validate():
        msgs.append("[base] " + m)

    qty = QTY
    entry = 1.00

    # (a) percent -8% -> floor = 0.92 -> realized loss at floor = (1.00-0.92)*3*100 = $24.
    floor_a = _premium_floor_for("percent", entry, -0.08, qty)
    assert abs(floor_a - 0.92) < 1e-9, floor_a
    loss_a = (entry - floor_a) * qty * 100.0
    assert abs(loss_a - 24.0) < 1e-6, loss_a
    msgs.append(f"OK (a) percent -8%: entry ${entry:.2f} -> floor ${floor_a:.2f} -> capped loss ${loss_a:.2f}")

    # (b) dollar-anchored $39 cap -> floor = entry - 39/(3*100) = 1.00 - 0.13 = 0.87;
    #     realized loss at floor = (1.00-0.87)*3*100 = $39 (caps the DOLLAR loss exactly).
    thresh = 39.0
    floor_b = _premium_floor_for("dollar", entry, thresh, qty)
    assert abs(floor_b - 0.87) < 1e-9, floor_b
    loss_b = (entry - floor_b) * qty * 100.0
    assert abs(loss_b - thresh) < 1e-6, loss_b
    msgs.append(f"OK (b) dollar-anchored ${thresh:.0f}: entry ${entry:.2f} -> floor ${floor_b:.2f} "
                f"-> capped loss ${loss_b:.2f} (== threshold)")
    # And the SAME $39 cap on a BIGGER 1DTE-style premium ($2.00) caps the SAME dollars:
    entry_big = 2.00
    floor_b_big = _premium_floor_for("dollar", entry_big, thresh, qty)
    loss_b_big = (entry_big - floor_b_big) * qty * 100.0
    assert abs(loss_b_big - thresh) < 1e-6, loss_b_big
    pct_big = (floor_b_big / entry_big - 1.0) * 100.0
    msgs.append(f"OK (b) SAME ${thresh:.0f} cap on bigger ${entry_big:.2f} premium -> floor "
                f"${floor_b_big:.2f} ({pct_big:.1f}% vs -8%) -> capped loss ${loss_b_big:.2f} "
                f"(dollar loss INVARIANT to DTE premium — the lever)")

    # (c) chart-only -> floor ~ 1% of entry (premium stop effectively disabled; chart governs).
    floor_c = _premium_floor_for("chart", entry, 0.0, qty)
    assert abs(floor_c - 0.01) < 1e-9, floor_c
    msgs.append(f"OK (c) chart-only: premium floor ${floor_c:.2f} (== -99%; the PRICE/level stop "
                f"governs; option retains value at the structural-stop bar)")

    # (d) percent-scaled reproduces -8% at 0DTE (param == -0.08 there); on a 2x premium it
    #     halves the percent so the DOLLAR loss matches 0DTE.
    floor_d0 = _premium_floor_for("percent_scaled", entry, -0.08, qty)
    assert abs(floor_d0 - floor_a) < 1e-9, (floor_d0, floor_a)
    msgs.append(f"OK (d) percent-scaled: reproduces -8% at 0DTE (floor ${floor_d0:.2f} == percent "
                f"floor ${floor_a:.2f}); per-DTE pct = -8% * (0DTE_prem / DTE_prem)")
    # 0DTE prem 1.00, 1DTE prem 2.00 -> pct_1dte = -0.08 * (1.00/2.00) = -0.04 -> $ loss matches.
    pct_1dte = round(-0.08 * (1.00 / 2.00), 4)
    floor_d1 = _premium_floor_for("percent_scaled", 2.00, pct_1dte, qty)
    loss_d1 = (2.00 - floor_d1) * qty * 100.0
    assert abs(loss_d1 - 24.0) < 1e-6, loss_d1   # == the 0DTE $24 loss above
    msgs.append(f"OK (d) percent-scaled at 1DTE prem $2.00: pct={pct_1dte} -> floor ${floor_d1:.2f} "
                f"-> capped loss ${loss_d1:.2f} (== 0DTE $24 dollar loss)")
    return msgs


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def _load_spy_vix():
    return base._load_spy_vix()


def _print_sample(signals, spy, day_open_close, tier_offset, calib):
    """Print one fillable trade under EACH of the 4 constructions at 1DTE (the lever DTE)."""
    constructions = [
        ("percent", BASELINE_PCT),
        ("dollar", calib["dollar_thresh"]),
        ("chart", 0.0),
        ("percent_scaled", calib["percent_scaled_pct"]["1"]),
    ]
    # find a signal fillable at 1DTE under percent (the densest), reuse it for all.
    chosen = None
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"]); atm = _strike_from_spot(spot)
        target = atm - tier_offset if sg.side == "P" else atm + tier_offset
        res = _nearest_cached_strike_dte(d, target, sg.side, 1)
        if res is None:
            continue
        strike, expiry = res
        if simulate_dte_trade_stop(sg, spy, day_open_close, 1, strike=strike, expiry=expiry,
                                   side=sg.side, construction="percent", stop_param=BASELINE_PCT):
            chosen = (sg, d, strike, expiry)
            break
    if chosen is None:
        print("  (no 1DTE sample fillable)")
        return
    sg, d, strike, expiry = chosen
    print(f"\n=== SAMPLE 1DTE TRADE under EACH stop construction (live tier off={tier_offset:+d}) ===")
    print(f"  signal {d} {sg.side} strike={strike} expiry={expiry} note={sg.note}")
    for name, param in constructions:
        f = simulate_dte_trade_stop(sg, spy, day_open_close, 1, strike=strike, expiry=expiry,
                                    side=sg.side, construction=name, stop_param=param)
        floor = _premium_floor_for(name, f.entry_premium, param, QTY)
        floor_pct = (floor / f.entry_premium - 1.0) * 100.0 if f.entry_premium else 0.0
        floor_loss = (f.entry_premium - floor) * QTY * 100.0
        print(f"  [{name:14s} param={param:>7}] entry=${f.entry_premium:.2f} "
              f"stop_floor=${floor:.2f} ({floor_pct:+.1f}%, caps ${floor_loss:.2f}) "
              f"-> exit=${f.exit_premium:.2f} reason={f.exit_reason:16s} "
              f"P&L=${f.dollar_pnl:+.2f} held_on={f.held_overnight}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="validate + print a sample trade under each stop")
    ap.add_argument("--validate", action="store_true", help="run deterministic self-tests only")
    ap.add_argument("--family", default="vwap_continuation", choices=list(FAMILIES_EXT))
    ap.add_argument("--tier", default=None, choices=list(TIERS),
                    help="strike tier; defaults to the family's live tier "
                         "(ITM-2 for vwap_continuation, ATM for vix_regime_dayside)")
    args = ap.parse_args()

    # Per-family live tier default (#4 is ATM-only/Safe-2; #1 is ITM-2). C29: the dollar-stop
    # is re-derived per (edge, tier) below, so this only sets WHICH tier to A/B at.
    if args.tier is None:
        args.tier = VIX_REGIME_LIVE_TIER if args.family == "vix_regime_dayside" else LIVE_TIER

    if args.validate:
        for m in validate():
            print("  " + m)
        print("VALIDATION PASSED")
        return 0

    print("[dte-stop] loading SPY+VIX ...", flush=True)
    spy, vix = _load_spy_vix()
    day_open_close = _spy_day_open_close(spy)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    for d in DTES:
        if d:
            _build_expiry_index(d)
    print(f"[dte-stop] SPY bars={len(spy)} days={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    detect = FAMILIES_EXT[args.family]
    signals = detect(days, vix, spy, ribbon)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    print(f"[dte-stop] family={args.family} signals={len(signals)} on {sig_days} days", flush=True)

    tier_offset = TIERS[args.tier]
    print(f"[dte-stop] tier={args.tier} (offset {tier_offset:+d}); calibrating from 0DTE -8% ...", flush=True)
    calib = calibrate(signals, spy, day_open_close, tier_offset)
    print(f"[dte-stop] CALIBRATION: dollar_thresh=${calib['dollar_thresh']} "
          f"(median 0DTE loss on {calib['n_0dte_losers']} losers) | "
          f"median_0dte_prem=${calib['median_0dte_entry_premium']} | "
          f"percent_scaled={calib['percent_scaled_pct']}", flush=True)

    if args.smoke:
        print("\n=== VALIDATION ===")
        for m in validate():
            print("  " + m)
        _print_sample(signals, spy, day_open_close, tier_offset, calib)
        return 0

    # ── FULL MATRIX: DTE x construction at the chosen tier ───────────────────────
    constructions = {
        "a_percent_-8pct": ("percent", lambda d: BASELINE_PCT),
        "b_dollar_anchored": ("dollar", lambda d: calib["dollar_thresh"]),
        "c_chart_level": ("chart", lambda d: 0.0),
        "d_percent_scaled": ("percent_scaled", lambda d: calib["percent_scaled_pct"][str(d)]),
    }

    # 0DTE -8% baseline (the reference the clean-win bar measures against).
    base_cell = run_cell(signals, spy, day_open_close, 0,
                         strike_offset=tier_offset, construction="percent", stop_param=BASELINE_PCT)
    base_book = _book_metrics(base_cell.rows)
    base_oos_total = _oos_total(base_cell.rows)
    base_maxdd = abs(base_book.get("book_maxDD") or 0.0)
    base_sortino = base_book.get("book_sortino_ann") or 0.0

    matrix = {}
    winners = []
    for ckey, (cname, pfn) in constructions.items():
        by_dte = {}
        for d in DTES:
            cell = run_cell(signals, spy, day_open_close, d,
                            strike_offset=tier_offset, construction=cname, stop_param=pfn(d))
            m = dte_metrics(cell.rows)
            structural_ok, structural_fails = clears_bar(m)
            book = _book_metrics(cell.rows)
            oos_total = _oos_total(cell.rows)

            # CLEAN-WIN bar legs (only meaningful for DTE>0 vs the 0DTE -8% baseline).
            var_maxdd = abs(book.get("book_maxDD") or 0.0)
            var_sortino = book.get("book_sortino_ann") or 0.0
            worst_day = book.get("book_worst_day") or 0.0
            lift_kept = oos_total > base_oos_total + 1e-9         # materially MORE OOS dollars
            maxdd_worsen = (var_maxdd - base_maxdd) / base_maxdd if base_maxdd > 0 else 0.0
            maxdd_ok = maxdd_worsen <= MAXDD_MATERIAL_WORSEN_PCT  # not materially worse than 0DTE
            sortino_ok = var_sortino >= base_sortino - 1e-9
            killswitch_ok = worst_day >= KILL_SWITCH["bold"]      # worst day inside Bold kill switch
            killswitch_safe_ok = worst_day >= KILL_SWITCH["safe"]
            clean_win = bool(d > 0 and lift_kept and maxdd_ok and sortino_ok
                             and structural_ok and killswitch_ok)
            if clean_win:
                winners.append({"construction": ckey, "dte": d,
                                "oos_total": oos_total, "maxDD": book.get("book_maxDD"),
                                "sortino": var_sortino})

            by_dte[str(d)] = {
                "stop_param": pfn(d),
                "coverage": cell.cov,
                "metrics": m,
                "book": book,
                "oos_total": oos_total,
                "structural_bar_pass": structural_ok,
                "structural_bar_fails": structural_fails,
                "clean_win_legs": {
                    "vs_0dte_8pct_baseline": True,
                    "oos_lift_kept": bool(lift_kept),
                    "oos_total_vs_base": round(oos_total - base_oos_total, 2),
                    "maxdd_worsen_frac": round(maxdd_worsen, 4),
                    "maxdd_not_materially_worse": bool(maxdd_ok),
                    "sortino_holds": bool(sortino_ok),
                    "structural_bar_pass": structural_ok,
                    "worst_day_inside_bold_killswitch": bool(killswitch_ok),
                    "worst_day_inside_safe_killswitch": bool(killswitch_safe_ok),
                    "CLEAN_WIN": clean_win,
                },
            }
            print(f"  {ckey:18s} DTE={d} | n={m.get('n','-'):>3} exp=${m.get('exp_dollar','-'):>8} "
                  f"oos_tot=${oos_total:>9} maxDD=${book.get('book_maxDD','-'):>9} "
                  f"sortino={var_sortino:>6} worstDay=${worst_day:>8} struct={structural_ok} "
                  f"-> {'CLEAN_WIN' if clean_win else ''}", flush=True)
        matrix[ckey] = {"construction": cname, "by_dte": by_dte}

    verdict = "DTE_STOP_CLEAN_WIN" if winners else "NO_CLEAN_WIN_-8pct_0DTE_REMAINS"
    results = {
        "campaign": "DTE x STOP-CONSTRUCTION MATRIX — edge #1 vwap_continuation (real DTE OPRA fills)",
        "purpose": ("does a dollar-/percent-scaled-/chart-stop turn the 1-2DTE +$/tr theta lift into "
                    "a CLEAN win by killing the -8%-percent-stop maxDD-doubling? Test the DTE x STOP "
                    "matrix, not stops in isolation."),
        "run_date": dt.date.today().isoformat(),
        "family": args.family,
        "tier": args.tier,
        "tier_offset": tier_offset,
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "n_signals": len(signals),
        "calibration": calib,
        "0dte_8pct_baseline": {"book": base_book, "oos_total": base_oos_total},
        "constructions": {
            "a_percent_-8pct": "the live default; premium floor = entry*(1-0.08)",
            "b_dollar_anchored": (f"per-trade dollar-loss cap = median 0DTE -8% loss "
                                  f"(${calib['dollar_thresh']}); SAME $ at every DTE"),
            "c_chart_level": "PRICE/level stop only (premium stop disabled); option retains value at the level bar",
            "d_percent_scaled": ("per-DTE pct so dollar-loss == 0DTE dollar-loss: "
                                 "-8% * (median_0dte_prem / median_dte_prem)"),
        },
        "clean_win_bar": ("DTE>0 cell that (1) keeps materially MORE OOS dollars than the 0DTE -8% "
                          "baseline at the same tier, (2) maxDD not materially worse than 0DTE -8% "
                          f"(<=+{MAXDD_MATERIAL_WORSEN_PCT*100:.0f}%), (3) book Sortino >= 0DTE -8% "
                          "baseline, (4) clears the structural+L173 bar, (5) worst day inside the "
                          f"Bold kill switch (${KILL_SWITCH['bold']})"),
        "kill_switch": KILL_SWITCH,
        "maxdd_material_worsen_threshold": MAXDD_MATERIAL_WORSEN_PCT,
        "matrix": matrix,
        "winners": winners,
        "verdict": verdict,
        "DISCLOSURE": {
            "fills": ("real per-DTE OPRA day-T bars + honest overnight gap + expiry intrinsic "
                      "settlement (no synthetic mid-life marks) — inherited byte-for-byte from "
                      "_dte_expansion_sim.simulate_dte_trade; only the stop check is generalized."),
            "detector": "BYTE-FOR-BYTE FAMILIES[family] (#1 = _edgehunt_vwap_continuation, the LIVE detector)",
            "calibration_note": ("dollar_thresh + percent_scaled pct are calibrated FROM the 0DTE -8% "
                                 "run at this tier, then frozen and applied at 1/2DTE — no per-DTE refit."),
            "chart_stop_caveat": ("chart-stop-only was BAD at 0DTE (recency stop-variant A/B: 8x deeper "
                                  "maxDD — the -8% truncation IS the 0DTE risk mgmt); it is tested here "
                                  "at 1-2DTE where the option retains value at a structural-stop exit. "
                                  "The matrix quantifies whether it transfers."),
            "tighter_stop_caveat": ("a tighter dollar/percent stop may stop out MORE often, cutting the "
                                    "lift (the diagonal failure). oos_total quantifies the NET, not just maxDD."),
            "n_caveat": "DTE option cache covers a sub-window of the SPY history; per-DTE n is the fill_rate authority.",
        },
    }
    # Family-tagged output so #4 (and other edges) never clobber #1's dte-stop-construction.json.
    out_path = OUT if args.family == "vwap_continuation" else (
        OUT.parent / f"dte-stop-construction-{args.family}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n[dte-stop] wrote {out_path}", flush=True)

    print("\n=== DTE x STOP-CONSTRUCTION VERDICT ===")
    print(f"VERDICT: {verdict}")
    if winners:
        for w in winners:
            print(f"  CLEAN_WIN: {w['construction']} DTE={w['dte']} oos_tot=${w['oos_total']} "
                  f"maxDD=${w['maxDD']} sortino={w['sortino']}")
    else:
        print("  No DTE>0 cell clears the clean-win bar -> 0DTE -8% remains optimal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
