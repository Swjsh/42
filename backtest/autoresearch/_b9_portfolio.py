"""B9 — MEASURE THE 3-EDGE VWAP PORTFOLIO (the never-done make-money + sizing question).

We validated the three real edges INDIVIDUALLY. We have NEVER measured them as a combined
portfolio. This harness runs all three edges' real-fills trade streams over the SAME window
(2025-01..2026-05, real OPRA fills via lib.simulator_real, each at its validated tier+config)
and computes the portfolio's combined behaviour:

THE THREE EDGES (all VWAP-native, all call/bull-biased on the 2026 bull tape):
  #1 vwap_continuation       — LIVE. ITM-2 (Bold) + ATM (Safe-2). Detector = the byte-for-byte
                               LIVE detector (_edgehunt_vwap_continuation.detect_signals).
                               PLUS the WP-1 touch-and-go refinement (GENUINE_TRIGGER, B8) run
                               as an A/B variant of #1's CALL entry on the matched call-days.
  #2 vwap_reclaim_failed_break — dormant. ITM-2 (Bold) + ATM (Safe-2). Detector =
                               _sub_struct_vwap_reclaim_failed_break.detect_signals.
  #4 vix_regime_dayside      — dormant. ATM (Safe-2). Detector =
                               _b5_vix_regime_dayside.detect_opt_signals at its robust config
                               (slope_rule + low_margin read from the b5 scorecard's robust cell).

PER-ACCOUNT COMPOSITION (respect where each edge is validated):
  * Safe-2 (ATM, strike_offset=0): #1 + #2 + #4   (all three)
  * Bold   (ITM-2, strike_offset=-2): #1 + #2      (#4 is ATM-only)
When 2+ edges fire the same day, BOTH trades are taken (each per its own one-entry/day rule).

WHAT WE COMPUTE (the actual deliverables):
  1. COMBINED daily equity curve per account (sum of that day's edge P&Ls).
  2. EDGE CORRELATION / DAY-OVERLAP matrix between #1, #2, #4 — do they fire the same days?
     are their daily P&Ls correlated? (low correlation = diversification value). Overlap =
     Jaccard of fire-day sets; daily-P&L corr = Pearson on the union of fire-days (0 where an
     edge didn't fire that day — the realistic "what the book felt" series).
  3. PORTFOLIO AGGREGATE per account: total P&L, per-trade expectancy, annualized Sharpe (on
     the DAILY equity series), max drawdown, % of trading days in market, worst day — vs each
     edge STANDALONE.
  4. ROUTING / ABSTENTION: does day-of-week / OPEX / month-end / gap / vol-regime routing or
     abstention improve the PORTFOLIO Sharpe & drawdown? For each calendar/day-type bucket we
     measure the portfolio's per-bucket daily mean; a bucket whose mean is < 0 is a candidate
     ABSTAIN bucket. No-regression = the abstained days are net-NEGATIVE across the portfolio
     (L174) — we report the abstained-day net so the verdict is honest, never cherry-picked.

DISCLOSURE (OP-20 / C7 — PASTE REAL NUMBERS):
  * Real OPRA fills (C1) — the only 0DTE WR authority. SPY-direction != option edge (C3/L58).
  * Per-trade EXPECTANCY, not WR alone (OP-14). Daily Sharpe annualized x sqrt(252).
  * This is a MEASUREMENT (verdict PORTFOLIO_MEASURED) + any routing improvement
    (ROUTING_IMPROVEMENT) — NOT a new edge candidate. No standing-bar gate is applied to the
    portfolio itself; the constituents already cleared their bars individually.

Pure Python / numpy, $0 (no LLM, no live orders). Markets closed.
Writes analysis/recommendations/B9-PORTFOLIO-SCORECARD.{md,json}.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b9_portfolio.py
"""
from __future__ import annotations

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

from autoresearch import runner as ar_runner  # noqa: E402
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
from autoresearch._b7_vwap_structures import detect_touch_and_go  # noqa: E402
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals as detect_reclaim_failed_break,
)
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    causal_vix_median,
    vix_slope,
    detect_opt_signals as detect_vix_regime_dayside,
    VIX_MEDIAN_BARS,
    VIX_SLOPE_BARS,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "B9-PORTFOLIO-SCORECARD.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "B9-PORTFOLIO-SCORECARD.md"
B5_SCORECARD = ROOT / "analysis" / "recommendations" / "b5-vix-regime-dayside.json"

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# ── Shared sim config (each edge ratified at v15 tight -8% premium stop, qty 3) ───
PREMIUM_STOP_PCT = -0.08
MAX_STRIKE_STEPS = 4
QTY = 3
OOS_YEAR = 2026
TRADING_DAYS_PER_YEAR = 252

# Strike tiers per account (C29 — knobs/edges live at the tier they were validated on).
ATM = 0
ITM2 = -2

# Edge #4 robust config fallback (overridden from the b5 scorecard if present).
VIX_REGIME_DEFAULT = {"slope_rule": "not_rising", "low_margin": 0.0}


# ════════════════════════════════════════════════════════════════════════════════
# SIM — one signal set at one strike tier on real OPRA fills (v15 default exits)
# ════════════════════════════════════════════════════════════════════════════════
@dataclass
class TradeRow:
    date: str
    side: str
    strike: int
    pnl: float
    pct: float
    exit_reason: str


def simulate_set(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct=PREMIUM_STOP_PCT,
                 setup="B9") -> tuple[list[TradeRow], dict]:
    """Run every signal at one strike tier on real OPRA fills. One entry/day already
    guaranteed by each detector (breaks after the first qualifying bar)."""
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup=setup, strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct)
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(d), side=sg.side, strike=int(strike),
            pnl=round(float(fill.dollar_pnl), 2),
            pct=round(float(fill.pct_return_on_premium), 5),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE"))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ════════════════════════════════════════════════════════════════════════════════
# METRICS — standalone-edge + portfolio (daily equity)
# ════════════════════════════════════════════════════════════════════════════════
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def by_day(rows: list[TradeRow]) -> dict[str, float]:
    d: dict[str, float] = defaultdict(float)
    for r in rows:
        d[r.date] += r.pnl
    return dict(d)


def edge_metrics(rows: list[TradeRow]) -> dict:
    """Per-trade standalone metrics for one edge stream."""
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]
    bd = by_day(rows)
    daily = np.array(list(bd.values()), float)
    return {
        "n": n,
        "days": len(bd),
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows),
        "is_exp": round(float(np.mean([r.pnl for r in is_rows])), 2) if is_rows else 0.0,
        "oos_n": len(oos_rows),
        "oos_exp": round(float(np.mean([r.pnl for r in oos_rows])), 2) if oos_rows else 0.0,
        "oos_total": round(float(np.sum([r.pnl for r in oos_rows])), 2) if oos_rows else 0.0,
        "daily_mean": round(float(daily.mean()), 2),
        "daily_std": round(float(daily.std(ddof=1)), 2) if len(daily) > 1 else 0.0,
        "by_side": {sd: {"n": sum(1 for r in rows if r.side == sd),
                         "total": round(sum(r.pnl for r in rows if r.side == sd), 2)}
                    for sd in ("C", "P") if any(r.side == sd for r in rows)},
    }


def daily_series_for_days(rows: list[TradeRow], all_days: list[str]) -> np.ndarray:
    """Daily P&L aligned to a fixed day axis (0 on days the edge did not fire/fill)."""
    bd = by_day(rows)
    return np.array([bd.get(d, 0.0) for d in all_days], float)


def portfolio_aggregate(combined_daily: dict[str, float], n_trading_days: int) -> dict:
    """Aggregate over the COMBINED daily equity (book-level)."""
    if not combined_daily:
        return {"days_in_market": 0}
    days_sorted = sorted(combined_daily)
    pnl_days = np.array([combined_daily[d] for d in days_sorted], float)
    total = float(pnl_days.sum())
    eq = np.cumsum(pnl_days)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    max_dd = float(dd.min())
    # Sharpe on the daily-equity series across ALL trading days (in-market days carry P&L,
    # flat days carry 0) — the realistic risk-adjusted measure of the book.
    full_axis = np.zeros(n_trading_days)
    full_axis[:len(pnl_days)] = 0.0  # placeholder, replaced below by union semantics
    # Build a real all-trading-day daily vector via the caller's axis handled separately;
    # here we annualize on the in-market daily series + flat days appended as zeros.
    flat_days = max(0, n_trading_days - len(pnl_days))
    daily_vec = np.concatenate([pnl_days, np.zeros(flat_days)])
    mean_d = float(daily_vec.mean())
    std_d = float(daily_vec.std(ddof=1)) if len(daily_vec) > 1 else 0.0
    sharpe = round((mean_d / std_d) * np.sqrt(TRADING_DAYS_PER_YEAR), 2) if std_d > 0 else None
    worst = float(pnl_days.min())
    best = float(pnl_days.max())
    return {
        "total_dollar": round(total, 2),
        "days_in_market": len(pnl_days),
        "n_trading_days": n_trading_days,
        "pct_days_in_market": round(100 * len(pnl_days) / n_trading_days, 1) if n_trading_days else 0.0,
        "daily_mean_all_days": round(mean_d, 2),
        "daily_mean_in_market": round(float(pnl_days.mean()), 2),
        "daily_std_all_days": round(std_d, 2),
        "annualized_sharpe": sharpe,
        "max_drawdown": round(max_dd, 2),
        "worst_day": round(worst, 2),
        "best_day": round(best, 2),
        "win_days": int((pnl_days > 0).sum()),
        "loss_days": int((pnl_days < 0).sum()),
        "day_win_pct": round(100 * float((pnl_days > 0).mean()), 1),
    }


# ════════════════════════════════════════════════════════════════════════════════
# CORRELATION / DAY-OVERLAP MATRIX
# ════════════════════════════════════════════════════════════════════════════════
def jaccard(a: set, b: set) -> float:
    u = a | b
    return round(len(a & b) / len(u), 3) if u else 0.0


def overlap_and_corr(edge_rows: dict[str, list[TradeRow]]) -> dict:
    """Day-overlap (Jaccard of fire-day sets) + daily-P&L Pearson corr, pairwise.

    Corr computed on the UNION of the two edges' fire-days (0 where one didn't fire) —
    the realistic 'what the book felt day to day' series, so a non-overlapping pair shows
    near-zero correlation (genuine diversification), not a spuriously high corr from a tiny
    shared subset."""
    names = list(edge_rows)
    fire_days = {nm: set(by_day(rows)) for nm, rows in edge_rows.items()}
    overlap = {}
    corr = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            key = f"{a}__{b}"
            overlap[key] = {
                "jaccard": jaccard(fire_days[a], fire_days[b]),
                "shared_days": len(fire_days[a] & fire_days[b]),
                f"{a}_days": len(fire_days[a]),
                f"{b}_days": len(fire_days[b]),
            }
            union = sorted(fire_days[a] | fire_days[b])
            if len(union) >= 3:
                va = daily_series_for_days(edge_rows[a], union)
                vb = daily_series_for_days(edge_rows[b], union)
                if va.std() > 0 and vb.std() > 0:
                    corr[key] = round(float(np.corrcoef(va, vb)[0, 1]), 3)
                else:
                    corr[key] = None
            else:
                corr[key] = None
    return {"day_overlap": overlap, "daily_pnl_correlation": corr,
            "fire_day_counts": {nm: len(s) for nm, s in fire_days.items()}}


# ════════════════════════════════════════════════════════════════════════════════
# DAY-TYPE / CALENDAR CLASSIFICATION (for routing)
# ════════════════════════════════════════════════════════════════════════════════
def classify_days(days, spy: pd.DataFrame) -> dict[str, dict]:
    """Per-day labels: day-of-week, OPEX (3rd Fri), month-end (last trading day of month),
    gap (|open-prior_close|/prior_close), open-vs-VWAP day-trend side, intraday range %.
    All causal (computed from that day's own session + prior close)."""
    from autoresearch.infinite_ammo_discovery import session_vwap_asof
    labels: dict[str, dict] = {}
    by_month: dict[str, list[str]] = defaultdict(list)
    for dc in days:
        d = dc.date
        ds = str(d)
        by_month[f"{d.year}-{d.month:02d}"].append(ds)
        rth = dc.rth
        o = float(rth["open"].iloc[0])
        hi = float(rth["high"].max())
        lo = float(rth["low"].min())
        pc = dc.prior_close
        gap = round(100 * (o - pc) / pc, 3) if pc else 0.0
        rng = round(100 * (hi - lo) / o, 3) if o else 0.0
        # day-trend side from first 3 closes vs as-of VWAP (the shared edge primitive)
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        if len(closes) >= 3:
            head_c, head_v = closes[:3], vwap[:3]
            if np.all(head_c > head_v):
                side = "up"
            elif np.all(head_c < head_v):
                side = "down"
            else:
                side = "mixed"
        else:
            side = "mixed"
        is_opex = (d.weekday() == 4 and 15 <= d.day <= 21)
        labels[ds] = {
            "dow": d.weekday(),  # 0=Mon
            "dow_name": ["Mon", "Tue", "Wed", "Thu", "Fri"][d.weekday()] if d.weekday() < 5 else "WE",
            "gap_pct": gap,
            "gap_bucket": ("gap_up" if gap > 0.3 else "gap_down" if gap < -0.3 else "flat_open"),
            "range_pct": rng,
            "range_bucket": ("wide" if rng > 1.5 else "narrow" if rng < 0.7 else "mid"),
            "trend_side": side,
            "is_opex": bool(is_opex),
        }
    # month-end = last trading day in each month
    for ds_list in by_month.values():
        last = max(ds_list)
        labels[last]["is_month_end"] = True
    for ds in labels:
        labels[ds].setdefault("is_month_end", False)
    return labels


def routing_analysis(combined_daily: dict[str, float], labels: dict[str, dict],
                     n_trading_days: int) -> dict:
    """For each calendar/day-type bucket, the portfolio's per-day mean + total on the
    days the book was IN MARKET. A bucket with negative mean is an ABSTAIN candidate; we
    then report the no-regression check: net P&L of the abstained days (must be < 0 for
    abstention to be non-regressive, L174). We test the SINGLE best abstention bucket and
    the cumulative effect of abstaining every negative-mean bucket."""
    market_days = sorted(combined_daily)

    def bucket_stats(key_fn) -> dict:
        b: dict[str, list[float]] = defaultdict(list)
        for d in market_days:
            lab = labels.get(d)
            if lab is None:
                continue
            b[str(key_fn(lab))].append(combined_daily[d])
        return {k: {"n_days": len(v), "mean": round(float(np.mean(v)), 2),
                    "total": round(float(np.sum(v)), 2)}
                for k, v in sorted(b.items())}

    buckets = {
        "day_of_week": bucket_stats(lambda l: l["dow_name"]),
        "gap_bucket": bucket_stats(lambda l: l["gap_bucket"]),
        "range_bucket": bucket_stats(lambda l: l["range_bucket"]),
        "trend_side": bucket_stats(lambda l: l["trend_side"]),
        "opex": bucket_stats(lambda l: "opex" if l["is_opex"] else "non_opex"),
        "month_end": bucket_stats(lambda l: "month_end" if l["is_month_end"] else "non_month_end"),
    }

    base = portfolio_aggregate(combined_daily, n_trading_days)

    # Build the cumulative abstain set: every (dimension,value) bucket with mean < 0 and
    # at least 4 in-market days (avoid 1-2-day noise). Abstain = drop those days from book.
    abstain_keys = []
    for dim, bstats in buckets.items():
        for val, st in bstats.items():
            if st["mean"] < 0 and st["n_days"] >= 4:
                abstain_keys.append((dim, val))

    def label_value(lab, dim):
        return {
            "day_of_week": lab["dow_name"], "gap_bucket": lab["gap_bucket"],
            "range_bucket": lab["range_bucket"], "trend_side": lab["trend_side"],
            "opex": "opex" if lab["is_opex"] else "non_opex",
            "month_end": "month_end" if lab["is_month_end"] else "non_month_end",
        }[dim]

    def apply_abstain(keys):
        """Drop a day from the book if ANY of its bucket-values is in the abstain keyset."""
        kept, dropped = {}, {}
        keyset = set(keys)
        for d in market_days:
            lab = labels.get(d, {})
            drop = any((dim, label_value(lab, dim)) in keyset for dim in
                       ("day_of_week", "gap_bucket", "range_bucket", "trend_side", "opex", "month_end"))
            if drop:
                dropped[d] = combined_daily[d]
            else:
                kept[d] = combined_daily[d]
        return kept, dropped

    # Single best abstain bucket (largest NEGATIVE total, >=4 days) — the cleanest routing move.
    single_best = None
    for dim, bstats in buckets.items():
        for val, st in bstats.items():
            if st["n_days"] >= 4 and st["total"] < 0:
                if single_best is None or st["total"] < single_best["abstained_total"]:
                    single_best = {"dimension": dim, "value": val,
                                   "abstained_days": st["n_days"],
                                   "abstained_total": st["total"],
                                   "abstained_mean": st["mean"]}
    single_block = None
    if single_best:
        keep, drop = apply_abstain([(single_best["dimension"], single_best["value"])])
        agg_after = portfolio_aggregate(keep, n_trading_days)
        single_block = {
            **single_best,
            "no_regression_abstained_net": round(sum(drop.values()), 2),
            "no_regression_pass": bool(sum(drop.values()) < 0),
            "portfolio_after": agg_after,
            "sharpe_delta": (round(agg_after["annualized_sharpe"] - base["annualized_sharpe"], 2)
                             if agg_after.get("annualized_sharpe") is not None
                             and base.get("annualized_sharpe") is not None else None),
            "max_dd_delta": round(agg_after["max_drawdown"] - base["max_drawdown"], 2),
            "total_delta": round(agg_after["total_dollar"] - base["total_dollar"], 2),
        }

    cumulative_block = None
    if abstain_keys:
        keep, drop = apply_abstain(abstain_keys)
        agg_after = portfolio_aggregate(keep, n_trading_days)
        cumulative_block = {
            "abstain_buckets": [f"{d}={v}" for d, v in abstain_keys],
            "n_abstained_days": len(drop),
            "no_regression_abstained_net": round(sum(drop.values()), 2),
            "no_regression_pass": bool(sum(drop.values()) < 0),
            "portfolio_after": agg_after,
            "sharpe_delta": (round(agg_after["annualized_sharpe"] - base["annualized_sharpe"], 2)
                             if agg_after.get("annualized_sharpe") is not None
                             and base.get("annualized_sharpe") is not None else None),
            "max_dd_delta": round(agg_after["max_drawdown"] - base["max_drawdown"], 2),
            "total_delta": round(agg_after["total_dollar"] - base["total_dollar"], 2),
        }

    return {
        "base_portfolio": base,
        "buckets": buckets,
        "single_best_abstain": single_block,
        "cumulative_abstain": cumulative_block,
        "routing_note": ("a bucket is an ABSTAIN candidate only if its in-market daily MEAN < 0 "
                         "with >= 4 days; no-regression (L174) requires the abstained days' NET "
                         "P&L < 0. Sharpe/DD/total deltas are vs the base 3-edge book."),
    }


# ════════════════════════════════════════════════════════════════════════════════
# EDGE #4 robust config from the b5 scorecard (fallback to default)
# ════════════════════════════════════════════════════════════════════════════════
def load_vix_regime_config() -> dict:
    try:
        b5 = json.loads(B5_SCORECARD.read_text(encoding="utf-8"))
        rb = b5.get("headline", {}).get("robust_clearing_cell")
        if rb and rb.get("slope_rule") is not None and rb.get("low_margin") is not None:
            return {"slope_rule": rb["slope_rule"], "low_margin": rb["low_margin"],
                    "source": "b5 robust_clearing_cell"}
    except Exception as e:  # noqa: BLE001
        print(f"[b9] WARN could not read b5 scorecard ({e}); using default vix-regime config",
              flush=True)
    return {**VIX_REGIME_DEFAULT, "source": "default (b5 robust cell unavailable)"}


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"[b9] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_trading_days = len(days)
    all_days = [str(dc.date) for dc in days]
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    print(f"[b9] trading_days={n_trading_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    # VIX arrays for edge #4 (causal median + slope; numpy arrays indexed by global idx)
    vix_g = vix.to_numpy()
    vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
    vix_cfg = load_vix_regime_config()
    print(f"[b9] edge#4 vix-regime config: {vix_cfg}", flush=True)

    # ── Detect each edge's signals ONCE ──────────────────────────────────────────
    sig_e1 = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_e1_tg = detect_touch_and_go(days)             # WP-1 refinement (call-day entry variant)
    sig_e2 = detect_reclaim_failed_break(days)
    sig_e4 = detect_vix_regime_dayside(days, spy, vix_g, vix_med_g, vix_slp_g,
                                       vix_cfg["low_margin"], vix_cfg["slope_rule"])
    # edge #4 returns OptSig (gidx) — adapt to Signal so simulate_set can run it.
    sig_e4 = [Signal(bar_idx=s.gidx, side=s.side,
                     stop_level=None, note="vix_regime_dayside") for s in sig_e4]
    # edge #4's stop is a 12-bar swing in its own harness; here we let the sim use the
    # premium stop + (None) chart level. To keep it faithful we recompute the swing stop.
    from autoresearch._b5_vix_regime_dayside import _swing_stop
    sig_e4 = [Signal(bar_idx=s.bar_idx, side=s.side,
                     stop_level=round(_swing_stop(spy, s.bar_idx, s.side), 2),
                     note="vix_regime_dayside") for s in sig_e4]

    print(f"[b9] signals: #1={len(sig_e1)}  #1_touchgo={len(sig_e1_tg)}  "
          f"#2={len(sig_e2)}  #4={len(sig_e4)}", flush=True)

    # ── Simulate each edge at each account's strike tier on real OPRA fills ───────
    # Safe-2 = ATM ; Bold = ITM-2
    rows = {}
    cov = {}
    plan = [
        ("e1_atm", sig_e1, ATM, "VWAPCONT"),
        ("e1_itm2", sig_e1, ITM2, "VWAPCONT"),
        ("e1tg_atm", sig_e1_tg, ATM, "VWAPCONT_TG"),
        ("e1tg_itm2", sig_e1_tg, ITM2, "VWAPCONT_TG"),
        ("e2_atm", sig_e2, ATM, "RECLAIM"),
        ("e2_itm2", sig_e2, ITM2, "RECLAIM"),
        ("e4_atm", sig_e4, ATM, "VIXREGIME"),
    ]
    for name, sigs, off, setup in plan:
        r, c = simulate_set(sigs, spy, ribbon, vix, strike_offset=off, setup=setup)
        rows[name] = r
        cov[name] = c
        m = edge_metrics(r)
        print(f"[b9]   {name:12s} off={off:+d}: n={m.get('n')} days={m.get('days')} "
              f"exp=${m.get('exp_dollar')} oos_exp=${m.get('oos_exp')} "
              f"total=${m.get('total_dollar')} fill={c['fill_rate']}", flush=True)

    # ── Standalone metrics per edge per tier ─────────────────────────────────────
    standalone = {name: edge_metrics(r) for name, r in rows.items()}

    # ── Build the two account portfolios (combine daily P&Ls) ────────────────────
    def combine(*edge_names) -> dict[str, float]:
        comb: dict[str, float] = defaultdict(float)
        for nm in edge_names:
            for d, p in by_day(rows[nm]).items():
                comb[d] += p
        return dict(comb)

    # Safe-2 ATM: #1 + #2 + #4 (base #1, NOT the touch-and-go variant — that is an A/B)
    safe_combined = combine("e1_atm", "e2_atm", "e4_atm")
    # Safe-2 with WP-1 touch-and-go SWAP for #1's call entry:
    safe_tg_combined = combine("e1tg_atm", "e2_atm", "e4_atm")
    # Bold ITM-2: #1 + #2
    bold_combined = combine("e1_itm2", "e2_itm2")
    bold_tg_combined = combine("e1tg_itm2", "e2_itm2")

    safe_agg = portfolio_aggregate(safe_combined, n_trading_days)
    safe_tg_agg = portfolio_aggregate(safe_tg_combined, n_trading_days)
    bold_agg = portfolio_aggregate(bold_combined, n_trading_days)
    bold_tg_agg = portfolio_aggregate(bold_tg_combined, n_trading_days)

    # ── Correlation / overlap matrices per account ───────────────────────────────
    safe_corr = overlap_and_corr({"e1": rows["e1_atm"], "e2": rows["e2_atm"], "e4": rows["e4_atm"]})
    bold_corr = overlap_and_corr({"e1": rows["e1_itm2"], "e2": rows["e2_itm2"]})

    # ── Routing analysis (run on the Safe-2 base book — the one with all 3 edges) ─
    labels = classify_days(days, spy)
    safe_routing = routing_analysis(safe_combined, labels, n_trading_days)
    bold_routing = routing_analysis(bold_combined, labels, n_trading_days)

    # ── Verdict ──────────────────────────────────────────────────────────────────
    routing_improves = False
    routing_reasons = []
    for acct, rt in (("Safe-2", safe_routing), ("Bold", bold_routing)):
        for blk_name, blk in (("single", rt["single_best_abstain"]),
                              ("cumulative", rt["cumulative_abstain"])):
            if blk and blk.get("no_regression_pass") and blk.get("sharpe_delta") is not None \
                    and blk["sharpe_delta"] > 0:
                routing_improves = True
                routing_reasons.append(
                    f"{acct} {blk_name}-abstain raises Sharpe by {blk['sharpe_delta']} "
                    f"(abstained net ${blk['no_regression_abstained_net']} < 0)")

    verdict = "ROUTING_IMPROVEMENT" if routing_improves else "PORTFOLIO_MEASURED"

    summary = {
        "campaign": "B9 — measure the 3-edge VWAP portfolio (combined real-fills + correlation + routing)",
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "trading_days": n_trading_days,
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR}",
        "config": {"premium_stop_pct": PREMIUM_STOP_PCT, "qty": QTY,
                   "exits": "v15 default (tp1=0.30, runner=2.5x, profit_lock=OFF)",
                   "vix_regime_config": vix_cfg},
        "edges": {
            "1_vwap_continuation": "LIVE; ITM-2 (Bold) + ATM (Safe-2); +WP-1 touch-and-go A/B variant",
            "2_vwap_reclaim_failed_break": "dormant; ITM-2 (Bold) + ATM (Safe-2)",
            "4_vix_regime_dayside": "dormant; ATM (Safe-2 only)",
        },
        "account_composition": {
            "Safe-2_ATM": ["#1", "#2", "#4"],
            "Bold_ITM2": ["#1", "#2"],
        },
        "signal_counts": {"e1": len(sig_e1), "e1_touch_and_go": len(sig_e1_tg),
                          "e2": len(sig_e2), "e4": len(sig_e4)},
        "coverage": cov,
        "standalone_edge_metrics": standalone,
        "portfolios": {
            "Safe-2_ATM_base_1+2+4": safe_agg,
            "Safe-2_ATM_withWP1touchandgo_1tg+2+4": safe_tg_agg,
            "Bold_ITM2_base_1+2": bold_agg,
            "Bold_ITM2_withWP1touchandgo_1tg+2": bold_tg_agg,
        },
        "correlation_overlap": {"Safe-2": safe_corr, "Bold": bold_corr},
        "routing": {"Safe-2": safe_routing, "Bold": bold_routing},
        "verdict": verdict,
        "routing_reasons": routing_reasons,
        "DISCLOSURE": {
            "measurement_not_candidate": ("this is a PORTFOLIO MEASUREMENT — the constituents "
                                          "each cleared the standing bar individually; no new "
                                          "standing-bar gate is applied to the book itself."),
            "per_trade": "per-trade EXPECTANCY reported, not WR alone (OP-14/C4)",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58)",
            "sharpe": "annualized = daily Sharpe x sqrt(252); daily series over ALL trading days "
                      "(flat days = 0) so % days in market is reflected in the risk-adjusted number",
            "correlation": ("daily-P&L Pearson on the UNION of each pair's fire-days (0 where one "
                            "didn't fire) — the realistic book-level diversification measure; "
                            "Jaccard = day-set overlap"),
            "routing_no_regression": ("L174 — an abstain bucket is only non-regressive if the "
                                      "abstained days' NET P&L < 0; reported per bucket"),
            "wp1_caveat": ("the touch-and-go (WP-1) row SWAPS #1's call entry for the touch-and-go "
                           "entry on call-days; reported as an A/B, not double-counted with base #1"),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_md(summary)
    print(f"\n[b9] wrote {OUT_JSON}\n[b9] wrote {OUT_MD}", flush=True)

    # ── Console verdict ──────────────────────────────────────────────────────────
    print("\n=== B9 PORTFOLIO VERDICT ===")
    print(f"VERDICT: {verdict}")
    for acct, agg in (("Safe-2 (ATM, 1+2+4)", safe_agg), ("Bold (ITM-2, 1+2)", bold_agg)):
        print(f"  {acct}: total=${agg['total_dollar']} sharpe={agg['annualized_sharpe']} "
              f"maxDD=${agg['max_drawdown']} %inMkt={agg['pct_days_in_market']} "
              f"worst=${agg['worst_day']} dayWR%={agg['day_win_pct']}")
    print(f"  Safe-2 pairwise corr: {safe_corr['daily_pnl_correlation']}")
    print(f"  Safe-2 overlap(Jaccard): "
          f"{ {k: v['jaccard'] for k, v in safe_corr['day_overlap'].items()} }")
    for r in routing_reasons:
        print(f"  ROUTING+: {r}")
    if not routing_reasons:
        print("  ROUTING: no non-regressive bucket abstention improves portfolio Sharpe.")
    return 0


def write_md(s: dict) -> None:
    L = []
    L.append("# B9 — The 3-Edge VWAP Portfolio (combined real-fills measurement)\n")
    L.append(f"- Run: {s['run_date']}  |  Window: {s['window']}  |  Trading days: {s['trading_days']}")
    L.append(f"- Fills: {s['fills_authority']}  |  OOS split: {s['oos_split']}")
    L.append(f"- Config: -8% premium stop, qty 3, v15 default exits; edge#4 vix config = "
             f"{s['config']['vix_regime_config']}")
    L.append(f"\n## VERDICT: **{s['verdict']}**\n")
    if s["routing_reasons"]:
        for r in s["routing_reasons"]:
            L.append(f"- ROUTING IMPROVEMENT: {r}")
    else:
        L.append("- No non-regressive calendar/day-type abstention improved portfolio Sharpe "
                 "(the book is already lean — see routing tables).")
    L.append("")

    # Standalone edge table
    L.append("## Standalone edges (real OPRA fills, per tier)\n")
    L.append("| edge (tier) | n | days | exp/tr | OOS exp/tr | total$ | WR% |")
    L.append("|---|---|---|---|---|---|---|")
    name_map = {"e1_atm": "#1 vwap_continuation (ATM)", "e1_itm2": "#1 vwap_continuation (ITM-2)",
                "e1tg_atm": "#1 WP-1 touch-and-go (ATM)", "e1tg_itm2": "#1 WP-1 touch-and-go (ITM-2)",
                "e2_atm": "#2 reclaim_failed_break (ATM)", "e2_itm2": "#2 reclaim_failed_break (ITM-2)",
                "e4_atm": "#4 vix_regime_dayside (ATM)"}
    for k, lbl in name_map.items():
        m = s["standalone_edge_metrics"].get(k, {})
        if not m.get("n"):
            L.append(f"| {lbl} | 0 | - | - | - | - | - |")
            continue
        L.append(f"| {lbl} | {m['n']} | {m['days']} | ${m['exp_dollar']} | ${m['oos_exp']} | "
                 f"${m['total_dollar']} | {m['wr_pct']} |")
    L.append("")

    # Portfolio aggregate table
    L.append("## Portfolio aggregates (combined daily equity vs standalone)\n")
    L.append("| book | total$ | ann.Sharpe | maxDD$ | % days in mkt | worst day$ | best day$ | day-WR% |")
    L.append("|---|---|---|---|---|---|---|---|")
    for lbl, agg in s["portfolios"].items():
        L.append(f"| {lbl} | ${agg['total_dollar']} | {agg['annualized_sharpe']} | "
                 f"${agg['max_drawdown']} | {agg['pct_days_in_market']}% | ${agg['worst_day']} | "
                 f"${agg['best_day']} | {agg['day_win_pct']} |")
    L.append("")

    # Correlation / overlap
    L.append("## Edge correlation & day-overlap (diversification value)\n")
    for acct in ("Safe-2", "Bold"):
        co = s["correlation_overlap"][acct]
        L.append(f"### {acct}")
        L.append(f"- fire-day counts: {co['fire_day_counts']}")
        L.append("")
        L.append("| pair | day-overlap (Jaccard) | shared days | daily-P&L corr |")
        L.append("|---|---|---|---|")
        for key, ov in co["day_overlap"].items():
            corr = co["daily_pnl_correlation"].get(key)
            L.append(f"| {key} | {ov['jaccard']} | {ov['shared_days']} | {corr} |")
        L.append("")

    # Routing tables
    L.append("## Routing / abstention analysis\n")
    L.append(f"_{s['routing']['Safe-2']['routing_note']}_\n")
    for acct in ("Safe-2", "Bold"):
        rt = s["routing"][acct]
        L.append(f"### {acct} base book")
        base = rt["base_portfolio"]
        L.append(f"- base: total=${base['total_dollar']} Sharpe={base['annualized_sharpe']} "
                 f"maxDD=${base['max_drawdown']} %inMkt={base['pct_days_in_market']}%")
        for dim, bstats in rt["buckets"].items():
            cells = "  ".join(f"{v}(n={st['n_days']},mean=${st['mean']},tot=${st['total']})"
                              for v, st in bstats.items())
            L.append(f"  - **{dim}**: {cells}")
        sb = rt["single_best_abstain"]
        if sb:
            L.append(f"- single best abstain: **{sb['dimension']}={sb['value']}** "
                     f"(drop {sb['abstained_days']} days, net ${sb['no_regression_abstained_net']}, "
                     f"no-regression={sb['no_regression_pass']}) -> Sharpe delta {sb['sharpe_delta']}, "
                     f"maxDD delta ${sb['max_dd_delta']}, total delta ${sb['total_delta']}")
        cb = rt["cumulative_abstain"]
        if cb:
            L.append(f"- cumulative abstain {cb['abstain_buckets']}: drop {cb['n_abstained_days']} "
                     f"days (net ${cb['no_regression_abstained_net']}, "
                     f"no-regression={cb['no_regression_pass']}) -> Sharpe delta {cb['sharpe_delta']}, "
                     f"maxDD delta ${cb['max_dd_delta']}, total delta ${cb['total_delta']}")
        L.append("")

    L.append("## How to read this\n")
    L.append("- **PORTFOLIO_MEASURED**: the combined-book numbers above are the answer — total "
             "P&L, per-trade expectancy (standalone table), annualized Sharpe, max DD, % days in "
             "market, worst day, vs each edge alone. This directly informs sizing + WP-0 ship order.")
    L.append("- **Correlation/overlap**: low Jaccard + low daily-P&L corr between edges = real "
             "diversification (the book's Sharpe should exceed any single edge's).")
    L.append("- **ROUTING_IMPROVEMENT** only if a calendar/day-type abstention raises Sharpe AND "
             "the abstained days were net-negative (L174 no-regression) — otherwise it is curve-fit.")
    L.append("- Real OPRA fills; SPY-direction != option edge (C3/L58). Per-trade EXPECTANCY, not "
             "WR alone (OP-14). All 3 edges are call/bull-biased on the 2026 bull tape.")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
