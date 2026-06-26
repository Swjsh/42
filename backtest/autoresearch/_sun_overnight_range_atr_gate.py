"""SUNDAY-FRESH ANGLE — overnight-range/ATR DEPLOY-TIMING gate (web-sourced hypothesis).

slug = overnight-range-pct-atr-regime-gate
kind = regime_gate  (a DEPLOY-TIMING layer on the BOOK — NOT a new signal, NOT a per-trade gate)

CLAIM (web-sourced, the published TradingView "NQ Overnight Range (% of Daily ATR)" framework,
rodtradessometimes; corroborated by ATR-regime day-trading literature): the OVERNIGHT range
(18:00 ET prior -> 09:30 ET) as a fraction of recent daily ATR classifies the coming RTH session:
    <25% of ATR  = CHOP-leaning  (quiet overnight -> fakeouts, weak follow-through)
    25-50%       = NEUTRAL
    >50%         = EXPANSION/TREND-leaning (active overnight -> follow-through)
Trend-continuation edges (our VWAP-native book) should BLEED in the chop band and WORK in the
trend band. DEPLOY-TIMING rule: deploy the book ONLY when overnight-range/ATR is in a trend-leaning
band; ABSTAIN in the chop band.

THE RIGHT BAR (a deploy-timing layer, per the task + L174): a mask is ACCEPTED only if it
  (a) LIFTS the book's risk-adjusted return (daily Sharpe/Sortino + maxDD), AND
  (b) passes NO-REGRESSION: the ABSTAINED days must sum NET-NEGATIVE (we are removing losers,
      not winners). A mask that improves Sharpe by removing net-positive days is winner-killing
      (L174) and is REJECTED.

WHAT IT REUSES (no edits to any watcher / params / detector — Sunday money-path guard):
  * recency_check.detect_all  -> the byte-for-byte LIVE detectors for #1/#2/#4
  * recency_check.simulate_set -> the real-OPRA fill path (lib.simulator_real) = the WR authority (C1)
  * recency_check.load_merged_spy_vix / _normalize_spy / _align_vix / build_day_contexts
  * BOOKS composition (Safe-2 ATM #1+#2+#4 ; Bold ITM-2 #1+#2) from recency_check
NEW: overnight-range/ATR per RTH date from backtest/data/futures/MES_1m_continuous.csv
  (MES = continuous incl. overnight; ATR(14) from daily RTH true-range of MES 5m bars).

CAVEAT (disclosed honestly): MES/MNQ 1m cache ends 2026-06-12; OPRA fills end 2026-06-18. Dates
06-13..06-18 have NO overnight-range value -> they are reported as UNCLASSIFIED and (conservatively)
KEPT in the deployed set (a deploy-timing layer can only abstain where it has data). The 25-day
live-drawdown window (2026-05-14..06-18) is covered through 06-12.

DISCLOSURE (OP-20/C1/C3/C7): real OPRA fills only; per-trade EXPECTANCY not WR alone; SPY-direction
!= option edge; daily Sharpe annualized x sqrt(252); abstained-day net reported (no winner-kill hide).
Pure Python/numpy, $0, markets closed, RESEARCH ONLY — no live edit, no orders.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sun_overnight_range_atr_gate.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from lib.ribbon import compute_ribbon  # noqa: E402
from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from autoresearch.recency_check import (  # noqa: E402
    load_merged_spy_vix,
    detect_all,
    simulate_set,
    BOOKS,
    EDGE_TIERS,
)
from autoresearch._edgehunt_vwap_continuation import _normalize_spy, _align_vix  # noqa: E402

MES_1M = REPO / "data" / "futures" / "MES_1m_continuous.csv"
OUT_MD = ROOT / "analysis" / "recommendations" / "SUNDAY-FRESH-ANGLES-SCORECARD.md"
OUT_JSON = ROOT / "analysis" / "recommendations" / "_sun_overnight_range_atr_gate.json"

ATR_LEN = 14
DRAWDOWN_START = dt.date(2026, 5, 14)   # the 25-trading-day live-drawdown window (recency_check)
DRAWDOWN_END = dt.date(2026, 6, 18)

# Band edges (web-sourced framework)
CHOP_HI = 0.25     # <25% of ATR = chop-leaning
TREND_LO = 0.50    # >50% of ATR = trend/expansion-leaning


# ─────────────────────────────────────────────────────────────────────────────
# OVERNIGHT-RANGE / ATR  (from MES 1m continuous incl. overnight)
# ─────────────────────────────────────────────────────────────────────────────
def load_mes_1m() -> pd.DataFrame:
    df = pd.read_csv(MES_1M)
    ts = pd.to_datetime(df["timestamp_et"], utc=True)
    df["ts"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def daily_atr_from_mes(mes: pd.DataFrame, length: int = ATR_LEN) -> dict[dt.date, float]:
    """Daily ATR(length) from MES RTH (09:30-16:00 ET) true range. Returns {date: ATR-as-of-PRIOR-close}
    so the value is causal (known before the session opens)."""
    rth = mes[(mes["ts"].dt.time >= dt.time(9, 30)) & (mes["ts"].dt.time < dt.time(16, 0))].copy()
    rth["date"] = rth["ts"].dt.date
    agg = rth.groupby("date").agg(high=("high", "max"), low=("low", "min"),
                                  close=("close", "last")).reset_index()
    agg = agg.sort_values("date").reset_index(drop=True)
    prev_close = agg["close"].shift(1)
    tr = np.maximum(agg["high"] - agg["low"],
                    np.maximum((agg["high"] - prev_close).abs(),
                               (agg["low"] - prev_close).abs()))
    atr = tr.rolling(length, min_periods=length).mean()
    # causal: ATR known at PRIOR close -> shift by 1 so date D uses ATR through D-1
    atr_asof = atr.shift(1)
    return {d: float(a) for d, a in zip(agg["date"], atr_asof) if pd.notna(a)}


def overnight_range_by_date(mes: pd.DataFrame) -> dict[dt.date, float]:
    """Overnight range = max(high)-min(low) over [18:00 prior calendar day -> 09:30 session day).
    Keyed by the SESSION (RTH) date. Walk RTH dates; window = prior 18:00 ET to that date 09:30 ET."""
    rth_dates = sorted({t.date() for t in mes["ts"] if dt.time(9, 30) <= t.time() < dt.time(16, 0)})
    ts = mes["ts"].values
    hi = mes["high"].values
    lo = mes["low"].values
    out: dict[dt.date, float] = {}
    for d in rth_dates:
        win_start = pd.Timestamp(dt.datetime.combine(d, dt.time(0, 0)) - dt.timedelta(hours=6))  # prior 18:00
        win_end = pd.Timestamp(dt.datetime.combine(d, dt.time(9, 30)))
        mask = (ts >= np.datetime64(win_start)) & (ts < np.datetime64(win_end))
        if not mask.any():
            continue
        out[d] = float(hi[mask].max() - lo[mask].min())
    return out


def overnight_ratio_by_date(mes: pd.DataFrame) -> dict[dt.date, dict]:
    atr = daily_atr_from_mes(mes)
    onr = overnight_range_by_date(mes)
    out: dict[dt.date, dict] = {}
    for d, r in onr.items():
        a = atr.get(d)
        if a is None or a <= 0:
            continue
        ratio = r / a
        band = "chop" if ratio < CHOP_HI else ("trend" if ratio > TREND_LO else "neutral")
        out[d] = {"overnight_range": round(r, 2), "atr": round(a, 2),
                  "ratio": round(ratio, 4), "band": band}
    return out


# ─────────────────────────────────────────────────────────────────────────────
# BOOK DAILY P&L (real fills, all books' members)
# ─────────────────────────────────────────────────────────────────────────────
def build_book_daily(rows_by_edge_tier: dict, members: list, start=None, end=None) -> dict[dt.date, float]:
    daily: dict[dt.date, float] = defaultdict(float)
    for edge, tier in members:
        for r in rows_by_edge_tier[(edge, tier)]:
            d = dt.date.fromisoformat(r["date"])
            if start and d < start:
                continue
            if end and d > end:
                continue
            daily[d] += r["pnl"]
    return dict(daily)


# ─────────────────────────────────────────────────────────────────────────────
# RISK-ADJUSTED METRICS on a daily P&L series
# ─────────────────────────────────────────────────────────────────────────────
def risk_metrics(daily: dict[dt.date, float]) -> dict:
    if not daily:
        return {"n_days": 0, "total": 0.0}
    days = sorted(daily)
    x = np.array([daily[d] for d in days], float)
    total = float(x.sum())
    mean = float(x.mean())
    sd = float(x.std(ddof=1)) if len(x) > 1 else 0.0
    downside = x[x < 0]
    dsd = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sharpe = (mean / sd * np.sqrt(252)) if sd > 0 else 0.0
    sortino = (mean / dsd * np.sqrt(252)) if dsd > 0 else 0.0
    eq = np.cumsum(x)
    peak = np.maximum.accumulate(eq)
    maxdd = float((eq - peak).min()) if len(eq) else 0.0
    return {
        "n_days": len(days),
        "total": round(total, 2),
        "daily_mean": round(mean, 2),
        "daily_sd": round(sd, 2),
        "sharpe_ann": round(sharpe, 3),
        "sortino_ann": round(sortino, 3),
        "max_dd": round(maxdd, 2),
        "win_days": int((x > 0).sum()),
        "loss_days": int((x < 0).sum()),
    }


def apply_mask(daily: dict[dt.date, float], ratios: dict[dt.date, dict],
               deploy_bands: set, keep_unclassified: bool) -> tuple[dict, dict, dict]:
    """Split daily P&L into DEPLOYED (kept) vs ABSTAINED (removed) by band membership.
    keep_unclassified: dates without an overnight-ratio are KEPT in deployed (can't abstain
    where we have no data)."""
    deployed, abstained, unclassified = {}, {}, {}
    for d, pnl in daily.items():
        info = ratios.get(d)
        if info is None:
            unclassified[d] = pnl
            if keep_unclassified:
                deployed[d] = pnl
            else:
                abstained[d] = pnl
            continue
        if info["band"] in deploy_bands:
            deployed[d] = pnl
        else:
            abstained[d] = pnl
    return deployed, abstained, unclassified


def bucket_breakdown(daily: dict[dt.date, float], ratios: dict[dt.date, dict]) -> dict:
    out = {}
    for band in ("chop", "neutral", "trend", "unclassified"):
        if band == "unclassified":
            vals = [pnl for d, pnl in daily.items() if d not in ratios]
        else:
            vals = [pnl for d, pnl in daily.items()
                    if d in ratios and ratios[d]["band"] == band]
        if vals:
            arr = np.array(vals, float)
            out[band] = {"n_days": len(vals), "total": round(float(arr.sum()), 2),
                         "daily_mean": round(float(arr.mean()), 2),
                         "win_days": int((arr > 0).sum()), "loss_days": int((arr < 0).sum())}
        else:
            out[band] = {"n_days": 0, "total": 0.0}
    return out


def eval_deploy_rule(name: str, daily: dict, ratios: dict, deploy_bands: set) -> dict:
    base = risk_metrics(daily)
    deployed, abstained, unclassified = apply_mask(daily, ratios, deploy_bands, keep_unclassified=True)
    md = risk_metrics(deployed)
    ab = risk_metrics(abstained)
    # no-regression: abstained days must sum NET-NEGATIVE (removing losers, not winners)
    abstained_net = ab.get("total", 0.0)
    no_regression_ok = abstained_net < 0
    sharpe_lift = round(md.get("sharpe_ann", 0) - base.get("sharpe_ann", 0), 3)
    sortino_lift = round(md.get("sortino_ann", 0) - base.get("sortino_ann", 0), 3)
    dd_improve = round(md.get("max_dd", 0) - base.get("max_dd", 0), 2)  # >0 = shallower DD = better
    risk_adj_better = (md.get("sharpe_ann", 0) > base.get("sharpe_ann", 0)) or \
                      (md.get("sortino_ann", 0) > base.get("sortino_ann", 0) and
                       md.get("max_dd", -1e9) >= base.get("max_dd", -1e9))
    accept = bool(risk_adj_better and no_regression_ok)
    return {
        "rule": name,
        "deploy_bands": sorted(deploy_bands),
        "base": base,
        "deployed": md,
        "abstained": ab,
        "n_unclassified_kept": len(unclassified),
        "abstained_net": round(abstained_net, 2),
        "no_regression_ok": no_regression_ok,
        "sharpe_lift": sharpe_lift,
        "sortino_lift": sortino_lift,
        "maxdd_improve": dd_improve,
        "ACCEPT": accept,
    }


def main() -> int:
    print("[onr] loading merged SPY+VIX + MES 1m ...", flush=True)
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    mes = load_mes_1m()
    ratios = overnight_ratio_by_date(mes)
    mes_dates = sorted(ratios)
    print(f"[onr] overnight-ratio computed for {len(ratios)} dates "
          f"{mes_dates[0]}..{mes_dates[-1]}", flush=True)
    band_ct = defaultdict(int)
    for v in ratios.values():
        band_ct[v["band"]] += 1
    print(f"[onr] band counts (full history): {dict(band_ct)}", flush=True)

    print("[onr] detecting #1/#2/#4 signals + simulating real fills ...", flush=True)
    sigs = detect_all(days, spy, vix)
    sigs.pop("_vix_cfg", None)
    rows_by_edge_tier: dict = {}
    for edge, tiers in EDGE_TIERS.items():
        for tier, off in tiers.items():
            rows, _ = simulate_set(sigs[edge], spy, ribbon, vix, strike_offset=off,
                                   setup=f"{edge}_{tier}")
            rows_by_edge_tier[(edge, tier)] = rows

    results = {}
    for book, members in BOOKS.items():
        # FULL-history book daily P&L
        daily_full = build_book_daily(rows_by_edge_tier, members)
        # restrict to overnight-data coverage for the gate eval (can only mask where we have data)
        cov_first, cov_last = mes_dates[0], mes_dates[-1]
        daily_cov = {d: p for d, p in daily_full.items() if cov_first <= d <= cov_last}
        # drawdown-window book daily P&L
        daily_dd = build_book_daily(rows_by_edge_tier, members, DRAWDOWN_START, DRAWDOWN_END)

        buckets_full = bucket_breakdown(daily_cov, ratios)
        buckets_dd = bucket_breakdown(daily_dd, ratios)

        # candidate deploy rules
        rule_ge25 = eval_deploy_rule("deploy_if_ratio>=25% (drop chop)", daily_cov, ratios,
                                     {"neutral", "trend"})
        rule_trend = eval_deploy_rule("deploy_if_ratio>50% (trend band only)", daily_cov, ratios,
                                      {"trend"})
        # same two rules evaluated on the drawdown window specifically
        rule_ge25_dd = eval_deploy_rule("DD-window deploy_if_ratio>=25%", daily_dd, ratios,
                                        {"neutral", "trend"})
        rule_trend_dd = eval_deploy_rule("DD-window deploy_if_ratio>50%", daily_dd, ratios,
                                         {"trend"})

        results[book] = {
            "members": [f"{e}/{t}" for e, t in members],
            "full_history_book": risk_metrics(daily_cov),
            "drawdown_window_book": risk_metrics(daily_dd),
            "buckets_full_history": buckets_full,
            "buckets_drawdown_window": buckets_dd,
            "rules": {
                "ge25_full": rule_ge25,
                "trend_full": rule_trend,
                "ge25_drawdown": rule_ge25_dd,
                "trend_drawdown": rule_trend_dd,
            },
        }

    out = {
        "slug": "overnight-range-pct-atr-regime-gate",
        "kind": "regime_gate (deploy-timing layer on the BOOK)",
        "run_date": dt.date.today().isoformat(),
        "hypothesis": ("overnight range (18:00 ET prior -> 09:30 ET, MES 1m) as fraction of daily "
                       "ATR(14): <25% chop-leaning (edges bleed), >50% trend-leaning (edges work); "
                       "deploy book only in trend-leaning band, abstain in chop"),
        "web_source": ("TradingView 'NQ Overnight Range (% of Daily ATR)' (rodtradessometimes) — "
                       "the <25%/25-50%/>50% chop/neutral/expansion framework; corroborated by "
                       "ATR-regime day-trading literature (StockCharts ATRP, TradeThatSwing ADR/IR)"),
        "bands": {"chop": f"<{CHOP_HI}", "neutral": f"{CHOP_HI}-{TREND_LO}", "trend": f">{TREND_LO}"},
        "the_bar": ("DEPLOY-TIMING (L174): ACCEPT only if (a) risk-adj better (Sharpe/Sortino up, "
                    "maxDD not worse) AND (b) abstained days sum NET-NEGATIVE (removing losers, not "
                    "winners). Winner-removal => REJECT."),
        "data": {
            "overnight_range_atr": f"MES_1m_continuous {mes_dates[0]}..{mes_dates[-1]} ({len(ratios)} dates)",
            "fills": "real OPRA via lib.simulator_real (C1)",
            "coverage_caveat": ("MES 1m ends 2026-06-12; OPRA fills end 2026-06-18 -> dates "
                                "2026-06-13..06-18 UNCLASSIFIED & kept-in-deployed (can't abstain "
                                "without overnight data). DD window 2026-05-14..06-18 covered thru 06-12."),
            "atr_causal": "ATR(14) from MES RTH daily TR, shifted +1 day (known at prior close)",
        },
        "band_counts_full_history": dict(band_ct),
        "books": results,
        "DISCLOSURE": {
            "real_fills": "real OPRA only — WR authority (C1); SPY-direction != option edge (C3/L58)",
            "per_trade": "book daily P&L; risk metrics on DAILY series; Sharpe ann x sqrt(252)",
            "no_winner_kill": "abstained-day net reported explicitly (L174 no-regression honesty)",
            "research_only": "no live edit, no orders (Sunday money-path guard)",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[onr] wrote {OUT_JSON}", flush=True)

    # ── console verdict ──
    print("\n=== OVERNIGHT-RANGE/ATR DEPLOY-TIMING GATE — VERDICT ===")
    for book, b in results.items():
        print(f"\nBOOK {book}  members={b['members']}")
        fh = b["full_history_book"]
        print(f"  full-hist(book, overnight-covered): n_days={fh['n_days']} total=${fh['total']} "
              f"Sharpe={fh['sharpe_ann']} Sortino={fh['sortino_ann']} maxDD=${fh['max_dd']}")
        print(f"  buckets(full): " + " | ".join(
            f"{k}: n={v['n_days']} ${v.get('total')}" for k, v in b["buckets_full_history"].items()))
        for rk, r in b["rules"].items():
            print(f"  RULE[{rk}] {r['rule']}: deployed Sharpe={r['deployed'].get('sharpe_ann')} "
                  f"(base {r['base'].get('sharpe_ann')}, lift {r['sharpe_lift']}) "
                  f"abstained_net=${r['abstained_net']} no_regression={r['no_regression_ok']} "
                  f"-> {'ACCEPT' if r['ACCEPT'] else 'REJECT'}")
    return out


if __name__ == "__main__":
    res = main()
    sys.exit(0)
