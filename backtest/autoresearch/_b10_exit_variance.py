"""B10 — WP-4 VARIANCE / DOWNSIDE audit (the ONE open caveat that makes WP-4 ratify-ready).

The B10 exit sweep (_b10_exit_audit.py) found TP1 +30% -> +75% lifts the 3-edge book's
MEAN per-trade expectancy by +$13.23/tr (Safe-2 ATM) / +$17.17/tr (Bold ITM-2), broad-based
across IS(2025)+OOS(2026). The audit flagged ONE caveat for the daytime ratify gate:

    a higher TP1 banks less early and carries MORE theta/stop exposure on days the trade does
    NOT run -> verify per-trade VARIANCE / downside, not just the mean.

This module computes EXACTLY that, for the WINNING config (tp1=0.75, tp1_qty=0.50, runner=3.0x,
time=15:30) vs the v15 BASELINE (tp1=0.30, tp1_qty=0.50, runner=2.5x, time=15:50), for BOTH books.

It REUSES the exact detectors + real-OPRA-fill plumbing from _b10_exit_audit.py (imports
simulate_book / BOOKS composition / the same signal detection) — it does NOT rebuild detectors.

Sections:
  1. Per-trade distribution: mean, STD, Sharpe-per-trade (mean/std), skew, P05/P25/median/P75/P95,
     worst single trade, % losing trades.
  2. Downside-specific: mean of losing trades; count+total of trades that get WORSE under +75% vs
     +30% (the no-run-day exposure the caveat warns about); and what those worse trades have in
     common (exit-reason mix on the worse set — do non-running days lose more because TP1 isn't hit
     and theta/stop bites?).
  3. Book-level (daily equity): max drawdown, worst day, downside-deviation, annualized Sortino
     (target 0) AND annualized Sharpe under each TP1 setting.
  4. Verdict: CLEAN_WIN (higher mean AND per-trade Sharpe + book Sortino improve/hold AND maxDD
     doesn't worsen materially) vs RISK_UP (higher mean but worse risk-adjusted / maxDD).

Pure Python / numpy, $0 (no LLM, no live orders). Markets closed. NO live watcher/params edits.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b10_exit_variance.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

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
    Signal,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    detect_signals as detect_vwap_continuation,
)
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals as detect_reclaim_failed_break,
)
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    causal_vix_median,
    vix_slope,
    detect_opt_signals as detect_vix_regime_dayside,
    VIX_MEDIAN_BARS,
    VIX_SLOPE_BARS,
    _swing_stop,
)
from lib.ribbon import compute_ribbon  # noqa: E402

# Reuse B10's sim plumbing (same TradeRow, same simulate_book, same _key, same constants).
from autoresearch._b10_exit_audit import (  # noqa: E402
    simulate_book,
    load_vix_regime_config,
    _key,
    TradeRow,
    START, END, OOS_YEAR, ATM, ITM2,
    BASE_TP1_PCT, BASE_TP1_QTY_FRAC, BASE_RUNNER_PCT, BASE_TIME_STOP,
)

OUT_JSON = ROOT / "analysis" / "recommendations" / "B10-EXIT-VARIANCE.json"
SCORECARD_MD = ROOT / "analysis" / "recommendations" / "B10-EXIT-AUDIT-SCORECARD.md"

# ── The WINNING config from the B10 sweep (top by expectancy lift for BOTH books) ──
WIN_TP1_PCT = 0.75
WIN_TP1_QTY_FRAC = 0.50
WIN_RUNNER_PCT = 3.0
WIN_TIME_STOP = dt.time(15, 30)

# Trading-days-per-year for annualization (US equity market).
TRADING_DAYS_YEAR = 252

# What "worsens materially" means for maxDD (book-level). A higher TP1 banks less early so a
# modest DD widening is EXPECTED and acceptable; we only fail the gate if maxDD blows out.
MAXDD_MATERIAL_WORSEN_PCT = 0.25  # +25% deeper book maxDD = "material" worsening


# ════════════════════════════════════════════════════════════════════════════════
# 1. PER-TRADE DISTRIBUTION
# ════════════════════════════════════════════════════════════════════════════════
def _percentiles(a: np.ndarray) -> dict:
    return {
        "p05": round(float(np.percentile(a, 5)), 2),
        "p25": round(float(np.percentile(a, 25)), 2),
        "median": round(float(np.percentile(a, 50)), 2),
        "p75": round(float(np.percentile(a, 75)), 2),
        "p95": round(float(np.percentile(a, 95)), 2),
    }


def _skew(a: np.ndarray) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    m = a.mean()
    sd = a.std(ddof=0)
    if sd == 0:
        return 0.0
    return round(float(((a - m) ** 3).mean() / (sd ** 3)), 3)


def per_trade_dist(rows: list[TradeRow]) -> dict:
    pnl = np.array([r.pnl for r in rows], float)
    n = len(pnl)
    mean = float(pnl.mean())
    std = float(pnl.std(ddof=1)) if n > 1 else 0.0
    losers = pnl[pnl < 0]
    return {
        "n": n,
        "mean": round(mean, 2),
        "std": round(std, 2),
        "sharpe_per_trade": round(mean / std, 4) if std > 0 else 0.0,
        "skew": _skew(pnl),
        **_percentiles(pnl),
        "worst_trade": round(float(pnl.min()), 2),
        "best_trade": round(float(pnl.max()), 2),
        "pct_losing": round(100 * float((pnl < 0).mean()), 1),
        "mean_of_losers": round(float(losers.mean()), 2) if len(losers) else 0.0,
        "n_losers": int(len(losers)),
        "total": round(float(pnl.sum()), 2),
    }


# ════════════════════════════════════════════════════════════════════════════════
# 2. DOWNSIDE — trades that get WORSE under +75% vs +30% (the no-run-day exposure)
# ════════════════════════════════════════════════════════════════════════════════
def worse_trade_profile(base_rows: list[TradeRow], win_rows: list[TradeRow]) -> dict:
    """Match trades by identity (edge + entry bar). For each shared trade compare win vs base pnl.
    Report the set that gets WORSE under +75% — count, total $ given back, and the exit-reason mix
    of the worse set (does the higher TP1 hurt mainly on NON-running days where TP1 isn't reached
    and the position rides to stop/time? That shows up as STOP / TIME / RIBBON-without-TP1 on the
    worse set)."""
    base_by = {_key(r): r for r in base_rows}
    win_by = {_key(r): r for r in win_rows}
    keys = set(base_by) & set(win_by)

    worse = []
    better = []
    same = []
    for k in keys:
        b = base_by[k]
        w = win_by[k]
        d = round(w.pnl - b.pnl, 2)
        if d < -1e-6:
            worse.append((k, b, w, d))
        elif d > 1e-6:
            better.append((k, b, w, d))
        else:
            same.append((k, b, w, d))

    worse_total = round(sum(d for *_, d in worse), 2)
    better_total = round(sum(d for *_, d in better), 2)

    # Exit-reason mix on the WORSE set, under the +75% (winning) config — this is the mechanism.
    worse_win_exit_mix = Counter(w.exit_reason for _, _, w, _ in worse)
    # On the worse set: how many did NOT fill TP1 at all (TP1 unreachable at +75% -> rode to a
    # worse market/stop/time exit)? That is the "no-run-day theta/stop bite" the caveat names.
    worse_no_tp1 = sum(1 for _, _, w, _ in worse if not w.tp1_filled)
    worse_n = len(worse)

    # Among the WORSE set, mean pnl under each config (did these trades go from green->less-green,
    # or green->red? i.e. is the give-back banked profit, or new losses?).
    worse_base_mean = round(float(np.mean([b.pnl for _, b, _, _ in worse])), 2) if worse else 0.0
    worse_win_mean = round(float(np.mean([w.pnl for _, _, w, _ in worse])), 2) if worse else 0.0
    worse_win_now_red = sum(1 for _, b, w, _ in worse if b.pnl > 0 and w.pnl <= 0)

    return {
        "shared_trades": len(keys),
        "n_worse": worse_n,
        "n_better": len(better),
        "n_same": len(same),
        "worse_total_giveback": worse_total,     # negative = $ given back on the worse set
        "better_total_gain": better_total,       # positive = $ gained on the better set
        "net_changed": round(better_total + worse_total, 2),
        "worse_pct_no_tp1": round(100 * worse_no_tp1 / worse_n, 1) if worse_n else 0.0,
        "worse_exit_mix_at_75": dict(worse_win_exit_mix),
        "worse_set_base_mean": worse_base_mean,
        "worse_set_win_mean": worse_win_mean,
        "worse_green_to_red_n": worse_win_now_red,  # trades that flipped from winner to loser
    }


# ════════════════════════════════════════════════════════════════════════════════
# 3. BOOK-LEVEL — daily-equity maxDD, worst day, downside-dev, annualized Sortino/Sharpe
# ════════════════════════════════════════════════════════════════════════════════
def daily_pnl_series(rows: list[TradeRow]) -> pd.Series:
    """Collapse the book's trades to a per-calendar-day net P&L series (the equity-curve unit)."""
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame({"date": [r.date for r in rows], "pnl": [r.pnl for r in rows]})
    return df.groupby("date")["pnl"].sum().sort_index()


def max_drawdown(equity: np.ndarray) -> float:
    """Max peak-to-trough drawdown on a cumulative equity curve (dollars, negative)."""
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    return round(float(dd.min()), 2)


def book_risk(rows: list[TradeRow]) -> dict:
    """Book-level risk metrics on the DAILY P&L series (only days the book traded)."""
    daily = daily_pnl_series(rows)
    if daily.empty:
        return {"trading_days": 0}
    d = daily.to_numpy(float)
    n_days = len(d)
    mean_d = float(d.mean())
    std_d = float(d.std(ddof=1)) if n_days > 1 else 0.0

    # Downside deviation vs target 0 (only negative daily returns contribute).
    downside = np.minimum(d, 0.0)
    dd_dev = float(np.sqrt((downside ** 2).mean()))

    equity = np.cumsum(d)
    mdd = max_drawdown(equity)

    # Annualize using the FRACTION of all trading days the book is actually in the market — both
    # configs trade the same entry set (same days), so this scalar is identical across configs and
    # the Sharpe/Sortino comparison is apples-to-apples. We report the in-market-day stats too.
    ann = np.sqrt(TRADING_DAYS_YEAR)
    sharpe_ann = round((mean_d / std_d) * ann, 3) if std_d > 0 else 0.0
    sortino_ann = round((mean_d / dd_dev) * ann, 3) if dd_dev > 0 else 0.0

    return {
        "trading_days": n_days,
        "mean_daily": round(mean_d, 2),
        "std_daily": round(std_d, 2),
        "downside_dev_daily": round(dd_dev, 2),
        "worst_day": round(float(d.min()), 2),
        "best_day": round(float(d.max()), 2),
        "max_drawdown": mdd,
        "total": round(float(d.sum()), 2),
        "day_wr_pct": round(100 * float((d > 0).mean()), 1),
        "sharpe_annualized": sharpe_ann,
        "sortino_annualized": sortino_ann,
    }


# ════════════════════════════════════════════════════════════════════════════════
# VERDICT
# ════════════════════════════════════════════════════════════════════════════════
def decide_verdict(base_pt: dict, win_pt: dict, base_bk: dict, win_bk: dict) -> dict:
    """CLEAN_WIN iff higher mean AND per-trade Sharpe holds/improves AND book Sortino holds/improves
    AND book maxDD doesn't worsen materially. Else RISK_UP."""
    higher_mean = win_pt["mean"] > base_pt["mean"]
    sharpe_ok = win_pt["sharpe_per_trade"] >= base_pt["sharpe_per_trade"] - 1e-9
    sortino_ok = win_bk["sortino_annualized"] >= base_bk["sortino_annualized"] - 1e-9
    sharpe_book_ok = win_bk["sharpe_annualized"] >= base_bk["sharpe_annualized"] - 1e-9

    # maxDD: both negative; "worse" = deeper (more negative). Material = >25% deeper.
    base_mdd = abs(base_bk["max_drawdown"])
    win_mdd = abs(win_bk["max_drawdown"])
    mdd_worsen_frac = (win_mdd - base_mdd) / base_mdd if base_mdd > 0 else 0.0
    mdd_material_worse = mdd_worsen_frac > MAXDD_MATERIAL_WORSEN_PCT

    clean = bool(higher_mean and sharpe_ok and sortino_ok and (not mdd_material_worse))
    return {
        "higher_mean": bool(higher_mean),
        "per_trade_sharpe_holds": bool(sharpe_ok),
        "book_sharpe_holds": bool(sharpe_book_ok),
        "book_sortino_holds": bool(sortino_ok),
        "maxdd_worsen_frac": round(mdd_worsen_frac, 4),
        "maxdd_material_worse": bool(mdd_material_worse),
        "verdict": "CLEAN_WIN" if clean else "RISK_UP",
    }


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"[b10-var] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    print(f"[b10-var] trading_days={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    vix_g = vix.to_numpy()
    vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
    vix_cfg = load_vix_regime_config()
    print(f"[b10-var] edge#4 vix config: {vix_cfg}", flush=True)

    # Detect each edge ONCE (byte-for-byte identical to B9/B10).
    sig_e1 = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_e2 = detect_reclaim_failed_break(days)
    sig_e4_raw = detect_vix_regime_dayside(days, spy, vix_g, vix_med_g, vix_slp_g,
                                           vix_cfg["low_margin"], vix_cfg["slope_rule"])
    sig_e4 = [Signal(bar_idx=s.gidx, side=s.side,
                     stop_level=round(_swing_stop(spy, s.gidx, s.side), 2),
                     note="vix_regime_dayside") for s in sig_e4_raw]
    sigs = {"e1": sig_e1, "e2": sig_e2, "e4": sig_e4}
    print(f"[b10-var] signals: e1={len(sig_e1)} e2={len(sig_e2)} e4={len(sig_e4)}", flush=True)

    BOOKS = {
        "Safe-2_ATM": [("e1", ATM, "VWAPCONT"), ("e2", ATM, "RECLAIM"), ("e4", ATM, "VIXREGIME")],
        "Bold_ITM2":  [("e1", ITM2, "VWAPCONT"), ("e2", ITM2, "RECLAIM")],
    }

    results: dict[str, dict] = {}
    for book_name, comp in BOOKS.items():
        print(f"\n[b10-var] === {book_name} ===", flush=True)
        base_rows = simulate_book(sigs, spy, ribbon, vix, composition=comp,
                                  tp1_premium_pct=BASE_TP1_PCT, tp1_qty_fraction=BASE_TP1_QTY_FRAC,
                                  runner_target_pct=BASE_RUNNER_PCT, time_stop_et=BASE_TIME_STOP)
        win_rows = simulate_book(sigs, spy, ribbon, vix, composition=comp,
                                 tp1_premium_pct=WIN_TP1_PCT, tp1_qty_fraction=WIN_TP1_QTY_FRAC,
                                 runner_target_pct=WIN_RUNNER_PCT, time_stop_et=WIN_TIME_STOP)

        base_pt = per_trade_dist(base_rows)
        win_pt = per_trade_dist(win_rows)
        downside = worse_trade_profile(base_rows, win_rows)
        base_bk = book_risk(base_rows)
        win_bk = book_risk(win_rows)
        verdict = decide_verdict(base_pt, win_pt, base_bk, win_bk)

        results[book_name] = {
            "per_trade": {"baseline_tp30": base_pt, "winning_tp75": win_pt},
            "downside_worse_set": downside,
            "book": {"baseline_tp30": base_bk, "winning_tp75": win_bk},
            "verdict": verdict,
        }

        # Console print
        print(f"[b10-var]   PER-TRADE  base(tp30): mean=${base_pt['mean']} std=${base_pt['std']} "
              f"sharpe/tr={base_pt['sharpe_per_trade']} skew={base_pt['skew']} "
              f"worst=${base_pt['worst_trade']} %losing={base_pt['pct_losing']} "
              f"mean_loser=${base_pt['mean_of_losers']}", flush=True)
        print(f"[b10-var]   PER-TRADE  WIN(tp75):  mean=${win_pt['mean']} std=${win_pt['std']} "
              f"sharpe/tr={win_pt['sharpe_per_trade']} skew={win_pt['skew']} "
              f"worst=${win_pt['worst_trade']} %losing={win_pt['pct_losing']} "
              f"mean_loser=${win_pt['mean_of_losers']}", flush=True)
        print(f"[b10-var]   PCTILES base: P05=${base_pt['p05']} P25=${base_pt['p25']} "
              f"med=${base_pt['median']} P75=${base_pt['p75']} P95=${base_pt['p95']}", flush=True)
        print(f"[b10-var]   PCTILES WIN:  P05=${win_pt['p05']} P25=${win_pt['p25']} "
              f"med=${win_pt['median']} P75=${win_pt['p75']} P95=${win_pt['p95']}", flush=True)
        print(f"[b10-var]   DOWNSIDE  shared={downside['shared_trades']} "
              f"worse={downside['n_worse']} (giveback=${downside['worse_total_giveback']}) "
              f"better={downside['n_better']} (gain=${downside['better_total_gain']}) "
              f"net_changed=${downside['net_changed']}", flush=True)
        print(f"[b10-var]   WORSE-SET  %no-TP1={downside['worse_pct_no_tp1']} "
              f"green->red={downside['worse_green_to_red_n']} "
              f"base_mean=${downside['worse_set_base_mean']} win_mean=${downside['worse_set_win_mean']} "
              f"exit_mix={downside['worse_exit_mix_at_75']}", flush=True)
        print(f"[b10-var]   BOOK base: maxDD=${base_bk['max_drawdown']} worstday=${base_bk['worst_day']} "
              f"dn-dev=${base_bk['downside_dev_daily']} Sharpe={base_bk['sharpe_annualized']} "
              f"Sortino={base_bk['sortino_annualized']}", flush=True)
        print(f"[b10-var]   BOOK WIN:  maxDD=${win_bk['max_drawdown']} worstday=${win_bk['worst_day']} "
              f"dn-dev=${win_bk['downside_dev_daily']} Sharpe={win_bk['sharpe_annualized']} "
              f"Sortino={win_bk['sortino_annualized']}", flush=True)
        print(f"[b10-var]   VERDICT {book_name}: {verdict['verdict']} "
              f"(higher_mean={verdict['higher_mean']} sharpe/tr_holds={verdict['per_trade_sharpe_holds']} "
              f"sortino_holds={verdict['book_sortino_holds']} "
              f"maxDD_worsen={verdict['maxdd_worsen_frac']:.1%} "
              f"material={verdict['maxdd_material_worse']})", flush=True)

    # Book-level verdict roll-up: CLEAN_WIN only if BOTH books are clean.
    both_clean = all(r["verdict"]["verdict"] == "CLEAN_WIN" for r in results.values())
    overall = "CLEAN_WIN" if both_clean else "RISK_UP"

    summary = {
        "campaign": "B10 WP-4 — TP1 +30%->+75% variance / downside audit (3-edge book, real OPRA fills)",
        "purpose": ("verify the ONE open caveat: does the higher TP1 raise the mean by taking on "
                    "disproportionate tail risk on no-run days, or is it risk-adjusted clean?"),
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR}",
        "baseline_v15_tp30": {"tp1_premium_pct": BASE_TP1_PCT, "tp1_qty_fraction": BASE_TP1_QTY_FRAC,
                              "runner_target_pct": BASE_RUNNER_PCT,
                              "time_stop_et": BASE_TIME_STOP.strftime("%H:%M")},
        "winning_tp75": {"tp1_premium_pct": WIN_TP1_PCT, "tp1_qty_fraction": WIN_TP1_QTY_FRAC,
                         "runner_target_pct": WIN_RUNNER_PCT,
                         "time_stop_et": WIN_TIME_STOP.strftime("%H:%M")},
        "maxdd_material_worsen_threshold": MAXDD_MATERIAL_WORSEN_PCT,
        "books": results,
        "overall_verdict": overall,
        "DISCLOSURE": {
            "real_fills": "real OPRA fills, the only 0DTE WR authority (C1); SPY-dir != option edge (C3)",
            "bull_tape_caveat": ("OOS (2026) is a bull tape; the ~4.5-4.7 book Sharpe is bull-flattered "
                                 "and will compress in chop/bear. The risk-adjusted comparison here is "
                                 "RELATIVE (tp75 vs tp30 on the SAME tape) so the bull bias cancels — "
                                 "but the absolute Sharpe/Sortino are NOT a forward forecast."),
            "annualization": (f"daily P&L annualized with sqrt({TRADING_DAYS_YEAR}); both configs trade "
                              "the identical entry/day set so the scalar cancels in the comparison."),
            "per_trade_sharpe": "mean/std on the per-trade $ P&L (not annualized) — a shape metric.",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[b10-var] wrote {OUT_JSON}", flush=True)

    print("\n=== B10 WP-4 VARIANCE/DOWNSIDE VERDICT ===")
    print(f"OVERALL: {overall}")
    for bk, r in results.items():
        v = r["verdict"]
        bp = r["per_trade"]["baseline_tp30"]
        wp = r["per_trade"]["winning_tp75"]
        bb = r["book"]["baseline_tp30"]
        wb = r["book"]["winning_tp75"]
        print(f"  {bk}: {v['verdict']}")
        print(f"     mean ${bp['mean']}->${wp['mean']}  sharpe/tr {bp['sharpe_per_trade']}->{wp['sharpe_per_trade']}  "
              f"%losing {bp['pct_losing']}->{wp['pct_losing']}  worst ${bp['worst_trade']}->${wp['worst_trade']}")
        print(f"     book maxDD ${bb['max_drawdown']}->${wb['max_drawdown']} ({v['maxdd_worsen_frac']:.1%})  "
              f"Sortino {bb['sortino_annualized']}->{wb['sortino_annualized']}  "
              f"Sharpe {bb['sharpe_annualized']}->{wb['sharpe_annualized']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
