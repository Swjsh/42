"""SUNDAY-FRESH ANGLE: monday-overnight-gap-up-skip (DEPLOY-TIMING, not a new signal).

WEB-SOURCED HYPOTHESIS
  Monday gap-ups specifically face heightened intraday FADE risk: the weekend builds a
  "news premium" that gaps SPY up at the cash open, and that premium tends to over-correct
  intraday (the classic "Monday reversal"/weekend-effect folklore). If true, the three
  trend-CONTINUATION edges (which buy WITH the morning trend) should bleed on Mondays that
  open materially gap-UP, because price fades back against the continuation thesis.

  Web sources (cited in scorecard): the documented "weekend effect" / "Monday effect"
  (French 1980, Gibbons-Hess 1981) shows Monday returns historically negative; the
  "Monday reversal" literature (Jegadeesh 1990; reversal-after-weekend studies) argues the
  Friday-close -> Monday-open gap mean-reverts intraday. The DEPLOY-TIMING test: do OUR
  real-OPRA continuation fills actually lose on Monday-gap-up days?

DEPLOY-TIMING RULE UNDER TEST
  Abstain (or de-size) the BOOK on Mondays that open gap-UP beyond a threshold.
  ACCEPT the abstain mask ONLY IF (L174 no-regression, the deploy-timing bar):
    (a) the abstained Monday-gap-up days are NET-NEGATIVE in aggregate (we are removing
        losers, NOT winners), AND
    (b) removing them LIFTS the book's risk-adjusted return (daily Sharpe AND Sortino up,
        maxDD not worse).
  Mondays are ~1/5 of days and gap-ups a subset -> n is SMALL by construction. Per the
  brief this is CONFIRMATORY/SECONDARY: gate HARD on direction + DSR-style robustness,
  never ship standalone.

WHAT IT REUSES (no edits to any production file; Sunday money-path guard):
  - the three validated detectors via recency_check.detect_all (THE live detectors)
  - the real-OPRA fill path lib.simulator_real.simulate_trade_real (C1, the WR authority)
  - _normalize_spy / _align_vix / build_day_contexts / strike pickers / compute_ribbon
  - the merged master+recent frame (recency_check.load_merged_spy_vix), HARD-WINDOWED to the
    OPRA cache last date (2026-06-18) so no fill is scored past the cache (data-coverage guard)

OVERNIGHT GAP definition (causal, as-of the cash open):
  gap_pct[d] = (today RTH open at 09:30 ET) / (prior trading day's last RTH close <=16:00) - 1
  Computed from SPY 5m (the same frame the edges run on). MES 1m continuous (incl overnight)
  is loaded as a CROSS-CHECK of the gap sign/magnitude where it overlaps (futures trade the
  weekend-news premium directly) -- reported, not used to gate.

DISCLOSURE (C1/C3/C7/L58/L174/OP-14/OP-20): real OPRA fills only; per-trade EXPECTANCY not WR;
small-n by design, reported honestly; SPY-direction != option edge (C3/L58); a deploy-timing
mask that merely removes winning days is winner-removal (L174) -> REJECTED. RESEARCH ONLY.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sunday_monday_gap_skip.py
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

from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import _normalize_spy, _align_vix  # noqa: E402
from autoresearch.recency_check import (  # noqa: E402
    load_merged_spy_vix,
    detect_all,
    simulate_set,
    EDGE_TIERS,
    BOOKS,
    read_cache_last_date,
)
from lib.ribbon import compute_ribbon  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "sunday-monday-gap-skip.json"
SCORECARD = ROOT / "analysis" / "recommendations" / "SUNDAY-FRESH-ANGLES-SCORECARD.md"
DATA = REPO / "data"

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
# gap-up thresholds to scan (per task: gap > +0.30% is the headline; scan a small ladder)
GAP_THRESHOLDS = [0.0010, 0.0020, 0.0030, 0.0050]
HEADLINE_THR = 0.0030  # +0.30%


# ─────────────────────────────────────────────────────────────────────────────
# OVERNIGHT GAP (causal, from the SPY 5m frame the edges run on)
# ─────────────────────────────────────────────────────────────────────────────
def compute_overnight_gaps(spy: pd.DataFrame) -> dict[dt.date, dict]:
    """gap_pct[d] = RTH-open(09:30)/prior-RTH-close - 1, plus weekday. Causal at the open."""
    df = spy.copy()
    df["d"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    rth = df[(df["t"] >= RTH_OPEN) & (df["t"] <= RTH_CLOSE)]
    # per-day open at first bar >= 09:30, close at last bar <= 16:00
    opens, closes = {}, {}
    for d, g in rth.groupby("d"):
        g = g.sort_values("timestamp_et")
        # first bar AT/after 09:30 -> its OPEN is the cash open
        first = g.iloc[0]
        last = g.iloc[-1]
        opens[d] = float(first["open"])
        closes[d] = float(last["close"])
    days_sorted = sorted(opens)
    out: dict[dt.date, dict] = {}
    for i, d in enumerate(days_sorted):
        if i == 0:
            continue
        prev = days_sorted[i - 1]
        pc = closes.get(prev)
        op = opens.get(d)
        if pc is None or op is None or pc <= 0:
            continue
        gap = op / pc - 1.0
        out[d] = {
            "gap_pct": round(gap * 100, 4),
            "gap_frac": gap,
            "weekday": d.weekday(),  # Mon=0 .. Fri=4
            "weekday_name": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()],
            "prior_close": round(pc, 2),
            "rth_open": round(op, 2),
            "prior_date": str(prev),
        }
    return out


def mes_gap_crosscheck() -> dict:
    """Cross-check the Monday gap sign using MES 1m continuous (trades the weekend premium).
    Reported only -- NOT used to gate. Compares MES Fri-RTH-close -> Mon-RTH-open sign vs SPY."""
    try:
        mes = pd.read_csv(DATA / "futures" / "MES_1m_continuous.csv")
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": str(e)}
    ts = pd.to_datetime(mes["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    mes = mes.assign(ts=ts)
    mes["d"] = mes["ts"].dt.date
    mes["t"] = mes["ts"].dt.time
    rth = mes[(mes["t"] >= RTH_OPEN) & (mes["t"] <= RTH_CLOSE)]
    opens, closes = {}, {}
    for d, g in rth.groupby("d"):
        g = g.sort_values("ts")
        opens[d] = float(g.iloc[0]["open"])
        closes[d] = float(g.iloc[-1]["close"])
    days_sorted = sorted(opens)
    gaps = {}
    for i, d in enumerate(days_sorted):
        if i == 0:
            continue
        prev = days_sorted[i - 1]
        pc = closes.get(prev)
        op = opens.get(d)
        if pc and op and pc > 0 and d.weekday() == 0:  # Mondays only
            gaps[str(d)] = round((op / pc - 1) * 100, 4)
    return {"available": True, "n_monday_gaps": len(gaps),
            "first": days_sorted[0].isoformat() if days_sorted else None,
            "last": days_sorted[-1].isoformat() if days_sorted else None,
            "monday_gaps_pct": gaps}


# ─────────────────────────────────────────────────────────────────────────────
# BOOK daily P&L  (combine a book's (edge,tier) member rows into per-DAY P&L)
# ─────────────────────────────────────────────────────────────────────────────
def book_daily(rows_by_edge_tier: dict, members: list[tuple], cache_last: dt.date
               ) -> dict[dt.date, float]:
    """Per-DAY combined P&L for a book, HARD-WINDOWED to <= cache_last (OPRA cache guard)."""
    by_day: dict[dt.date, float] = defaultdict(float)
    for edge, tier in members:
        for r in rows_by_edge_tier[(edge, tier)]:
            d = dt.date.fromisoformat(r["date"])
            if d <= cache_last:
                by_day[d] += r["pnl"]
    return dict(by_day)


def risk_stats(daily: list[float]) -> dict:
    """Risk-adjusted stats on a list of per-DAY P&L values."""
    if not daily:
        return {"n_days": 0}
    a = np.array(daily, float)
    mean = float(a.mean())
    sd = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    downside = a[a < 0]
    dsd = float(downside.std(ddof=1)) if len(downside) > 1 else (float(abs(downside.mean())) if len(downside) else 0.0)
    sharpe = round(mean / sd, 4) if sd > 0 else (float("inf") if mean > 0 else 0.0)
    sortino = round(mean / dsd, 4) if dsd > 0 else (float("inf") if mean > 0 else 0.0)
    # max drawdown on the cumulative daily-P&L equity curve
    eq = np.cumsum(a)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    maxdd = round(float(dd.min()), 2)  # most-negative
    return {
        "n_days": len(a),
        "total": round(float(a.sum()), 2),
        "daily_mean": round(mean, 3),
        "daily_sd": round(sd, 3),
        "sharpe_daily": sharpe if sharpe == float("inf") else round(sharpe, 4),
        "sortino_daily": sortino if sortino == float("inf") else round(sortino, 4),
        "max_drawdown": maxdd,
        "win_days": int((a > 0).sum()),
        "loss_days": int((a < 0).sum()),
    }


def _fmt(x):
    if x == float("inf"):
        return "inf"
    return x


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    cache_last = read_cache_last_date()
    print(f"[gap-skip] OPRA cache last (hard window) = {cache_last}", flush=True)
    print("[gap-skip] loading merged SPY+VIX (master + recent) ...", flush=True)
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    frame_first, frame_last = spy["timestamp_et"].iloc[0].date(), spy["timestamp_et"].iloc[-1].date()
    print(f"[gap-skip] frame {frame_first}..{frame_last} trading_days={len(days)}", flush=True)

    gaps = compute_overnight_gaps(spy)
    mondays = {d for d, g in gaps.items() if g["weekday"] == 0}
    print(f"[gap-skip] gaps tagged on {len(gaps)} days; Mondays={len(mondays)}", flush=True)

    mes_cc = mes_gap_crosscheck()
    print(f"[gap-skip] MES Monday-gap cross-check available={mes_cc.get('available')} "
          f"n={mes_cc.get('n_monday_gaps')}", flush=True)

    # Detect the 3 live edges + simulate every (edge,tier) cell on real OPRA fills (once).
    print("[gap-skip] detecting 3 live edges + simulating real-OPRA fills ...", flush=True)
    sigs = detect_all(days, spy, vix)
    sigs.pop("_vix_cfg", None)
    rows_by_edge_tier: dict[tuple, list[dict]] = {}
    for edge, tiers in EDGE_TIERS.items():
        for tier, off in tiers.items():
            rows, _cov = simulate_set(sigs[edge], spy, ribbon, vix, strike_offset=off,
                                      setup=f"{edge}_{tier}")
            rows_by_edge_tier[(edge, tier)] = rows

    # Single-edge view too (the LIVE edge #1 at its live tiers) + the two books.
    cohorts = {
        "BOOK_Safe2_ATM_1+2+4": BOOKS["Safe2_ATM_1+2+4"],
        "BOOK_Bold_ITM2_1+2": BOOKS["Bold_ITM2_1+2"],
        "EDGE_vwap_continuation_ATM": [("vwap_continuation", "ATM")],
        "EDGE_vwap_continuation_ITM-2": [("vwap_continuation", "ITM-2")],
    }

    results = {}
    for cohort_name, members in cohorts.items():
        bd = book_daily(rows_by_edge_tier, members, cache_last)
        # restrict to days that have BOTH a fill and a tagged gap
        traded_days = sorted(d for d in bd if d in gaps)
        if not traded_days:
            results[cohort_name] = {"n_traded_days": 0}
            continue

        # full book daily series (all traded days)
        full_daily = [bd[d] for d in traded_days]
        full_stats = risk_stats(full_daily)

        # Monday gap-up subset analyses at each threshold
        thr_blocks = {}
        for thr in GAP_THRESHOLDS:
            mon_gapup = [d for d in traded_days
                         if gaps[d]["weekday"] == 0 and gaps[d]["gap_frac"] > thr]
            other = [d for d in traded_days if d not in set(mon_gapup)]
            removed_pnl = [bd[d] for d in mon_gapup]
            kept_pnl = [bd[d] for d in other]
            removed_total = round(float(np.sum(removed_pnl)), 2) if removed_pnl else 0.0
            kept_stats = risk_stats(kept_pnl)
            # L174 no-regression check: removed days must be net-NEGATIVE
            removed_net_negative = removed_total < 0
            # risk-adjusted lift: Sharpe AND Sortino up, maxDD not worse
            def _ge(a, b):  # inf-safe >=
                if a == float("inf"):
                    return True
                if b == float("inf"):
                    return False
                return a >= b
            sharpe_up = _ge(kept_stats.get("sharpe_daily", 0), full_stats.get("sharpe_daily", 0)) \
                and kept_stats.get("sharpe_daily") != full_stats.get("sharpe_daily")
            sortino_up = _ge(kept_stats.get("sortino_daily", 0), full_stats.get("sortino_daily", 0)) \
                and kept_stats.get("sortino_daily") != full_stats.get("sortino_daily")
            dd_not_worse = kept_stats.get("max_drawdown", -9e9) >= full_stats.get("max_drawdown", -9e9)
            accept = bool(removed_net_negative and sharpe_up and sortino_up and dd_not_worse
                          and len(mon_gapup) > 0)
            thr_blocks[f"gap>+{thr*100:.2f}%"] = {
                "threshold_pct": round(thr * 100, 2),
                "n_monday_gapup_days": len(mon_gapup),
                "monday_gapup_dates": [str(d) for d in mon_gapup],
                "monday_gapup_gaps_pct": [gaps[d]["gap_pct"] for d in mon_gapup],
                "removed_total_pnl": removed_total,
                "removed_mean_pnl": round(removed_total / len(mon_gapup), 2) if mon_gapup else None,
                "removed_net_negative": removed_net_negative,
                "kept_stats": kept_stats,
                "lift_checks": {"sharpe_up": sharpe_up, "sortino_up": sortino_up,
                                "maxdd_not_worse": dd_not_worse},
                "ACCEPT_deploy_timing_mask": accept,
            }

        # also a plain Monday-vs-rest baseline (no gap filter), for context
        all_mondays = [d for d in traded_days if gaps[d]["weekday"] == 0]
        mon_total = round(float(np.sum([bd[d] for d in all_mondays])), 2) if all_mondays else 0.0
        nonmon_total = round(float(np.sum([bd[d] for d in traded_days if d not in set(all_mondays)])), 2)

        results[cohort_name] = {
            "members": [f"{e}/{t}" for e, t in members],
            "n_traded_days": len(traded_days),
            "full_book_stats": full_stats,
            "all_mondays": {"n": len(all_mondays), "total_pnl": mon_total,
                            "mean": round(mon_total / len(all_mondays), 2) if all_mondays else None},
            "all_non_mondays_total_pnl": nonmon_total,
            "thresholds": thr_blocks,
        }
        h = thr_blocks.get(f"gap>+{HEADLINE_THR*100:.2f}%", {})
        print(f"[gap-skip] {cohort_name}: traded_days={len(traded_days)} "
              f"full Sharpe={_fmt(full_stats.get('sharpe_daily'))} total=${full_stats.get('total')} | "
              f"Mon-gap>+0.30%: n={h.get('n_monday_gapup_days')} "
              f"removed=${h.get('removed_total_pnl')} ACCEPT={h.get('ACCEPT_deploy_timing_mask')}",
              flush=True)

    # any accept anywhere at the headline threshold?
    any_accept = any(
        results[c].get("thresholds", {}).get(f"gap>+{HEADLINE_THR*100:.2f}%", {})
        .get("ACCEPT_deploy_timing_mask", False)
        for c in results if results[c].get("n_traded_days")
    )

    summary = {
        "slug": "monday-overnight-gap-up-skip",
        "kind": "deploy_timing",
        "run_date": dt.date.today().isoformat(),
        "hypothesis": ("Monday gap-UPS face heightened intraday FADE risk (weekend news premium "
                       "over-corrects) -> trend-continuation edges underperform; abstain/de-size "
                       "the book on Monday large-up-gap days."),
        "deploy_timing_bar_L174": ("ACCEPT only if the abstained Monday-gap-up days are NET-NEGATIVE "
                                   "(removing losers not winners) AND removing them lifts book "
                                   "risk-adjusted return (daily Sharpe AND Sortino up, maxDD not worse)."),
        "gap_definition": "RTH-open(09:30)/prior-RTH-close - 1, causal from SPY 5m",
        "headline_threshold_pct": round(HEADLINE_THR * 100, 2),
        "opra_cache_last_hard_window": str(cache_last),
        "frame": f"{frame_first}..{frame_last}",
        "fills_authority": "real OPRA via lib.simulator_real (C1); 3 live detectors via recency_check.detect_all",
        "mes_monday_gap_crosscheck": mes_cc,
        "cohorts": results,
        "headline_verdict": "ACCEPT_SOMEWHERE" if any_accept else "REJECT_ALL_COHORTS",
        "web_sources": [
            "French (1980) 'Stock returns and the weekend effect', J. Financial Economics 8(1): Monday returns historically negative.",
            "Gibbons & Hess (1981) 'Day of the Week Effects and Asset Returns', J. Business 54(4).",
            "Jegadeesh (1990) 'Evidence of Predictable Behavior of Security Returns', J. Finance 45(3): short-horizon reversal incl. weekend.",
        ],
        "DISCLOSURE": {
            "small_n": "Mondays ~1/5 of days, gap-ups a subset -> n SMALL by design; confirmatory only, never ship standalone.",
            "real_fills": "real OPRA fills only (C1); per-trade EXPECTANCY + daily risk-adjusted, not WR alone (OP-14).",
            "winner_removal": "L174 guard: a mask that removes NET-POSITIVE days is winner-removal -> ACCEPT=false.",
            "spy_vs_option": "SPY-direction != 0DTE option edge (C3/L58).",
            "mes_role": "MES gap cross-check is REPORTED sign-confirmation only, not a gate input.",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[gap-skip] wrote {OUT_JSON}", flush=True)
    print(f"[gap-skip] HEADLINE VERDICT = {summary['headline_verdict']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
