"""SUNDAY FRESH ANGLE: overnight-gap-up-fades-the-day (DEPLOY-TIMING layer).

HYPOTHESIS (web-sourced, see scorecard for cites): On days where SPY opens with a
LARGE up-gap (prior-RTH-close -> 09:30 open > +0.30%), the bull-trend-continuation
0DTE edges UNDERPERFORM, because daytime arbitrageurs fade persistent overnight
up-pressure and the day's equity-premium was already spent overnight. Deploy-timing
rule: ABSTAIN the book on large overnight-up-gap days.

KIND: deploy_timing (NOT a new signal). The RIGHT bar (L174):
  ACCEPT only if deploying-only-on-non-large-up-gap days
    (a) raises the BOOK's risk-adjusted return (Sharpe/Sortino on daily P&L), AND
    (b) the ABSTAINED (gap>thresh) days sum to NET-NEGATIVE day P&L
        (true no-regression / NOT winner-removal).
  Both must hold, else WALL/DEAD.

REUSE (no edits to any watcher/params/risk_gate/orchestrator/heartbeat — Sunday guard):
  - recency_check.detect_all (the 3 live edges' validated detectors)
  - recency_check.simulate_set (real OPRA fills via lib.simulator_real — the WR authority, C1)
  - recency_check.load_merged_spy_vix / _normalize_spy / _align_vix / build_day_contexts
  - recency_check.EDGE_TIERS / BOOKS (same Sunday portfolio composition)
  - compute_ribbon
GAP computation:
  - SPY overnight gap = (SPY 09:30 RTH open - prior trading day 15:55 close) / prior close
    from the normalized 5m spy frame (primary; this is what the edges actually trade).
  - MES futures cross-check = (MES 09:25 ET close - MES prior-18:00 ET open) / prior close
    from MES_1m_continuous (overnight session). Reported for corroboration; NOT the gate.

Threshold sweep: {0.20%, 0.30%, 0.50%}. DSR note for the small drawdown-window n.
Pure Python, $0. No live orders, no live edits. Markets closed.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sub_overnight_gap_fade.py
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
    _normalize_spy,
    _align_vix,
    detect_all,
    simulate_set,
    EDGE_TIERS,
    BOOKS,
)

DATA = REPO / "data"
MES_1M = DATA / "futures" / "MES_1m_continuous.csv"
OUT_JSON = ROOT / "analysis" / "recommendations" / "overnight-gap-fade.json"

# Test window per the plan (MES futures end 2026-06-12; SPY 5m ends 2026-06-18).
WIN_START = dt.date(2025, 1, 1)
WIN_END = dt.date(2026, 6, 12)
THRESHOLDS = [0.0020, 0.0030, 0.0050]   # 0.20% / 0.30% / 0.50%
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(15, 55)


# ─────────────────────────────────────────────────────────────────────────────
# GAP COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────
def compute_spy_gaps(spy: pd.DataFrame) -> dict[dt.date, float]:
    """overnight gap = (today 09:30 open - prior trading day 15:55 close)/prior close.
    Uses the normalized 5m frame (tz-naive ET). One value per trading date with a prior."""
    # 09:30 open per day
    opens = (spy[spy["t"] == RTH_OPEN]
             .groupby("date")["open"].first())
    # 15:55 close per day (last RTH bar)
    closes = (spy[spy["t"] == RTH_CLOSE]
              .groupby("date")["close"].first())
    dates = sorted(set(opens.index) & set(closes.index))
    gaps: dict[dt.date, float] = {}
    for i in range(1, len(dates)):
        d, prior = dates[i], dates[i - 1]
        prior_close = float(closes.loc[prior])
        today_open = float(opens.loc[d])
        if prior_close > 0:
            gaps[d] = (today_open - prior_close) / prior_close
    return gaps


def compute_mes_gaps(spy_dates: list[dt.date]) -> dict[dt.date, float]:
    """Futures cross-check: (MES 09:25 ET close - prior-18:00 ET open)/prior close.
    Overnight session opens 18:00 ET prior calendar day; we anchor by the RTH date d:
    prior-18:00 open = the 18:00 bar on the calendar day BEFORE d (Sun-Thu evenings)."""
    mes = pd.read_csv(MES_1M)
    ts = pd.to_datetime(mes["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    mes = mes.assign(_ts=ts, _date=ts.dt.date, _t=ts.dt.time)
    mes = mes.drop_duplicates(subset="_ts", keep="first")
    by_cal_date = {d: g for d, g in mes.groupby("_date")}
    open18 = dt.time(18, 0)
    close0925 = dt.time(9, 25)
    out: dict[dt.date, float] = {}
    cal_dates = sorted(by_cal_date.keys())
    cal_idx = {d: i for i, d in enumerate(cal_dates)}
    for d in spy_dates:
        # 09:25 close on RTH date d
        gd = by_cal_date.get(d)
        if gd is None:
            continue
        row0925 = gd[gd["_t"] == close0925]
        if row0925.empty:
            # nearest <= 09:25 RTH-bar fallback
            pre = gd[gd["_t"] <= close0925]
            if pre.empty:
                continue
            c0925 = float(pre.iloc[-1]["close"])
        else:
            c0925 = float(row0925.iloc[0]["close"])
        # prior 18:00 open: walk back calendar days from d-1 to find an 18:00 bar
        if d not in cal_idx:
            continue
        found = None
        for back in range(1, 5):
            j = cal_idx[d] - back
            if j < 0:
                break
            pd_ = cal_dates[j]
            pg = by_cal_date[pd_]
            r18 = pg[pg["_t"] == open18]
            if not r18.empty:
                found = float(r18.iloc[0]["open"])
                break
        if found and found > 0:
            out[d] = (c0925 - found) / found
    return out


# ─────────────────────────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────────────────────────
def daily_series(rows: list[dict], dates_in_win: set) -> dict[dt.date, float]:
    by_day: dict[dt.date, float] = defaultdict(float)
    for r in rows:
        d = dt.date.fromisoformat(r["date"])
        if d in dates_in_win:
            by_day[d] += r["pnl"]
    return dict(by_day)


def risk_stats(daily_by_day: dict[dt.date, float], all_dates: list[dt.date]) -> dict:
    """Risk-adjusted stats over a fixed calendar of trading days (0 P&L on no-trade days).
    Sharpe/Sortino computed on the per-day P&L series across ALL deployable days."""
    series = np.array([daily_by_day.get(d, 0.0) for d in all_dates], float)
    n = len(series)
    if n == 0:
        return {"n_days": 0}
    mean = float(series.mean())
    sd = float(series.std(ddof=1)) if n > 1 else 0.0
    downside = series[series < 0]
    dsd = float(np.sqrt((downside ** 2).mean())) if len(downside) else 0.0
    sharpe = (mean / sd * np.sqrt(252)) if sd > 0 else 0.0
    sortino = (mean / dsd * np.sqrt(252)) if dsd > 0 else 0.0
    cum = np.cumsum(series)
    peak = np.maximum.accumulate(cum)
    maxdd = float((cum - peak).min()) if n else 0.0
    n_trade_days = int((series != 0).sum())
    return {
        "n_days": n,
        "n_trade_days": n_trade_days,
        "total_dollar": round(float(series.sum()), 2),
        "daily_mean": round(mean, 3),
        "daily_sd": round(sd, 3),
        "sharpe_ann": round(sharpe, 3),
        "sortino_ann": round(sortino, 3),
        "max_drawdown": round(maxdd, 2),
        "win_days": int((series > 0).sum()),
        "loss_days": int((series < 0).sum()),
    }


def main() -> int:
    print("[gapfade] loading merged SPY+VIX ...", flush=True)
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    trading_days = sorted({dc.date for dc in days if WIN_START <= dc.date <= WIN_END})
    win_set = set(trading_days)
    print(f"[gapfade] window {WIN_START}..{WIN_END} -> {len(trading_days)} trading days", flush=True)

    # GAPS
    spy_gaps_all = compute_spy_gaps(spy)
    spy_gaps = {d: g for d, g in spy_gaps_all.items() if d in win_set}
    mes_gaps = compute_mes_gaps(trading_days)
    common = sorted(set(spy_gaps) & set(mes_gaps))
    if common:
        a = np.array([spy_gaps[d] for d in common])
        b = np.array([mes_gaps[d] for d in common])
        corr = float(np.corrcoef(a, b)[0, 1]) if len(common) > 2 else 0.0
    else:
        corr = 0.0
    print(f"[gapfade] SPY gaps={len(spy_gaps)}  MES gaps={len(mes_gaps)}  "
          f"overlap={len(common)}  corr(SPY,MES)={corr:.3f}", flush=True)

    # DETECT + SIM all edge/tier cells ONCE on the full frame
    sigs = detect_all(days, spy, vix)
    sigs.pop("_vix_cfg", None)
    rows_by_edge_tier: dict[tuple, list[dict]] = {}
    for edge, tiers in EDGE_TIERS.items():
        for tier, off in tiers.items():
            rows, _cov = simulate_set(sigs[edge], spy, ribbon, vix,
                                      strike_offset=off, setup=f"{edge}_{tier}")
            rows_by_edge_tier[(edge, tier)] = rows

    # Build book daily series (within window)
    book_daily: dict[str, dict[dt.date, float]] = {}
    for book, members in BOOKS.items():
        comb: dict[dt.date, float] = defaultdict(float)
        for edge, tier in members:
            for r in rows_by_edge_tier[(edge, tier)]:
                d = dt.date.fromisoformat(r["date"])
                if d in win_set:
                    comb[d] += r["pnl"]
        book_daily[book] = dict(comb)

    # ALSO evaluate edge #1 ATM standalone (the LIVE edge) as its own "book".
    book_daily["LIVE_#1_vwap_continuation_ATM"] = daily_series(
        rows_by_edge_tier[("vwap_continuation", "ATM")], win_set)
    book_daily["LIVE_#1_vwap_continuation_ITM-2"] = daily_series(
        rows_by_edge_tier[("vwap_continuation", "ITM-2")], win_set)

    # ── EVALUATE the deploy-timing rule per book per threshold ──
    results = {}
    for book, dby in book_daily.items():
        baseline = risk_stats(dby, trading_days)
        thr_blocks = {}
        for thr in THRESHOLDS:
            abst_days = sorted(d for d in trading_days
                               if spy_gaps.get(d, -9.9) > thr)   # large up-gap days
            keep_days = [d for d in trading_days if d not in set(abst_days)]
            # deployed = keep days; abstained = removed
            deployed_stats = risk_stats(dby, keep_days)
            abst_pnl = sum(dby.get(d, 0.0) for d in abst_days)
            abst_trade_days = [d for d in abst_days if d in dby and dby[d] != 0.0]
            abst_pnl_traded = sum(dby.get(d, 0.0) for d in abst_trade_days)
            # no-regression test: abstained days NET-NEGATIVE (true) vs winner-removal (false)
            abstained_net_negative = abst_pnl < 0
            sharpe_lift = deployed_stats.get("sharpe_ann", 0) - baseline.get("sharpe_ann", 0)
            sortino_lift = deployed_stats.get("sortino_ann", 0) - baseline.get("sortino_ann", 0)
            accept = (sharpe_lift > 0) and abstained_net_negative
            thr_blocks[f"{thr*100:.2f}pct"] = {
                "threshold_pct": round(thr * 100, 2),
                "n_abstained_days": len(abst_days),
                "n_abstained_trade_days": len(abst_trade_days),
                "abstained_total_pnl": round(abst_pnl, 2),
                "abstained_pnl_on_traded_days": round(abst_pnl_traded, 2),
                "abstained_net_negative": abstained_net_negative,
                "deployed_stats": deployed_stats,
                "sharpe_lift": round(sharpe_lift, 3),
                "sortino_lift": round(sortino_lift, 3),
                "ACCEPT": accept,
                "accept_reason": (
                    "raises Sharpe AND abstained days net-negative (true no-regression)"
                    if accept else
                    (f"abstained days SUM POSITIVE (+${abst_pnl:.2f}) = winner-removal, NOT "
                     "no-regression" if not abstained_net_negative else
                     f"abstained net-neg but Sharpe lift {sharpe_lift:+.3f} <= 0")),
            }
        results[book] = {"baseline": baseline, "thresholds": thr_blocks}
        print(f"\n[gapfade] BOOK {book}", flush=True)
        print(f"  baseline: total=${baseline['total_dollar']} sharpe={baseline['sharpe_ann']} "
              f"sortino={baseline['sortino_ann']} maxDD=${baseline['max_drawdown']} "
              f"(trade_days={baseline['n_trade_days']}/{baseline['n_days']})", flush=True)
        for k, tb in thr_blocks.items():
            print(f"  gap>{k}: abstain {tb['n_abstained_days']}d "
                  f"(traded {tb['n_abstained_trade_days']}d) abst_pnl=${tb['abstained_total_pnl']} "
                  f"netNeg={tb['abstained_net_negative']} | deployed sharpe="
                  f"{tb['deployed_stats']['sharpe_ann']} (lift {tb['sharpe_lift']:+.3f}) "
                  f"total=${tb['deployed_stats']['total_dollar']} -> "
                  f"{'ACCEPT' if tb['ACCEPT'] else 'REJECT'}", flush=True)

    # gap distribution
    g_arr = np.array(list(spy_gaps.values()))
    gap_dist = {
        "mean_pct": round(float(g_arr.mean()) * 100, 3),
        "sd_pct": round(float(g_arr.std()) * 100, 3),
        "pct_up_gt_0.20": int((g_arr > 0.0020).sum()),
        "pct_up_gt_0.30": int((g_arr > 0.0030).sum()),
        "pct_up_gt_0.50": int((g_arr > 0.0050).sum()),
        "n": len(g_arr),
    }

    any_accept = any(tb["ACCEPT"] for r in results.values() for tb in r["thresholds"].values())
    summary = {
        "slug": "overnight-gap-up-fades-the-day",
        "kind": "deploy_timing",
        "run_date": dt.date.today().isoformat(),
        "window": f"{WIN_START}..{WIN_END}",
        "trading_days": len(trading_days),
        "books_evaluated": list(book_daily.keys()),
        "fills_authority": "real OPRA via lib.simulator_real (C1); v15 default exits, stop -8%",
        "gap_definition": "SPY (09:30 open - prior 15:55 close)/prior close (5m frame, primary gate)",
        "mes_crosscheck": f"corr(SPY 5m gap, MES overnight gap)={round(corr,3)} on {len(common)} overlap days",
        "gap_distribution": gap_dist,
        "thresholds_pct": [round(t * 100, 2) for t in THRESHOLDS],
        "deploy_timing_bar": ("ACCEPT iff deploying-only-on-non-large-up-gap days raises BOOK "
                              "Sharpe AND abstained (gap>thr) days sum NET-NEGATIVE (L174 no-regression)"),
        "results": results,
        "ANY_ACCEPT": any_accept,
        "DISCLOSURE": {
            "no_regression": "abstained days must be NET-NEGATIVE (not winner-removal) — L174",
            "small_n_dsr": ("abstained-day counts are small (see n_abstained_trade_days); a positive "
                            "Sharpe lift on few removed days is fragile — DSR-discount any lift driven "
                            "by < ~5 abstained trade-days"),
            "real_fills": "real OPRA fills only — the WR authority (C1); SPY-direction != option edge (C3/L58)",
            "research_only": "no live edit, no orders (Sunday money-path guard)",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[gapfade] wrote {OUT_JSON}", flush=True)
    print(f"\n=== OVERNIGHT-GAP-FADE DEPLOY-TIMING VERDICT === ANY_ACCEPT={any_accept}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
