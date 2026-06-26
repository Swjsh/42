"""REGIME-SWITCH BOOK — does regime ALLOCATION between two real-fills sleeves beat
directional-ALWAYS?

THE #3 THESIS (research question this harness answers): don't GATE per-trade and don't
change STRUCTURE per-edge — ALLOCATE between two CLASSES by REGIME. Deploy the directional
theta-PAYER (vwap_continuation) when the market TRENDS; deploy the theta-HARVESTER (iron
condor) when it CHOPS. The switch's value is right-tool-for-the-regime, NOT either sleeve
being a selection edge.

WHAT IT REUSES BYTE-FOR-BYTE (NO edits to any watcher / params / risk_gate / orchestrator /
heartbeat / simulator_real / simulator_credit — money-path guard):
  TREND sleeve (directional long):
    - the LIVE detector: autoresearch._edgehunt_vwap_continuation.detect_signals
      (== j_daily_pattern_ratify.detect_j_vwap_continuation == the live watcher), called
      EXACTLY as recency_check.py does (breakout_only=False, put_needs_rising_vix=False).
    - the real-OPRA directional fill path lib.simulator_real.simulate_trade_real, with the
      validated LIVE tier config: strike_offset=0 (ATM, Safe-2), premium_stop_pct=-0.08,
      qty=3, v15 default exits — byte-for-byte recency_check.simulate_set.
    - the strike pickers _strike_from_spot / _nearest_cached_strike (snap radius 4).
  CHOP sleeve (iron condor, the LEAD config from PIVOT-PREMIUM-SELLING-SCORECARD.md):
    - lib.simulator_credit.simulate_credit_trade + lib.multileg_structures.build_legs,
      called EXACTLY as _pivot_premium_finalize.run_real does, with the LEAD cell:
      IC / 10:30 ET / short_offset=2 / wing=2 / pt_frac=0.50 / stop_mult=1.5 / commission $0.65.
    - the pivot harness helpers _load_spy_master / _spot_and_decision / _build_variant_legs /
      _option_cache_dates (so the condor sleeve is identical to the validated scorecard run).

THE CAUSAL REGIME CLASSIFIER (label each trading day as-of the MORNING decision; only data
strictly <= the decision bar; ET localized per L165/L61):
  Features (ALL look-ahead-safe):
    f1  spy_trend_strength_20d : |close - sma20| / sma20 over the prior 20 DAILY closes
                                 (prior closes only; today excluded). The diagnosis feature.
    f2  vix_spot              : VIX as-of 09:30 ET (causal).
    f3  vix_slope_5bar        : VIX[09:30] - VIX[~5 bars earlier] (causal).
    f4  overnight_range_pct_atr: MES overnight range (18:00 prior -> 09:30 today, ET) as a
                                 fraction of the 14-day MES daily-range ATR (prior days only).
                                 The Sunday-fresh-angles feature.
    f5  prior_realized_range_pct_atr : prior RTH session range / 14-day SPY range ATR (causal;
                                 today's realized range is NOT knowable at the morning decision,
                                 so we use the PRIOR day's realized range as the causal proxy).
  Simple, robust rule (NOT ML):
    TREND  = strong 20d trend AND adequate overnight range (the market is moving with conviction)
    CHOP   = flat 20d trend AND compressed overnight range / compressed VIX (the market is coiled)
    NEUTRAL= everything else.
  Thresholds are PERCENTILE-based over the IN-SAMPLE distribution (terciles) so the split is
  not degenerate (the dead range/ATR band that produced 10/124/218 is explicitly rejected).

THE SWITCHED-BOOK HARNESS: for each day classify regime as-of the morning decision, then run
the MATCHING sleeve's real-fills sim and combine into ONE daily-equity book:
    TREND   -> directional vwap_continuation (ATM, the live tier)
    CHOP    -> iron condor (the LEAD config)
    NEUTRAL -> a documented choice; we test 3 variants {directional, condor, abstain}.
Compared head-to-head vs DIRECTIONAL-ALWAYS (the current live approach).

THE BAR (reported, not silently asserted):
  (1) risk-adjusted return UP vs directional-always (L175: Sharpe/Sortino up, maxDD down)
  (2) recency-25-trading-day chop drawdown REDUCED / flipped
  (3) no-regression: the days it SWITCHES must net-improve vs directional-alone on those days
  (4) OOS-positive.

HONEST CAVEATS (carried in the output, per C1/C3/C7/L172):
  - the condor sleeve is NULL-FAILING-AS-STANDALONE (generic theta, not strike-selection alpha,
    PIVOT scorecard gate-6 FAIL) AND data-constrained by the +/-$5 OPRA band / narrow $2 wings.
    A SHIP needs the wide-band condor validation (direction 4b) FIRST. This harness answers the
    RESEARCH question (does regime-allocation beat directional-alone?); a YES makes 4b worth the
    heavy fetch. It is NOT a ship signal on its own.
  - real OPRA fills only (C1 — the WR authority). per-trade EXPECTANCY, not WR (OP-14).
  - RESEARCH ONLY; no live edit, no orders (Sunday/market-closed money-path guard).

Run (offline, $0):
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_regime_switch_book.py --smoke
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_regime_switch_book.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
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

import numpy as np   # noqa: E402
import pandas as pd  # noqa: E402

# ── TREND sleeve (directional long) — reuse the recency_check path byte-for-byte ──
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    detect_signals as detect_vwap_continuation,
)
from lib.ribbon import compute_ribbon                  # noqa: E402
from lib.simulator_real import simulate_trade_real     # noqa: E402

# ── CHOP sleeve (iron condor) — reuse the pivot finalize path byte-for-byte ──
from lib import simulator_credit as sc                 # noqa: E402
from lib.multileg_structures import legs_in_band       # noqa: E402
import autoresearch._pivot_premium_selling as P        # noqa: E402

DATA = REPO / "data"
FUT = DATA / "futures"
OUT_DIR = REPO / "autoresearch" / "_state" / "regime_switch_book"

# ── directional LIVE-tier config (== recency_check.py) ───────────────────────────
DIR_STRIKE_OFFSET = 0          # ATM (Safe-2, the live tier)
DIR_PREMIUM_STOP_PCT = -0.08   # the OPTIMAL tight stop
DIR_QTY = 3
DIR_MAX_STRIKE_STEPS = 4

# ── iron-condor LEAD config (== PIVOT-PREMIUM-SELLING-SCORECARD.md LEAD cell) ─────
IC_STRUCTURE = "IC"
IC_ENTRY_TIME = dt.time(10, 30)
IC_SHORT_OFFSET = 2
IC_WING = 2
IC_PT_FRAC = 0.50
IC_STOP_MULT = 1.5
IC_COMMISSION = 0.65

# ── windows ──────────────────────────────────────────────────────────────────────
OOS_START = dt.date(2026, 1, 1)
RECENCY_N = 25                 # canonical last-25-TRADING-DAY chop drawdown window
TREASURY_RF = 0.0              # excess-return offset for Sharpe (0DTE intraday, ~0)


# ═════════════════════════════════════════════════════════════════════════════════
#  REGIME CLASSIFIER  (causal — only data strictly <= the morning decision bar)
# ═════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class RegimeFeatures:
    date: dt.date
    trend_strength_20d: Optional[float]
    vix_spot: Optional[float]
    vix_slope_5bar: Optional[float]
    overnight_range_pct_atr: Optional[float]
    prior_realized_range_pct_atr: Optional[float]


def _load_mes_overnight_ranges() -> dict[dt.date, float]:
    """MES overnight range (prior 18:00 ET -> today 09:30 ET) per RTH date, look-ahead-safe.

    The overnight session that PRECEDES a trading day's 09:30 open belongs to that day's
    morning decision (all bars are strictly before 09:30). We bucket every MES 1m bar with
    time in [18:00, 23:59] onto the NEXT calendar trading day, and bars in [00:00, 09:30)
    onto the SAME calendar day, then take high-low of that overnight block.
    """
    df = pd.read_csv(FUT / "MES_1m_continuous.csv")
    ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df = df.assign(_et=ts)
    df["d"] = df["_et"].dt.date
    df["tm"] = df["_et"].dt.time
    df["hm"] = df["_et"].dt.hour * 60 + df["_et"].dt.minute
    open_min = 9 * 60 + 30
    evening = df[df["hm"] >= 18 * 60].copy()       # 18:00..23:59 -> next session
    morning = df[df["hm"] < open_min].copy()       # 00:00..09:29 -> same session

    # map evening bars to the NEXT calendar day present in the SPY/option universe;
    # we approximate "next session" as next calendar date here, refined by caller's
    # trading-day list (a Friday-evening block maps to Monday once we intersect days).
    evening["session"] = evening["d"] + pd.Timedelta(days=1)
    morning["session"] = morning["d"]
    blocks = pd.concat([
        evening[["session", "high", "low"]],
        morning[["session", "high", "low"]],
    ], ignore_index=True)
    grp = blocks.groupby("session")
    rng = (grp["high"].max() - grp["low"].min())
    return {d: float(v) for d, v in rng.items()}


def _mes_daily_range_atr(n: int = 14) -> dict[dt.date, float]:
    """14-day SMA of MES RTH daily (high-low) range, as-of PRIOR days only (causal)."""
    df = pd.read_csv(FUT / "MES_1m_continuous.csv")
    ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df = df.assign(_et=ts)
    df["d"] = df["_et"].dt.date
    df["hm"] = df["_et"].dt.hour * 60 + df["_et"].dt.minute
    rth = df[(df["hm"] >= 9 * 60 + 30) & (df["hm"] < 16 * 60)]
    daily = rth.groupby("d").agg(hi=("high", "max"), lo=("low", "min"))
    daily["rng"] = daily["hi"] - daily["lo"]
    daily = daily.sort_index()
    # ATR as-of a day = mean of the PRIOR n daily ranges (shift(1) excludes today).
    daily["atr"] = daily["rng"].shift(1).rolling(n, min_periods=max(3, n // 2)).mean()
    return {d: (float(a) if pd.notna(a) else math.nan) for d, a in daily["atr"].items()}


def compute_regime_features(spy: pd.DataFrame, vix: pd.Series,
                            trading_days: list[dt.date]) -> dict[dt.date, RegimeFeatures]:
    """Per-day causal feature bundle, indexed by RTH date.

    spy: _normalize_spy output (tz-naive ET, cols date/t/minute/close, global index).
    vix: _align_vix output (aligned to spy rows, integer-indexed 0..len-1).
    """
    # --- daily SPY closes (last RTH bar each day) for the 20-day trend feature ---
    rth_mask = (spy["t"] >= dt.time(9, 30)) & (spy["t"] < dt.time(16, 0))
    rth = spy[rth_mask]
    daily_close = rth.groupby("date")["close"].last()
    daily_close = daily_close.sort_index()
    # SMA20 of PRIOR closes (shift(1) so today's close is excluded -> causal at 09:30).
    sma20_prior = daily_close.shift(1).rolling(20, min_periods=20).mean()

    # --- prior RTH realized range / SPY 14d range ATR (causal) ---
    daily_hi = rth.groupby("date")["high"].max().sort_index()
    daily_lo = rth.groupby("date")["low"].min().sort_index()
    daily_rng = (daily_hi - daily_lo)
    spy_atr = daily_rng.shift(1).rolling(14, min_periods=7).mean()
    prior_rng = daily_rng.shift(1)   # PRIOR day's realized range (knowable this morning)

    # --- per-day VIX spot + 5-bar slope as-of the 09:30 open bar ---
    spy_reset = spy.reset_index(drop=True)
    vix_arr = vix.to_numpy()
    open_idx_by_day: dict[dt.date, int] = {}
    for d, day in spy_reset.groupby("date"):
        oi = day[day["t"] >= dt.time(9, 30)]
        if not oi.empty:
            open_idx_by_day[d] = int(oi.index[0])

    mes_on = _load_mes_overnight_ranges()
    mes_atr = _mes_daily_range_atr(14)

    feats: dict[dt.date, RegimeFeatures] = {}
    close_map = {d: float(c) for d, c in daily_close.items()}
    for d in trading_days:
        # f1 trend strength: |close_prior_session_basis|... use PRIOR close vs prior SMA20.
        # As-of 09:30 we know yesterday's close + the 20d SMA of closes up to yesterday.
        c_prior = daily_close.shift(1).get(d, math.nan)
        s_prior = sma20_prior.get(d, math.nan)
        trend = (abs(c_prior - s_prior) / s_prior) if (pd.notna(c_prior) and pd.notna(s_prior)
                                                       and s_prior) else None

        oi = open_idx_by_day.get(d)
        if oi is not None and oi < len(vix_arr):
            vix_spot = float(vix_arr[oi]) if vix_arr[oi] > 0 else None
            j = oi - 5
            vix_slope = (float(vix_arr[oi] - vix_arr[j])
                         if j >= 0 and vix_arr[oi] > 0 and vix_arr[j] > 0 else None)
        else:
            vix_spot = vix_slope = None

        on_rng = mes_on.get(d)
        on_atr = mes_atr.get(d, math.nan)
        on_pct = (on_rng / on_atr) if (on_rng is not None and pd.notna(on_atr) and on_atr) else None

        pr = prior_rng.get(d, math.nan)
        pa = spy_atr.get(d, math.nan)
        pr_pct = (float(pr) / float(pa)) if (pd.notna(pr) and pd.notna(pa) and pa) else None

        feats[d] = RegimeFeatures(
            date=d, trend_strength_20d=trend, vix_spot=vix_spot, vix_slope_5bar=vix_slope,
            overnight_range_pct_atr=on_pct, prior_realized_range_pct_atr=pr_pct)
    return feats


@dataclass(frozen=True)
class RegimeThresholds:
    """Tercile cut-points learned from the IN-SAMPLE feature distribution (causal: IS only)."""
    trend_hi: float       # >= -> "strong trend"
    trend_lo: float       # <= -> "flat trend"
    on_hi: float          # >= -> "adequate overnight range"
    on_lo: float          # <= -> "compressed overnight range"
    vix_lo: float         # <= -> "compressed VIX"


def _tercile(vals: list[float]) -> tuple[float, float]:
    a = np.array([v for v in vals if v is not None and not math.isnan(v)], float)
    if a.size < 6:
        return (float("inf"), float("-inf"))
    return float(np.quantile(a, 1 / 3)), float(np.quantile(a, 2 / 3))


def learn_thresholds(feats: dict[dt.date, RegimeFeatures],
                     is_days: list[dt.date]) -> RegimeThresholds:
    """Learn tercile cut-points from IN-SAMPLE days ONLY (no OOS leakage)."""
    sub = [feats[d] for d in is_days if d in feats]
    tr_lo, tr_hi = _tercile([f.trend_strength_20d for f in sub])
    on_lo, on_hi = _tercile([f.overnight_range_pct_atr for f in sub])
    vix_lo, _vix_hi = _tercile([f.vix_spot for f in sub])
    return RegimeThresholds(trend_hi=tr_hi, trend_lo=tr_lo, on_hi=on_hi, on_lo=on_lo,
                            vix_lo=vix_lo)


def classify_day(f: RegimeFeatures, th: RegimeThresholds) -> str:
    """Causal regime label for one day. Simple robust rule (not ML).

    TREND  = strong 20d trend AND adequate overnight range (conviction move).
    CHOP   = flat 20d trend AND (compressed overnight range OR compressed VIX) (coiled).
    NEUTRAL= otherwise (incl. days missing a required feature).
    """
    trend = f.trend_strength_20d
    onr = f.overnight_range_pct_atr
    vix = f.vix_spot
    if trend is None or onr is None:
        return "NEUTRAL"
    strong_trend = trend >= th.trend_hi
    flat_trend = trend <= th.trend_lo
    adequate_on = onr >= th.on_hi
    compressed_on = onr <= th.on_lo
    compressed_vix = (vix is not None and vix <= th.vix_lo)
    if strong_trend and adequate_on:
        return "TREND"
    if flat_trend and (compressed_on or compressed_vix):
        return "CHOP"
    return "NEUTRAL"


# ═════════════════════════════════════════════════════════════════════════════════
#  SLEEVE SIMS  (byte-for-byte reuse — directional + condor)
# ═════════════════════════════════════════════════════════════════════════════════
def directional_pnl_by_day(spy: pd.DataFrame, vix: pd.Series) -> dict[dt.date, float]:
    """Run the LIVE directional sleeve (vwap_continuation, ATM, -8% stop) on real OPRA fills.
    Returns {date: total directional P&L that day}. Mirrors recency_check.simulate_set."""
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    signals = detect_vwap_continuation(days, vix, breakout_only=False,
                                       put_needs_rising_vix=False)
    by_day: dict[dt.date, float] = defaultdict(float)
    n_fill = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - DIR_STRIKE_OFFSET if sg.side == "P" else atm + DIR_STRIKE_OFFSET
        strike = _nearest_cached_strike(d, target, sg.side, DIR_MAX_STRIKE_STEPS)
        if strike is None:
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=DIR_QTY, setup="vwap_continuation_ATM", strike_override=strike,
            entry_vix=entry_vix, premium_stop_pct=DIR_PREMIUM_STOP_PCT)
        if fill is None or fill.dollar_pnl is None:
            continue
        by_day[d] += float(fill.dollar_pnl)
        n_fill += 1
    return dict(by_day)


def condor_pnl_by_day(spy_pivot: pd.DataFrame, cache_days: set,
                      day_list: list[dt.date]) -> dict[dt.date, float]:
    """Run the iron-condor LEAD sleeve on real OPRA fills. Returns {date: IC P&L}.
    Mirrors _pivot_premium_finalize.run_real EXACTLY (same LEAD cell)."""
    by_day: dict[dt.date, float] = {}
    for d in day_list:
        if d not in cache_days:
            continue
        spy_day = spy_pivot[spy_pivot["date"] == d]
        if spy_day.empty:
            continue
        decision_dt, spot, _ = P._spot_and_decision(spy_day, IC_ENTRY_TIME)
        if decision_dt is None or spot is None or spot <= 0:
            continue
        legs = P._build_variant_legs(IC_STRUCTURE, spot, IC_SHORT_OFFSET, IC_WING)
        if not legs_in_band(legs, spot, half_width=5):
            continue
        f = sc.simulate_credit_trade(
            d, legs, decision_dt, spot, wing_width=IC_WING, structure_name=IC_STRUCTURE,
            contracts=1, pt_frac=IC_PT_FRAC, stop_mult=IC_STOP_MULT,
            commission_per_contract=IC_COMMISSION)
        if not f.skipped:
            by_day[d] = float(f.realized_pnl)
    return by_day


# ═════════════════════════════════════════════════════════════════════════════════
#  METRICS
# ═════════════════════════════════════════════════════════════════════════════════
def _daily_series(by_day: dict[dt.date, float], days: list[dt.date]) -> np.ndarray:
    """Daily P&L vector over `days` (0.0 on a no-trade day for the book)."""
    return np.array([by_day.get(d, 0.0) for d in days], float)


def book_metrics(daily: np.ndarray) -> dict:
    """Sharpe/Sortino/maxDD/total on a daily-P&L vector (excess-return rf=0)."""
    n = int(daily.size)
    if n == 0:
        return {"n_days": 0, "total": 0.0, "mean": 0.0, "sharpe": 0.0, "sortino": 0.0,
                "max_dd": 0.0, "win_days": 0, "loss_days": 0}
    mean = float(daily.mean())
    sd = float(daily.std(ddof=1)) if n > 1 else 0.0
    downside = daily[daily < 0]
    dd_sd = float(np.sqrt((downside ** 2).mean())) if downside.size else 0.0
    eq = np.cumsum(daily)
    peak = np.maximum.accumulate(eq)
    max_dd = float((eq - peak).min()) if n else 0.0
    sharpe = (mean - TREASURY_RF) / sd * math.sqrt(252) if sd > 0 else 0.0
    sortino = (mean - TREASURY_RF) / dd_sd * math.sqrt(252) if dd_sd > 0 else 0.0
    return {"n_days": n, "total": round(float(daily.sum()), 2), "mean": round(mean, 3),
            "sharpe": round(sharpe, 3), "sortino": round(sortino, 3),
            "max_dd": round(max_dd, 2),
            "win_days": int((daily > 0).sum()), "loss_days": int((daily < 0).sum())}


def build_switched_book(regimes: dict[dt.date, str], dir_pnl: dict[dt.date, float],
                        ic_pnl: dict[dt.date, float], days: list[dt.date],
                        neutral_policy: str) -> dict[dt.date, float]:
    """One daily book P&L. TREND->directional, CHOP->condor, NEUTRAL->policy.
    neutral_policy in {'directional', 'condor', 'abstain'}."""
    book: dict[dt.date, float] = {}
    for d in days:
        r = regimes.get(d, "NEUTRAL")
        if r == "TREND":
            book[d] = dir_pnl.get(d, 0.0)
        elif r == "CHOP":
            book[d] = ic_pnl.get(d, 0.0)
        else:  # NEUTRAL
            if neutral_policy == "directional":
                book[d] = dir_pnl.get(d, 0.0)
            elif neutral_policy == "condor":
                book[d] = ic_pnl.get(d, 0.0)
            else:  # abstain
                book[d] = 0.0
    return book


def chop_day_isolation(regimes: dict[dt.date, str], dir_pnl: dict[dt.date, float],
                       ic_pnl: dict[dt.date, float], days: list[dt.date]) -> dict:
    """The LOAD-BEARING thesis check: on the classifier's OWN CHOP days, does the condor
    sleeve beat the directional sleeve? This is the cleanest test of right-tool-for-regime,
    isolated from the NEUTRAL-policy noise. condor_minus_directional > 0 => thesis supported."""
    chop = [d for d in days if regimes.get(d) == "CHOP"]
    d_chop = sum(dir_pnl.get(d, 0.0) for d in chop)
    i_chop = sum(ic_pnl.get(d, 0.0) for d in chop)
    trend = [d for d in days if regimes.get(d) == "TREND"]
    return {"n_chop_days": len(chop),
            "directional_pnl_on_chop": round(d_chop, 2),
            "condor_pnl_on_chop": round(i_chop, 2),
            "condor_minus_directional_on_chop": round(i_chop - d_chop, 2),
            "thesis_supported": bool(i_chop > d_chop),
            "n_trend_days": len(trend),
            "directional_pnl_on_trend": round(sum(dir_pnl.get(d, 0.0) for d in trend), 2)}


def switch_days_noregression(regimes: dict[dt.date, str], dir_pnl: dict[dt.date, float],
                             switched: dict[dt.date, float], days: list[dt.date]) -> dict:
    """No-regression gate (bar 3): on the days the book SWITCHES AWAY from directional
    (CHOP days, and NEUTRAL days that abstain/condor), did the book net-improve vs what
    directional-alone would have done on those same days?"""
    switch_days = [d for d in days if regimes.get(d) != "TREND"]
    book_on_switch = sum(switched.get(d, 0.0) for d in switch_days)
    dir_on_switch = sum(dir_pnl.get(d, 0.0) for d in switch_days)
    return {"n_switch_days": len(switch_days),
            "book_pnl_on_switch_days": round(book_on_switch, 2),
            "directional_pnl_on_switch_days": round(dir_on_switch, 2),
            "net_improvement": round(book_on_switch - dir_on_switch, 2),
            "no_regression_pass": bool(book_on_switch >= dir_on_switch)}


# ═════════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser(description="Regime-switch book harness (research question only)")
    ap.add_argument("--smoke", action="store_true",
                    help="print regime label + sleeve fired for ~5 sample days, then exit")
    args = ap.parse_args()

    print("[switch] loading SPY+VIX (master + recent), MES overnight ...", flush=True)
    # Directional path frame (recency_check convention).
    master_spy = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-06-16.csv")
    master_vix = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-06-16.csv")
    recent_spy = pd.read_csv(DATA / "spy_5m_2026-05-19_2026-06-18.csv")
    recent_vix = pd.read_csv(DATA / "vix_5m_2026-05-19_2026-06-18.csv")
    spy_raw = pd.concat([master_spy, recent_spy], ignore_index=True)
    vix_raw = pd.concat([master_vix, recent_vix], ignore_index=True)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)

    # Condor path frame (pivot convention) + the OPRA cache date universe.
    spy_pivot = P._load_spy_master()
    cache_days = P._option_cache_dates()

    days_ctx = build_day_contexts(spy)
    trading_days = sorted({dc.date for dc in days_ctx})
    # Universe = days we can trade BOTH sleeves' data on (intersect with OPRA cache).
    universe = [d for d in trading_days if d in cache_days]
    frame_first, frame_last = trading_days[0], trading_days[-1]
    print(f"[switch] trading_days={len(trading_days)} ({frame_first}..{frame_last}) | "
          f"OPRA-cache-overlap universe={len(universe)} ({universe[0]}..{universe[-1]})", flush=True)

    # --- Regime classifier (causal) ---
    feats = compute_regime_features(spy, vix, trading_days)
    is_days = [d for d in universe if d < OOS_START]
    th = learn_thresholds(feats, is_days)
    regimes = {d: classify_day(feats[d], th) for d in universe}

    dist = defaultdict(int)
    for d in universe:
        dist[regimes[d]] += 1
    dist_oos = defaultdict(int)
    for d in universe:
        if d >= OOS_START:
            dist_oos[regimes[d]] += 1
    print(f"[switch] thresholds: trend_hi={th.trend_hi:.5f} trend_lo={th.trend_lo:.5f} "
          f"on_hi={th.on_hi:.3f} on_lo={th.on_lo:.3f} vix_lo={th.vix_lo:.2f}", flush=True)
    print(f"[switch] regime distribution (universe): "
          f"TREND={dist['TREND']} CHOP={dist['CHOP']} NEUTRAL={dist['NEUTRAL']}", flush=True)

    # Reject a degenerate split (the dead 10/124/218 band). Require each non-NEUTRAL class
    # to be a meaningful minority and not collapse to ~0 or ~all.
    n = len(universe)
    degenerate = (dist["TREND"] < max(5, int(0.05 * n)) or
                  dist["CHOP"] < max(5, int(0.05 * n)) or
                  dist["NEUTRAL"] > int(0.85 * n))
    if degenerate:
        print("[switch] WARNING: regime split looks degenerate (a class < 5% or NEUTRAL > 85%). "
              "Reported for honesty; tune thresholds before trusting the book.", flush=True)

    if args.smoke:
        sample = universe[:3] + universe[len(universe) // 2: len(universe) // 2 + 1] + universe[-1:]
        print("\n=== SMOKE: regime label + sleeve for sample days ===")
        for d in sample:
            f = feats[d]
            r = regimes[d]
            sleeve = {"TREND": "directional(vwap_cont,ATM,-8%)",
                      "CHOP": "iron_condor(LEAD)",
                      "NEUTRAL": "policy-dependent"}[r]
            tr = f"{f.trend_strength_20d:.5f}" if f.trend_strength_20d is not None else "NA"
            onr = f"{f.overnight_range_pct_atr:.3f}" if f.overnight_range_pct_atr is not None else "NA"
            vx = f"{f.vix_spot:.2f}" if f.vix_spot is not None else "NA"
            print(f"  {d}  regime={r:7s} -> {sleeve:32s} | trend20d={tr} on/atr={onr} vix={vx}")
        print("\n[switch] --smoke OK (no sims run).")
        return 0

    # --- Run BOTH sleeves once on real OPRA fills ---
    print("[switch] running directional sleeve (real OPRA fills) ...", flush=True)
    dir_pnl = directional_pnl_by_day(spy, vix)
    print(f"[switch]   directional filled on {len(dir_pnl)} days", flush=True)
    print("[switch] running iron-condor sleeve (real OPRA fills) ...", flush=True)
    ic_pnl = condor_pnl_by_day(spy_pivot, cache_days, universe)
    print(f"[switch]   condor filled on {len(ic_pnl)} days", flush=True)

    # --- Baseline: DIRECTIONAL-ALWAYS over the universe ---
    dir_daily = _daily_series(dir_pnl, universe)
    dir_oos = _daily_series(dir_pnl, [d for d in universe if d >= OOS_START])
    dir_recent = _daily_series(dir_pnl, universe[-RECENCY_N:])
    baseline = {"full": book_metrics(dir_daily), "oos": book_metrics(dir_oos),
                f"recency_{RECENCY_N}d": book_metrics(dir_recent)}

    # --- The load-bearing thesis check: condor vs directional on the OWN CHOP days ---
    chop_iso = chop_day_isolation(regimes, dir_pnl, ic_pnl, universe)
    print(f"\n[switch] CHOP-DAY ISOLATION (the thesis): n_chop={chop_iso['n_chop_days']} "
          f"directional=${chop_iso['directional_pnl_on_chop']} "
          f"condor=${chop_iso['condor_pnl_on_chop']} "
          f"(condor-dir=${chop_iso['condor_minus_directional_on_chop']}) "
          f"-> thesis_supported={chop_iso['thesis_supported']}", flush=True)

    # --- Switched book under each NEUTRAL policy ---
    variants_out = {}
    for policy in ("directional", "condor", "abstain"):
        book = build_switched_book(regimes, dir_pnl, ic_pnl, universe, policy)
        b_full = _daily_series(book, universe)
        b_oos = _daily_series(book, [d for d in universe if d >= OOS_START])
        b_recent = _daily_series(book, universe[-RECENCY_N:])
        m_full, m_oos, m_rec = book_metrics(b_full), book_metrics(b_oos), book_metrics(b_recent)
        nores = switch_days_noregression(regimes, dir_pnl, book, universe)

        # THE BAR (reported, not asserted):
        bar1 = (m_full["sharpe"] >= baseline["full"]["sharpe"] and
                m_full["sortino"] >= baseline["full"]["sortino"] and
                m_full["max_dd"] >= baseline["full"]["max_dd"])  # max_dd is negative; >= = shallower
        bar2 = (m_rec["max_dd"] >= baseline[f"recency_{RECENCY_N}d"]["max_dd"] and
                m_rec["total"] >= baseline[f"recency_{RECENCY_N}d"]["total"])
        bar3 = nores["no_regression_pass"]
        bar4 = m_oos["total"] > 0
        variants_out[policy] = {
            "full": m_full, "oos": m_oos, f"recency_{RECENCY_N}d": m_rec,
            "no_regression": nores,
            "bar": {
                "1_risk_adjusted_up_vs_directional": bool(bar1),
                "2_recency_chop_drawdown_reduced": bool(bar2),
                "3_no_regression_on_switch_days": bool(bar3),
                "4_oos_positive": bool(bar4),
                "ALL_PASS": bool(bar1 and bar2 and bar3 and bar4),
            },
        }
        print(f"\n[switch] NEUTRAL={policy:11s} | FULL sharpe={m_full['sharpe']} "
              f"sortino={m_full['sortino']} maxDD=${m_full['max_dd']} tot=${m_full['total']} "
              f"| OOS tot=${m_oos['total']} | rec maxDD=${m_rec['max_dd']} tot=${m_rec['total']}")
        print(f"         vs DIR-ALWAYS  | FULL sharpe={baseline['full']['sharpe']} "
              f"sortino={baseline['full']['sortino']} maxDD=${baseline['full']['max_dd']} "
              f"tot=${baseline['full']['total']} | OOS tot=${baseline['oos']['total']} "
              f"| rec maxDD=${baseline[f'recency_{RECENCY_N}d']['max_dd']}")
        print(f"         BAR: rr_up={bar1} rec_dd_down={bar2} no_regress={bar3} oos_pos={bar4} "
              f"-> ALL={variants_out[policy]['bar']['ALL_PASS']}")

    summary = {
        "harness": "REGIME-SWITCH BOOK — does regime allocation beat directional-always?",
        "run_date": dt.date.today().isoformat(),
        "research_question": ("Allocate between two real-fills sleeves by causal morning regime "
                              "(TREND->directional vwap_continuation, CHOP->iron condor LEAD); "
                              "does the switched book beat directional-ALWAYS on risk-adjusted "
                              "return + recency chop drawdown + no-regression + OOS-positive?"),
        "frame": f"{frame_first}..{frame_last}",
        "universe_days": n,
        "universe_span": f"{universe[0]}..{universe[-1]}",
        "oos_start": str(OOS_START),
        "fills_authority": "real OPRA — simulator_real (directional) + simulator_credit (condor) (C1)",
        "directional_config": {"detector": "vwap_continuation (live)", "strike_offset": DIR_STRIKE_OFFSET,
                               "tier": "ATM (Safe-2)", "premium_stop_pct": DIR_PREMIUM_STOP_PCT,
                               "qty": DIR_QTY, "exits": "v15 default"},
        "condor_config": {"structure": IC_STRUCTURE, "entry": IC_ENTRY_TIME.strftime("%H:%M"),
                          "short_offset": IC_SHORT_OFFSET, "wing": IC_WING, "pt_frac": IC_PT_FRAC,
                          "stop_mult": IC_STOP_MULT, "commission": IC_COMMISSION,
                          "source": "PIVOT-PREMIUM-SELLING-SCORECARD.md LEAD cell"},
        "regime_classifier": {
            "features": ["trend_strength_20d (causal, prior closes vs prior SMA20)",
                         "vix_spot @09:30 (causal)", "vix_slope_5bar (causal)",
                         "overnight_range_pct_atr (MES 18:00->09:30 / 14d MES range ATR, causal)",
                         "prior_realized_range_pct_atr (prior RTH range / 14d SPY ATR, causal)"],
            "rule": ("TREND = strong trend AND adequate overnight range; "
                     "CHOP = flat trend AND (compressed overnight range OR compressed VIX); "
                     "NEUTRAL = otherwise"),
            "thresholds_source": "IN-SAMPLE terciles (pre-2026), no OOS leakage",
            "thresholds": {"trend_hi": round(th.trend_hi, 6), "trend_lo": round(th.trend_lo, 6),
                           "on_hi": round(th.on_hi, 4), "on_lo": round(th.on_lo, 4),
                           "vix_lo": round(th.vix_lo, 3)},
            "distribution_universe": dict(dist),
            "distribution_oos": dict(dist_oos),
            "degenerate_split_flag": bool(degenerate),
        },
        "chop_day_isolation": chop_iso,
        "directional_always_baseline": baseline,
        "switched_book_variants": variants_out,
        "DISCLOSURE": {
            "condor_is_null_failing_standalone": ("the IC sleeve FAILS the L172 random-strike null "
                "as a standalone (generic theta, not selection alpha) AND is data-constrained by the "
                "+/-$5 OPRA band / narrow $2 wings — see PIVOT-PREMIUM-SELLING-SCORECARD.md. A SHIP "
                "needs the wide-band condor validation (direction 4b) FIRST."),
            "what_this_answers": ("the RESEARCH question only — does regime ALLOCATION beat "
                "directional-alone? A YES makes the heavy wide-band fetch (4b) worth it; it is NOT "
                "a ship signal on its own."),
            "per_trade": "per-trade/per-day EXPECTANCY, not WR alone (OP-14)",
            "real_fills": "real OPRA fills only — the WR authority (C1); SPY-direction != option edge (C3/L58)",
            "no_new_ship": "RESEARCH ONLY; no live edit, no orders (money-path guard)",
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "results.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[switch] wrote {out_json}")

    print("\n=== REGIME-SWITCH BOOK VERDICT (vs DIRECTIONAL-ALWAYS) ===")
    print(f"regime dist (universe): TREND={dist['TREND']} CHOP={dist['CHOP']} "
          f"NEUTRAL={dist['NEUTRAL']}  (degenerate={degenerate})")
    print(f"THESIS (condor vs directional on CHOP days): "
          f"dir=${chop_iso['directional_pnl_on_chop']} condor=${chop_iso['condor_pnl_on_chop']} "
          f"-> supported={chop_iso['thesis_supported']}")
    for policy, v in variants_out.items():
        print(f"  NEUTRAL={policy:11s} -> ALL_BAR_PASS={v['bar']['ALL_PASS']}  "
              f"(rr_up={v['bar']['1_risk_adjusted_up_vs_directional']} "
              f"rec_dd={v['bar']['2_recency_chop_drawdown_reduced']} "
              f"no_regress={v['bar']['3_no_regression_on_switch_days']} "
              f"oos_pos={v['bar']['4_oos_positive']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
