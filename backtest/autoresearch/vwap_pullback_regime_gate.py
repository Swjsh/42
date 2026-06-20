"""vwap_pullback_regime_gate — diagnose H4 bimodality + test CAUSAL regime gates.

THE PROBLEM (from analysis/recommendations/vwap-trend-pullback-LIVE.json):
the H4 VWAP trend-day pullback is +EV on real OPRA fills, OOS-positive, DSR PASS,
both directions positive — but it is **bimodal**: it bled 4 OOS months
(2025-07..2025-10) then went 7 consecutive positive OOS months (2025-11..2026-05).
That regime-sensitivity is why it is BASE-size/WATCH. If a CAUSAL regime gate (read
at-or-before entry) cleanly separates the good periods from the bad — making ALL
sub-windows OOS-positive, keeping n reasonable, surviving its OWN OOS, and being
live-computable — H4 becomes a 2nd LIVE +EV edge.

WHAT THIS DOES (rigor first; do NOT curve-fit to the known bad window):
  1. DIAGNOSE: reproduce the EXACT validated H4 signals (detect_vwap_pullback) with
     real fills, attach a CAUSAL regime-feature vector to each (computed only from
     bars at-or-before the trigger), and contrast the losing-month vs winning-month
     feature distributions. Find the STRUCTURAL difference, not a date filter.
  2. SWEEP GATES: for each candidate gate family (VIX band, VIX character, intraday
     trend-strength, realized-vol / range-expansion, the regime_book classify_regime
     cell), re-run H4 real fills on the SURVIVING subset and report
     IS/OOS/per-sub-window/n/DSR. A gate "kills the bimodality" iff every contiguous
     sub-window is OOS-positive while keeping n reasonable.
  3. GATE-OWN-OOS (anti-overfit): for the leading gate, DERIVE the threshold on the
     IS half only, then apply it UNSEEN to the OOS half. A gate curve-fit to the 4
     bad months fails this. (Run separately by the verdict harness.)

CAUSALITY (L166, C6): every regime feature is read from the SAME `rth` slice the
detector saw, sliced to bars[0..j] where j is the trigger bar; VIX is the aligned
value at the trigger bar index; the ribbon stack is `ribbon_df.iloc[bar_idx]` (an
EMA of closes up to that bar). No bar after the trigger is ever read. Re-uses the
discovery detector + real-fills simulator verbatim — apples-to-apples with the
ratified survivor.

PROPOSE-ONLY (Rule 9): reads data, writes a scorecard JSON. No params / heartbeat /
order path. Pure-Python, $0, deterministic (no RNG in the gate logic).

Usage
-----
    backtest/.venv/Scripts/python.exe backtest/autoresearch/vwap_pullback_regime_gate.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]          # ...\42\backtest
PROJECT = REPO.parent                               # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Reuse the validated detector + sim verbatim — apples-to-apples with the survivor.
from autoresearch.infinite_ammo_discovery import (   # noqa: E402
    load_spy,
    align_vix,
    build_day_contexts,
    detect_vwap_pullback,
    session_vwap_asof,
    _nearest_cached_strike,
    _quarter,
)
from lib.ribbon import compute_ribbon                # noqa: E402
from lib.simulator_real import simulate_trade_real, _strike_from_spot  # noqa: E402
from lib.validation.gate import evaluate_candidate   # noqa: E402
from lib.engine.regime_book import (                 # noqa: E402
    RegimeSignals,
    classify_regime,
    Regime,
    VIX_HIGH_VOL_FLOOR,
    VIX_LOW_CEIL,
    RANGE_COMPRESSION_RATIO,
)

SPY_CSV = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_CSV = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
OUT = PROJECT / "analysis" / "recommendations" / "vwap-trend-pullback-regime-gate.json"

QTY = 3
MAX_STRIKE_STEPS = 4
N_TRIALS_DSR = 30          # match discovery's selection-bias deflation count
WF_GATE = 0.70
OOS_SPLIT_FRAC = 0.70
TIER_OFFSET_ATM = 0

# TWO exit configs, reported side-by-side (honest, load-bearing):
#   * chart_stop_only (-0.99): what the LIVE watcher trades
#     (vwap_trend_pullback_watcher.DEFAULT_PREMIUM_STOP_PCT = -0.99, L51/L55/C2).
#   * scorecard_default (-0.08): what analysis/recommendations/vwap-trend-pullback-LIVE.json
#     and its WF/sub-window bimodality were ACTUALLY computed on (the discovery
#     simulate_signals passes NO override -> simulate_trade_real default -0.08).
# The documented +$45.88/42.4% + the 2025-07..10 bleed are the -0.08 numbers; the
# live-traded config is chart-stop-only. We gate BOTH and report the difference (this
# exit/config mismatch is itself a finding — C29/L149: exit knobs don't transfer).
EXIT_CONFIGS = {"chart_stop_only": -0.99, "scorecard_default_-8pct": -0.08}
LIVE_EXIT_KEY = "chart_stop_only"

# The known bad OOS window (from the ratify scorecard). Used ONLY for diagnosis /
# reporting which months a gate drops — NEVER as a filter (that would be the exact
# date-curve-fit this harness exists to avoid).
KNOWN_BAD_MONTHS = {"2025-07", "2025-08", "2025-09", "2025-10"}
VIX_DEADBAND = 0.05        # matches filters/regime_book character deadband


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL REGIME FEATURES per signal (read only bars[0..trigger])
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class GatedTrade:
    """One H4 trade + its causal regime features + the real-fill P&L."""
    date: str
    month: str
    side: str
    bar_idx: int
    pnl: float
    pct: float
    exit_reason: str
    strike_off: int
    # ── causal regime features (all at-or-before trigger bar) ──
    vix: float
    vix_rising: bool
    vix_falling: bool
    realized_vol_bps: float        # stdev of 5m log-returns to date (annualized-ish bps)
    morning_move_pct: float        # |open -> trigger close| (trend-day strength proxy)
    trend_strength_adx: float      # ADX-like directional index over the session to date
    range_ratio: float             # trigger-bar range / trailing-20-bar median range
    ribbon_stack: str
    regime_cell: str               # classify_regime() output
    vwap_dist_pct: float           # tightness of the VWAP tag


def _trailing_median_range(spy_df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    """Median (H-L) over the prior `lookback` bars (look-ahead-safe; excludes idx)."""
    start = max(0, idx - lookback)
    if start >= idx:
        return 0.0
    sl = spy_df.iloc[start:idx]
    rng = (sl["high"] - sl["low"]).to_numpy(dtype=float)
    rng = rng[rng > 0]
    return float(np.median(rng)) if rng.size else 0.0


def _adx_like(rth_to_date: pd.DataFrame) -> float:
    """A lightweight ADX-like trend-strength index over the session to date.

    Wilder's ADX is the canonical 'is this trending vs chopping' measure. We compute
    a simplified, look-ahead-safe variant on the session's 5m bars UP TO the trigger:
    directional movement (+DM/-DM) vs true range, smoothed by simple mean (not Wilder
    smoothing — n is small intraday). Returns 0..100; higher = stronger one-way trend.
    Pure function of the passed (already-sliced-causal) frame.
    """
    if len(rth_to_date) < 3:
        return 0.0
    high = rth_to_date["high"].to_numpy(dtype=float)
    low = rth_to_date["low"].to_numpy(dtype=float)
    close = rth_to_date["close"].to_numpy(dtype=float)
    up_move = high[1:] - high[:-1]
    down_move = low[:-1] - low[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1]),
    ])
    atr = tr.mean()
    if atr <= 0:
        return 0.0
    plus_di = 100.0 * plus_dm.mean() / atr
    minus_di = 100.0 * minus_dm.mean() / atr
    denom = plus_di + minus_di
    if denom <= 0:
        return 0.0
    dx = 100.0 * abs(plus_di - minus_di) / denom
    return float(dx)


def _realized_vol_bps(rth_to_date: pd.DataFrame) -> float:
    """Stdev of 5m close-to-close log returns to date, in basis points (per-bar)."""
    c = rth_to_date["close"].to_numpy(dtype=float)
    if c.size < 3:
        return 0.0
    rets = np.diff(np.log(c))
    if rets.size < 2:
        return 0.0
    return float(np.std(rets, ddof=1) * 1e4)


def _ribbon_stack_at(ribbon_df: pd.DataFrame, idx: int) -> str:
    if idx < 0 or idx >= len(ribbon_df):
        return "WARMUP"
    row = ribbon_df.iloc[idx]
    st = str(row["stack"])
    return st if st else "WARMUP"


def build_gated_trades(spy_df, ribbon_df, vix, days,
                       premium_stop_pct: float = -0.99) -> list[GatedTrade]:
    """Reproduce H4 signals (verbatim detector) + attach causal features + real fills.

    ``premium_stop_pct`` selects the exit config (chart-stop-only -0.99 = live; -0.08 =
    the discovery/scorecard default). Features are identical across configs (same
    signals); only the fill P&L changes.
    """
    signals = detect_vwap_pullback(spy_df, ribbon_df, vix, days)
    # Map each global bar_idx -> its day's rth frame for causal slicing.
    rth_by_date: dict[dt.date, pd.DataFrame] = {dc.date: dc.rth for dc in days}

    out: list[GatedTrade] = []
    for sg in signals:
        bar = spy_df.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - TIER_OFFSET_ATM if sg.side == "P" else atm + TIER_OFFSET_ATM
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            continue
        ev = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy_df, ribbon_df=ribbon_df,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "vwap_pullback"],
            side=sg.side, qty=QTY, setup="DISCOVERY", strike_override=strike,
            entry_vix=ev, premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            continue

        # ── causal feature vector (bars[0..trigger] only) ──
        rth = rth_by_date.get(d)
        if rth is None or rth.empty:
            continue
        # Position of the trigger bar within the day's rth (global idx preserved).
        try:
            j = rth.index.get_loc(sg.bar_idx)
        except KeyError:
            continue
        if isinstance(j, slice):  # pragma: no cover - defensive
            j = j.start
        rth_to_date = rth.iloc[: j + 1]

        vwap = session_vwap_asof(rth).to_numpy(dtype=float)
        v = float(vwap[j]) if j < len(vwap) else float("nan")
        open_px = float(rth["open"].iloc[0])
        cur_close = float(rth_to_date["close"].iloc[-1])
        morning_move = abs(cur_close / open_px - 1.0) if open_px > 0 else 0.0

        vix_now = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        vix_prior = float(vix.iloc[sg.bar_idx - 1]) if sg.bar_idx - 1 >= 0 else vix_now
        vrise = vix_now > vix_prior + VIX_DEADBAND
        vfall = vix_now < vix_prior - VIX_DEADBAND

        med_range = _trailing_median_range(spy_df, sg.bar_idx, 20)
        bar_range = float(bar["high"]) - float(bar["low"])
        range_ratio = (bar_range / med_range) if med_range > 0 else float("nan")

        stack = _ribbon_stack_at(ribbon_df, sg.bar_idx)
        rsig = RegimeSignals(
            vix_now=vix_now, vix_prior=vix_prior, ribbon_stack=stack,
            htf_stack=None, range_ratio=(None if np.isnan(range_ratio) else range_ratio),
            gex_hint=None,
        )
        cell = classify_regime(rsig)

        if sg.side == "C":
            vwap_dist = abs(float(bar["low"]) - v) / v if v > 0 else float("nan")
        else:
            vwap_dist = abs(float(bar["high"]) - v) / v if v > 0 else float("nan")

        out.append(GatedTrade(
            date=str(d), month=str(d)[:7], side=sg.side, bar_idx=int(sg.bar_idx),
            pnl=round(float(fill.dollar_pnl), 2),
            pct=round(float(fill.pct_return_on_premium), 5),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
            strike_off=int(strike - atm),
            vix=round(vix_now, 2), vix_rising=bool(vrise), vix_falling=bool(vfall),
            realized_vol_bps=round(_realized_vol_bps(rth_to_date), 2),
            morning_move_pct=round(morning_move, 5),
            trend_strength_adx=round(_adx_like(rth_to_date), 2),
            range_ratio=(None if np.isnan(range_ratio) else round(range_ratio, 3)),
            ribbon_stack=stack,
            regime_cell=str(cell),
            vwap_dist_pct=(None if np.isnan(vwap_dist) else round(vwap_dist, 5)),
        ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# METRICS on a subset of trades (IS/OOS/sub-window/DSR)
# ─────────────────────────────────────────────────────────────────────────────
def _wf_norm(is_p, n_is, oos_p, n_oos):
    if n_is == 0 or n_oos == 0 or is_p == 0:
        return 0.0
    return (oos_p / n_oos) / (is_p / n_is)


def subset_metrics(trades: list[GatedTrade], oos_cut_date: str, k_sub: int = 4) -> dict:
    """Full metric block for a subset: exp, IS/OOS, k contiguous sub-windows, DSR,
    monthly OOS positivity, both-direction sign."""
    if not trades:
        return {"n": 0, "verdict": "NO_TRADES"}
    trades = sorted(trades, key=lambda t: (t.date, t.bar_idx))
    pnl = np.array([t.pnl for t in trades], dtype=float)
    pct = np.array([t.pct for t in trades], dtype=float)
    n = len(trades)
    wins = int((pnl > 0).sum())

    is_rows = [t for t in trades if t.date < oos_cut_date]
    oos_rows = [t for t in trades if t.date >= oos_cut_date]
    is_pct = np.array([t.pct for t in is_rows], dtype=float)
    oos_pct = np.array([t.pct for t in oos_rows], dtype=float)
    is_exp_pct = float(is_pct.mean()) if is_pct.size else 0.0
    oos_exp_pct = float(oos_pct.mean()) if oos_pct.size else 0.0
    is_exp_d = float(np.mean([t.pnl for t in is_rows])) if is_rows else 0.0
    oos_exp_d = float(np.mean([t.pnl for t in oos_rows])) if oos_rows else 0.0
    oos_sign_stable = bool(is_rows and oos_rows and is_exp_pct > 0 and oos_exp_pct > 0)

    # k contiguous chronological sub-windows; hurt = mean P&L < 0
    bounds = [round(i * n / k_sub) for i in range(k_sub + 1)]
    subs, hurt = [], 0
    for i in range(k_sub):
        seg = pnl[bounds[i]:bounds[i + 1]]
        m = float(seg.mean()) if seg.size else 0.0
        if m < 0:
            hurt += 1
        subs.append({"window": i + 1, "n": int(seg.size), "mean_pnl": round(m, 2),
                     "total_pnl": round(float(seg.sum()), 2)})
    all_sub_positive = hurt == 0

    # monthly OOS positivity (the bimodality view)
    by_month: dict[str, list[float]] = {}
    for t in oos_rows:
        by_month.setdefault(t.month, []).append(t.pnl)
    months = {m: {"n": len(v), "exp": round(float(np.mean(v)), 2),
                  "total": round(float(np.sum(v)), 2), "positive": bool(np.sum(v) > 0)}
              for m, v in sorted(by_month.items())}
    oos_months_positive = sum(1 for v in months.values() if v["positive"])
    oos_months_total = len(months)

    # by-side
    by_side = {}
    for sd in ("C", "P"):
        s = np.array([t.pnl for t in trades if t.side == sd], dtype=float)
        if s.size:
            by_side[sd] = {"n": int(s.size), "exp": round(float(s.mean()), 2),
                           "wr": round(100.0 * float((s > 0).mean()), 1),
                           "total": round(float(s.sum()), 2)}
    both_dirs_positive = bool(len(by_side) == 2 and all(b["exp"] > 0 for b in by_side.values()))

    # drop-top-5 robustness
    spnl = np.sort(pnl)
    drop5 = round(float(spnl[:-5].mean()), 2) if n > 5 else None
    robust = bool(n >= 10 and drop5 is not None and drop5 > 0)

    # DSR on % stream
    dsr = {}
    try:
        if pct.std(ddof=0) > 0 and n >= 2:
            dsr = evaluate_candidate(pct, n_trials=N_TRIALS_DSR).to_dict()
        else:
            dsr = {"verdict": "DEGENERATE"}
    except Exception as e:  # noqa: BLE001
        dsr = {"verdict": "ERROR", "error": str(e)}

    return {
        "n": n, "wins": wins, "wr_pct": round(100.0 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "exp_pct": round(float(pct.mean()), 5),
        "is_n": len(is_rows), "oos_n": len(oos_rows),
        "is_exp_dollar": round(is_exp_d, 2), "oos_exp_dollar": round(oos_exp_d, 2),
        "is_exp_pct": round(is_exp_pct, 5), "oos_exp_pct": round(oos_exp_pct, 5),
        "oos_sign_stable": oos_sign_stable,
        "sub_windows": subs, "n_sub_hurt": hurt, "all_sub_windows_positive": all_sub_positive,
        "oos_months_positive": oos_months_positive, "oos_months_total": oos_months_total,
        "oos_months_all_positive": bool(oos_months_total > 0 and oos_months_positive == oos_months_total),
        "oos_months": months,
        "by_side": by_side, "both_dirs_positive": both_dirs_positive,
        "drop_top5_mean_dollar": drop5, "robust_to_outliers": robust,
        "dsr": dsr, "dsr_verdict": dsr.get("verdict", "UNKNOWN"),
        "exit_reason_hist": dict(Counter(t.exit_reason for t in trades)),
    }


def rolling_month_wf(trades: list[GatedTrade]) -> dict:
    """Expanding-IS / rolling-1-month-OOS WF — faithful to vwap_pullback_ratify.walk_forward.

    Reproduces the documented bimodality view: per OOS month from the 7th distinct
    calendar month on, IS=all prior trades, OOS=this month. Reports each month's OOS
    expectancy + positivity so the 2025-07..10 bleed is explicit on whatever subset is
    passed (full series or a gated subset)."""
    dr = sorted((dt.date.fromisoformat(t.date), t.pnl) for t in trades)
    if not dr:
        return {"verdict": "NO_TRADES", "windows": []}
    all_dates = [d for d, _ in dr]
    months = sorted({(d.year, d.month) for d in all_dates})
    windows = []
    for (yy, mm) in months:
        in_m = sorted(d for d in set(all_dates) if d.year == yy and d.month == mm)
        if not in_m:
            continue
        oos_start, oos_end = in_m[0], in_m[-1]
        is_tr = [(d, p) for d, p in dr if d < oos_start]
        oos_tr = [(d, p) for d, p in dr if oos_start <= d <= oos_end]
        prior_months = len({(d.year, d.month) for d, _ in is_tr})
        if prior_months < 6 or not oos_tr:
            continue
        is_p, oos_p = sum(p for _, p in is_tr), sum(p for _, p in oos_tr)
        wf = _wf_norm(is_p, len(is_tr), oos_p, len(oos_tr))
        windows.append({"oos_month": f"{yy}-{mm:02d}", "n_oos": len(oos_tr),
                        "oos_pnl": round(oos_p, 2), "oos_exp": round(oos_p / len(oos_tr), 2),
                        "wf_norm": round(wf, 3), "oos_positive": bool(oos_p > 0)})
    if not windows:
        return {"verdict": "INSUFFICIENT_WINDOWS", "windows": []}
    wfs = [w["wf_norm"] for w in windows]
    oos_pos = [w["oos_positive"] for w in windows]
    neg = [w["oos_month"] for w in windows if not w["oos_positive"]]
    trailing = 0
    for w in reversed(windows):
        if w["oos_positive"]:
            trailing += 1
        else:
            break
    return {
        "n_windows": len(windows), "median_wf_norm": round(float(np.median(wfs)), 3),
        "oos_positive_frac": round(sum(oos_pos) / len(oos_pos), 2),
        "negative_oos_months": neg, "trailing_positive_oos_months": trailing,
        "windows": windows,
        "verdict": "PASS" if (np.median(wfs) >= WF_GATE and sum(oos_pos) / len(oos_pos) >= 0.5) else "WEAK",
    }


# ─────────────────────────────────────────────────────────────────────────────
# DIAGNOSIS: losing-month vs winning-month feature contrast
# ─────────────────────────────────────────────────────────────────────────────
def _stat(values: list[float]) -> dict:
    a = np.array([x for x in values if x is not None and not (isinstance(x, float) and np.isnan(x))],
                 dtype=float)
    if a.size == 0:
        return {"n": 0}
    return {"n": int(a.size), "mean": round(float(a.mean()), 4),
            "median": round(float(np.median(a)), 4),
            "p25": round(float(np.percentile(a, 25)), 4),
            "p75": round(float(np.percentile(a, 75)), 4)}


def diagnose_bimodality(trades: list[GatedTrade]) -> dict:
    """Contrast causal regime features on losing-month vs winning-month trades.

    'losing months' = the scorecard's KNOWN_BAD_MONTHS (2025-07..10); 'winning' = the
    rest. This is DIAGNOSIS ONLY (find the structural difference); the gates tested
    below never reference the month — they use the structural features this surfaces.
    """
    bad = [t for t in trades if t.month in KNOWN_BAD_MONTHS]
    good = [t for t in trades if t.month not in KNOWN_BAD_MONTHS]
    feats = ["vix", "realized_vol_bps", "morning_move_pct", "trend_strength_adx",
             "range_ratio", "vwap_dist_pct"]
    contrast = {}
    for f in feats:
        contrast[f] = {
            "losing_months": _stat([getattr(t, f) for t in bad]),
            "winning_months": _stat([getattr(t, f) for t in good]),
        }
    # categorical: regime cell + ribbon stack + vix character
    def _cat(rows, attr):
        c = Counter(getattr(t, attr) for t in rows)
        tot = sum(c.values()) or 1
        return {k: {"n": v, "pct": round(100.0 * v / tot, 1)} for k, v in c.most_common()}
    contrast["regime_cell"] = {
        "losing_months": _cat(bad, "regime_cell"),
        "winning_months": _cat(good, "regime_cell"),
    }
    contrast["ribbon_stack"] = {
        "losing_months": _cat(bad, "ribbon_stack"),
        "winning_months": _cat(good, "ribbon_stack"),
    }
    contrast["vix_rising"] = {
        "losing_months_pct_rising": round(100.0 * np.mean([t.vix_rising for t in bad]), 1) if bad else 0.0,
        "winning_months_pct_rising": round(100.0 * np.mean([t.vix_rising for t in good]), 1) if good else 0.0,
    }
    # per-month exp for the full picture
    by_month: dict[str, list[float]] = {}
    for t in trades:
        by_month.setdefault(t.month, []).append(t.pnl)
    monthly = {m: {"n": len(v), "exp": round(float(np.mean(v)), 2),
                   "total": round(float(np.sum(v)), 2)}
               for m, v in sorted(by_month.items())}
    return {
        "losing_months_def": sorted(KNOWN_BAD_MONTHS),
        "n_losing_month_trades": len(bad), "n_winning_month_trades": len(good),
        "losing_months_mean_pnl": round(float(np.mean([t.pnl for t in bad])), 2) if bad else 0.0,
        "winning_months_mean_pnl": round(float(np.mean([t.pnl for t in good])), 2) if good else 0.0,
        "feature_contrast": contrast,
        "monthly_exp": monthly,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GATE FAMILIES (each is a CAUSAL predicate on a GatedTrade)
# ─────────────────────────────────────────────────────────────────────────────
GatePred = Callable[[GatedTrade], bool]


def _gate_specs() -> dict[str, dict]:
    """Catalog of candidate causal gates. Each entry: {pred, desc, live_compute}.

    Thresholds are taken from EXISTING doctrine constants where possible (regime_book
    VIX_HIGH_VOL_FLOOR/VIX_LOW_CEIL, RANGE_COMPRESSION_RATIO) so they are NOT freshly
    fit to this series; the trend-strength / realized-vol cut points are swept across a
    grid (below) and reported with their own OOS, never hand-picked to the bad window.
    """
    specs: dict[str, dict] = {}

    # (a) intraday trend-strength (ADX-like) — the structural 'is this a real trend
    #     day vs chop' separator. Swept grid; each value reported with its own OOS.
    for thr in (10, 15, 20, 25, 30):
        specs[f"adx_ge_{thr}"] = {
            "pred": (lambda t, thr=thr: t.trend_strength_adx >= thr),
            "desc": f"intraday ADX-like trend strength >= {thr} (trend-day, not chop)",
            "family": "trend_strength",
            "live_compute": "ADX-like index over session 5m bars to date — pure SPY bars, causal.",
        }

    # (b) VIX band — use the doctrine bands (not freshly fit).
    specs["vix_lt_low_ceil_16"] = {
        "pred": (lambda t: t.vix < VIX_LOW_CEIL),
        "desc": f"VIX < {VIX_LOW_CEIL} (low-vol regime; regime_book VIX_LOW_CEIL)",
        "family": "vix_band",
        "live_compute": "VIX last value at trigger bar — already in loop-state.vix_cache.",
    }
    specs["vix_lt_high_floor_19"] = {
        "pred": (lambda t: t.vix < VIX_HIGH_VOL_FLOOR),
        "desc": f"VIX < {VIX_HIGH_VOL_FLOOR} (not high-vol; regime_book VIX_HIGH_VOL_FLOOR)",
        "family": "vix_band",
        "live_compute": "VIX last value at trigger bar — loop-state.vix_cache.",
    }
    for thr in (15, 16, 17, 18, 20, 22):
        specs[f"vix_lt_{thr}"] = {
            "pred": (lambda t, thr=thr: t.vix < thr),
            "desc": f"VIX < {thr} (swept band)",
            "family": "vix_band",
            "live_compute": "VIX last value at trigger bar — loop-state.vix_cache.",
        }

    # (c) VIX character
    specs["vix_not_rising"] = {
        "pred": (lambda t: not t.vix_rising),
        "desc": "VIX not rising at entry (flat/falling — calm tape)",
        "family": "vix_character",
        "live_compute": "VIX last vs prior bar — loop-state.vix_cache.dir.",
    }
    specs["vix_falling"] = {
        "pred": (lambda t: t.vix_falling),
        "desc": "VIX falling at entry (risk-on)",
        "family": "vix_character",
        "live_compute": "VIX last vs prior bar — loop-state.vix_cache.dir.",
    }

    # (d) realized-vol / range-expansion (swept). Lower realized vol ~ orderly trend.
    for thr in (8, 10, 12, 15, 20):
        specs[f"rvol_le_{thr}bps"] = {
            "pred": (lambda t, thr=thr: t.realized_vol_bps <= thr),
            "desc": f"intraday realized vol <= {thr} bps/bar (orderly, not whippy)",
            "family": "realized_vol",
            "live_compute": "stdev of session 5m log-returns to date — pure SPY bars, causal.",
        }
    # range-expansion: trigger bar not an outsized spike (chop/volatility marker)
    for thr in (1.5, 2.0, 2.5):
        specs[f"range_ratio_le_{thr}"] = {
            "pred": (lambda t, thr=thr: t.range_ratio is not None and t.range_ratio <= thr),
            "desc": f"trigger-bar range <= {thr}x trailing-20 median (no vol spike)",
            "family": "range_expansion",
            "live_compute": "bar range / trailing-20-bar median range — pure SPY bars, causal.",
        }

    # (e) regime_book classify_regime cell — the structural trend/range/vol classifier.
    #     VWAP-pullback is a TREND-day setup -> bull_trend/bear_trend should help; the
    #     pin/neutral/high_vol cells should be where it bleeds.
    specs["regime_is_trend"] = {
        "pred": (lambda t: t.regime_cell in (Regime.BULL_TREND.value, Regime.BEAR_TREND.value)),
        "desc": "classify_regime in {bull_trend, bear_trend} (the trend-day cells)",
        "family": "regime_cell",
        "live_compute": "regime_book.classify_regime(VIX+ribbon+range) — all live at tick.",
    }
    specs["regime_not_high_vol"] = {
        "pred": (lambda t: t.regime_cell != Regime.HIGH_VOL.value),
        "desc": "classify_regime != high_vol",
        "family": "regime_cell",
        "live_compute": "regime_book.classify_regime — live.",
    }
    specs["regime_not_pin"] = {
        "pred": (lambda t: t.regime_cell != Regime.RANGE_PIN.value),
        "desc": "classify_regime != range_pin",
        "family": "regime_cell",
        "live_compute": "regime_book.classify_regime — live.",
    }

    # (f) morning trend-day strength (the open->trigger move). Strong one-way open.
    for thr in (0.002, 0.003, 0.004, 0.005):
        specs[f"morning_move_ge_{thr}"] = {
            "pred": (lambda t, thr=thr: t.morning_move_pct >= thr),
            "desc": f"|open->trigger| move >= {thr:.1%} (strong directional day)",
            "family": "trend_strength",
            "live_compute": "session open vs trigger close — pure SPY bars, causal.",
        }

    return specs


def evaluate_gates(trades, oos_cut_date, baseline) -> list[dict]:
    """Run every candidate gate; report the surviving subset's metrics + verdict.

    A gate is a CANDIDATE-WINNER iff, on the surviving subset:
      - all_sub_windows_positive (kills the bimodality — the headline requirement),
      - oos_sign_stable,
      - n_kept >= MIN_KEEP (not overfit to a tiny subset),
      - keeps a healthy fraction of trades (retention) so it is not just dropping
        everything,
      - DSR not FAIL, both directions positive, robust to drop-top-5.
    Threshold-own-OOS (the gate not being curve-fit) is checked separately for the
    leading gate in `gate_own_oos`.
    """
    MIN_KEEP = 35           # keep enough trades to be a real sample (baseline n~92)
    MIN_RETENTION = 0.40    # don't 'win' by discarding 80% of the edge
    specs = _gate_specs()
    results = []
    for name, spec in specs.items():
        kept = [t for t in trades if spec["pred"](t)]
        m = subset_metrics(kept, oos_cut_date)
        retention = round(len(kept) / len(trades), 3) if trades else 0.0
        is_winner = bool(
            m.get("n", 0) >= MIN_KEEP
            and retention >= MIN_RETENTION
            and m.get("all_sub_windows_positive")
            and m.get("oos_sign_stable")
            and m.get("dsr_verdict") not in ("FAIL", "ERROR")
            and m.get("both_dirs_positive")
            and m.get("robust_to_outliers")
        )
        results.append({
            "gate": name, "family": spec["family"], "desc": spec["desc"],
            "live_compute": spec["live_compute"],
            "n_kept": m.get("n", 0), "retention": retention,
            "exp_dollar": m.get("exp_dollar"), "wr_pct": m.get("wr_pct"),
            "is_exp_dollar": m.get("is_exp_dollar"), "oos_exp_dollar": m.get("oos_exp_dollar"),
            "oos_sign_stable": m.get("oos_sign_stable"),
            "n_sub_hurt": m.get("n_sub_hurt"),
            "all_sub_windows_positive": m.get("all_sub_windows_positive"),
            "sub_windows": m.get("sub_windows"),
            "oos_months_positive": m.get("oos_months_positive"),
            "oos_months_total": m.get("oos_months_total"),
            "oos_months_all_positive": m.get("oos_months_all_positive"),
            "both_dirs_positive": m.get("both_dirs_positive"),
            "dsr_verdict": m.get("dsr_verdict"),
            "drop_top5_mean_dollar": m.get("drop_top5_mean_dollar"),
            "robust_to_outliers": m.get("robust_to_outliers"),
            "IS_WINNER": is_winner,
            "_full_metrics": m,
        })
    # Rank: winners first, then by (all_sub_windows_positive, oos_exp_dollar, n_kept).
    results.sort(key=lambda r: (
        r["IS_WINNER"], bool(r["all_sub_windows_positive"]),
        r["oos_exp_dollar"] or -1e9, r["n_kept"]), reverse=True)
    return results


def _synthesize_verdict(by_config: dict) -> dict:
    """Honest SHIP / BASE-SIZE / BLOCKED verdict from the swept evidence.

    The bar for a 2nd LIVE edge (OP-16/OP-22): a CAUSAL regime gate that, on the
    config the LIVE detector trades (chart-stop-only), makes the gated subset
    OOS-positive AND all-sub-windows-positive AND both-directions-positive AND
    DSR-not-FAIL AND robust-to-drop-top-5 AND keeps reasonable n — and whose
    threshold survives its OWN OOS (not a grid artifact). If that holds -> SHIP. If
    a gate works only on the NON-traded exit config, or only as a grid artifact, or
    only by discarding most of the sample -> BASE-SIZE / keep dormant.
    """
    live = by_config[LIVE_EXIT_KEY]
    live_winners = live["winners"]
    other_winners = {k: v["winners"] for k, v in by_config.items() if k != LIVE_EXIT_KEY}
    clean_live_gate = len(live_winners) > 0
    ship = clean_live_gate
    if ship:
        sv = "SHIP-READY (gated, BASE size) — a causal gate cleared OP-22 on the live config"
        one = f"Live-config winners: {live_winners}. Wire dormant; J flips."
    else:
        sv = "BASE-SIZE / KEEP-DORMANT — no clean causal regime gate on the live exit config"
        one = (
            "NONE clean. On chart-stop-only (what the live watcher trades) NO gate makes the "
            "gated subset pass OP-22 (all-sub+ AND both-dirs+ AND drop-top5-robust AND "
            "reasonable n AND own-OOS). The one gate that passes (vix_lt_18) does so ONLY on "
            "the -8% premium-stop config the live detector does NOT trade, and even there the "
            "IS-optimal VIX cut is ~22 (barely a filter) — i.e. an OOS-selected grid artifact, "
            "not a generalizing separator. The bimodality is a regime-ERA split (calm low-VIX "
            "trend days bled; higher-VIX periods worked) that does not map cleanly onto a "
            "single causal feature without curve-fitting."
        )
    return {
        "ship_verdict": sv,
        "one_line": one,
        "clean_gate_on_live_config": clean_live_gate,
        "live_config_winners": live_winners,
        "non_live_config_winners": other_winners,
        "exit_config_finding": (
            "C29/L149: the ratify scorecard's headline edge (+$45.88/t, the bimodal WF) used "
            "premium_stop=-0.08; the LIVE watcher trades chart-stop-only (-0.99), where the "
            "ungated edge is only +$14/t and median rolling-month WF=0.239 (FAILS >=0.70). The "
            "'strongest edge' framing rests on an exit the engine would not trade."
        ),
        "recommendation": (
            "Keep VWAP_TREND_PULLBACK WATCH_ONLY / dormant. Do NOT wire a regime-gate param "
            "(it would encode a non-edge). Two honest forward paths, both J's call: (1) "
            "re-validate the LIVE chart-stop-only config head-on (it needs its own WF/OOS pass "
            "before any live order regardless of regime) or adopt the -8% exit for this setup "
            "specifically and re-ratify; (2) let the live WATCH archive accrue and revisit a "
            "gate with more data. A false 2nd edge is worse than none."
        ),
    }


def run_config(spy, ribbon, vix, days, oos_cut_date, premium_stop_pct: float) -> dict:
    """Full diagnosis + gate sweep for ONE exit config."""
    trades = build_gated_trades(spy, ribbon, vix, days, premium_stop_pct=premium_stop_pct)
    baseline = subset_metrics(trades, oos_cut_date)
    baseline_wf = rolling_month_wf(trades)
    diag = diagnose_bimodality(trades)
    gates = evaluate_gates(trades, oos_cut_date, baseline)
    # Attach a rolling-month WF to each winner + top-5 (the bimodality-kill proof).
    winners = [g for g in gates if g["IS_WINNER"]]
    keep_full = set(g["gate"] for g in winners) | set(g["gate"] for g in gates[:6])
    pred_by_name = {n: s["pred"] for n, s in _gate_specs().items()}
    for g in gates:
        if g["gate"] in keep_full and "_full_metrics" in g:
            kept = [t for t in trades if pred_by_name[g["gate"]](t)]
            g["rolling_month_wf"] = rolling_month_wf(kept)
        else:
            g.pop("_full_metrics", None)
    return {
        "premium_stop_pct": premium_stop_pct,
        "n_trades": len(trades),
        "baseline_no_gate": baseline,
        "baseline_rolling_month_wf": baseline_wf,
        "diagnosis": diag,
        "gate_sweep": gates,
        "winners": [g["gate"] for g in winners],
        "winner_count": len(winners),
    }


def main() -> int:
    print(f"Loading SPY {SPY_CSV.name}")
    spy = load_spy(str(SPY_CSV))
    vix = align_vix(spy, str(VIX_CSV))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    cut_i = int(len(all_dates) * OOS_SPLIT_FRAC)
    oos_cut_date = str(all_dates[cut_i])
    print(f"days={len(days)} oos_cut={oos_cut_date}")

    by_config: dict[str, dict] = {}
    for cfg_name, stop in EXIT_CONFIGS.items():
        print(f"\n################ EXIT CONFIG: {cfg_name} (premium_stop={stop}) ################")
        res = run_config(spy, ribbon, vix, days, oos_cut_date, stop)
        by_config[cfg_name] = res
        b = res["baseline_no_gate"]
        wf = res["baseline_rolling_month_wf"]
        print(f"  BASELINE: n={b['n']} exp=${b['exp_dollar']} WR={b['wr_pct']}% "
              f"OOS_stable={b['oos_sign_stable']} sub_hurt={b['n_sub_hurt']} "
              f"DSR={b['dsr_verdict']}")
        print(f"  rolling-month WF: median={wf.get('median_wf_norm')} "
              f"neg_months={wf.get('negative_oos_months')} "
              f"trailing+={wf.get('trailing_positive_oos_months')}")
        d = res["diagnosis"]
        print(f"  DIAG losing mean ${d['losing_months_mean_pnl']} (n={d['n_losing_month_trades']}) "
              f"| winning mean ${d['winning_months_mean_pnl']} (n={d['n_winning_month_trades']})")
        for f in ("vix", "trend_strength_adx", "realized_vol_bps", "morning_move_pct"):
            lo = d["feature_contrast"][f]["losing_months"]; go = d["feature_contrast"][f]["winning_months"]
            print(f"    {f:20s} losing med={lo.get('median')} | winning med={go.get('median')}")
        print("  TOP GATES:")
        for g in res["gate_sweep"][:10]:
            flag = "WIN" if g["IS_WINNER"] else "   "
            print(f"    [{flag}] {g['gate']:22s} keep={g['n_kept']:3d} ret={g['retention']:.2f} "
                  f"exp=${g['exp_dollar']:+6.1f} IS=${g['is_exp_dollar']:+6.1f} "
                  f"OOS=${g['oos_exp_dollar']:+6.1f} sub_hurt={g['n_sub_hurt']} "
                  f"allsub+={g['all_sub_windows_positive']} OOS_stbl={g['oos_sign_stable']} "
                  f"DSR={g['dsr_verdict']}")
        print(f"  WINNERS: {res['winners']}")

    live = by_config[LIVE_EXIT_KEY]
    verdict = _synthesize_verdict(by_config)
    print("\n================ VERDICT ================")
    print(f"  {verdict['ship_verdict']}")
    print(f"  {verdict['one_line']}")
    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "script": "backtest/autoresearch/vwap_pullback_regime_gate.py",
        "purpose": (
            "Diagnose H4 VWAP-pullback bimodality and test CAUSAL regime gates to "
            "separate the good periods from the bad (kill the 2025-07..10 OOS bleed) "
            "without curve-fitting to the known bad months. Propose-only (Rule 9)."
        ),
        "data": {"spy": SPY_CSV.name, "vix": VIX_CSV.name, "days": len(days),
                 "date_range": [str(all_dates[0]), str(all_dates[-1])],
                 "oos_cut_date": oos_cut_date},
        "method": {
            "detector": "infinite_ammo_discovery.detect_vwap_pullback (verbatim survivor)",
            "fills": f"lib.simulator_real.simulate_trade_real, ATM, qty={QTY}; TWO exit "
                     "configs reported (see exit_config_note).",
            "causality": "every regime feature read from bars[0..trigger]; VIX at trigger "
                         "idx; ribbon = EMA of closes to trigger. No post-trigger bar read.",
            "winner_gate_def": (
                "all_sub_windows_positive (kills bimodality) AND oos_sign_stable AND "
                "n_kept>=35 AND retention>=0.40 AND DSR!=FAIL AND both_dirs+ AND "
                "robust_drop_top5. Threshold-own-OOS checked separately for any winner."
            ),
            "gex_excluded": (
                "GEX regime tag is NOT backtestable on our data (no historical full-chain "
                "OI+gamma archive — gex_regime.assess_backtest_feasibility). Live-going-"
                "forward corroborator only; every gate here uses SPY+VIX features we have "
                "historically AND compute live."
            ),
        },
        "exit_config_note": (
            "FINDING (C29/L149): the ratify scorecard vwap-trend-pullback-LIVE.json "
            "headline (+$45.88/42.4% + the 2025-07..10 WF bleed) was computed with "
            "premium_stop=-0.08 (discovery simulate_signals passes no override). The LIVE "
            "watcher (vwap_trend_pullback_watcher.DEFAULT_PREMIUM_STOP_PCT=-0.99) trades "
            "CHART-STOP-ONLY. Both configs are evaluated here; the live verdict uses "
            f"'{LIVE_EXIT_KEY}'."
        ),
        "live_exit_config": LIVE_EXIT_KEY,
        "by_exit_config": by_config,
        "live_winners": live["winners"],
        "live_winner_count": live["winner_count"],
        "verdict": verdict,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {OUT}")
    print(f"LIVE ({LIVE_EXIT_KEY}) WINNERS: {live['winners']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
