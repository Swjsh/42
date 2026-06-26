"""REGIME-SWITCH THRESHOLD + NEUTRAL SWEEP — does ANY causal threshold make regime
ALLOCATION beat directional-ALWAYS?

The base _regime_switch_book.py answers the question at ONE tercile cut-point and the core
thesis FAILED (on its CHOP days directional out-earned the condor). The campaign brief
explicitly asks to SWEEP the regime-threshold + NEUTRAL-handling before calling the verdict,
so this harness reuses _regime_switch_book.py BYTE-FOR-BYTE (imports its sleeves, classifier,
metrics — no edit to that file or any money-path module) and grid-searches the trend/overnight
quantile cut-points + NEUTRAL policy.

For each (trend_q, on_q) pair we learn IN-SAMPLE quantiles for the trend & overnight features
(no OOS leakage — quantiles from pre-2026 days only), classify every universe day, and run the
SAME switched-book vs directional-always comparison. We report the BEST cell by the bar, plus
the load-bearing CHOP-day isolation for every cell.

Run (offline, $0):
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_regime_switch_sweep.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import autoresearch._regime_switch_book as B  # noqa: E402

OUT_DIR = B.OUT_DIR


def _quant(vals, q):
    a = np.array([v for v in vals if v is not None and not math.isnan(v)], float)
    if a.size < 6:
        return None
    return float(np.quantile(a, q))


def main() -> int:
    print("[sweep] loading frames (reusing _regime_switch_book loaders) ...", flush=True)
    master_spy = pd.read_csv(B.DATA / "spy_5m_2025-01-01_2026-06-16.csv")
    master_vix = pd.read_csv(B.DATA / "vix_5m_2025-01-01_2026-06-16.csv")
    recent_spy = pd.read_csv(B.DATA / "spy_5m_2026-05-19_2026-06-18.csv")
    recent_vix = pd.read_csv(B.DATA / "vix_5m_2026-05-19_2026-06-18.csv")
    spy = B._normalize_spy(pd.concat([master_spy, recent_spy], ignore_index=True))
    vix = B._align_vix(spy, pd.concat([master_vix, recent_vix], ignore_index=True))

    spy_pivot = B.P._load_spy_master()
    cache_days = B.P._option_cache_dates()

    days_ctx = B.build_day_contexts(spy)
    trading_days = sorted({dc.date for dc in days_ctx})
    universe = [d for d in trading_days if d in cache_days]
    is_days = [d for d in universe if d < B.OOS_START]
    oos_days = [d for d in universe if d >= B.OOS_START]
    recent_days = universe[-B.RECENCY_N:]
    print(f"[sweep] universe={len(universe)} ({universe[0]}..{universe[-1]}) "
          f"IS={len(is_days)} OOS={len(oos_days)}", flush=True)

    feats = B.compute_regime_features(spy, vix, trading_days)

    # Run BOTH sleeves ONCE (expensive) — reuse across all cells.
    print("[sweep] running directional sleeve (real OPRA) ...", flush=True)
    dir_pnl = B.directional_pnl_by_day(spy, vix)
    print("[sweep] running condor sleeve (real OPRA) ...", flush=True)
    ic_pnl = B.condor_pnl_by_day(spy_pivot, cache_days, universe)

    baseline = {
        "full": B.book_metrics(B._daily_series(dir_pnl, universe)),
        "oos": B.book_metrics(B._daily_series(dir_pnl, oos_days)),
        "recency": B.book_metrics(B._daily_series(dir_pnl, recent_days)),
    }
    print(f"[sweep] DIR-ALWAYS baseline: full tot=${baseline['full']['total']} "
          f"sharpe={baseline['full']['sharpe']} sortino={baseline['full']['sortino']} "
          f"maxDD=${baseline['full']['max_dd']} | OOS tot=${baseline['oos']['total']} "
          f"| rec tot=${baseline['recency']['total']} maxDD=${baseline['recency']['max_dd']}",
          flush=True)

    # IS-feature pools for quantile learning (causal — IS only).
    is_trend = [feats[d].trend_strength_20d for d in is_days if d in feats]
    is_on = [feats[d].overnight_range_pct_atr for d in is_days if d in feats]
    is_vix = [feats[d].vix_spot for d in is_days if d in feats]

    # Sweep grid: trend hi/lo quantile pairs and overnight hi/lo quantile pairs.
    # (lo_q, hi_q) symmetric splits around the median, widening the "decisive" tails.
    splits = [(0.5, 0.5), (0.4, 0.6), (0.33, 0.67), (0.25, 0.75), (0.2, 0.8), (0.15, 0.85)]
    vix_q = 1 / 3

    cells = []
    best = None
    best_thesis = None
    for (t_lo_q, t_hi_q) in splits:
        for (o_lo_q, o_hi_q) in splits:
            t_lo, t_hi = _quant(is_trend, t_lo_q), _quant(is_trend, t_hi_q)
            o_lo, o_hi = _quant(is_on, o_lo_q), _quant(is_on, o_hi_q)
            v_lo = _quant(is_vix, vix_q)
            if None in (t_lo, t_hi, o_lo, o_hi, v_lo):
                continue
            th = B.RegimeThresholds(trend_hi=t_hi, trend_lo=t_lo, on_hi=o_hi, on_lo=o_lo,
                                    vix_lo=v_lo)
            regimes = {d: B.classify_day(feats[d], th) for d in universe}
            dist = defaultdict(int)
            for d in universe:
                dist[regimes[d]] += 1
            n = len(universe)
            degenerate = (dist["TREND"] < max(5, int(0.05 * n)) or
                          dist["CHOP"] < max(5, int(0.05 * n)) or
                          dist["NEUTRAL"] > int(0.90 * n))
            chop_iso = B.chop_day_isolation(regimes, dir_pnl, ic_pnl, universe)

            for policy in ("directional", "condor", "abstain"):
                book = B.build_switched_book(regimes, dir_pnl, ic_pnl, universe, policy)
                m_full = B.book_metrics(B._daily_series(book, universe))
                m_oos = B.book_metrics(B._daily_series(book, oos_days))
                m_rec = B.book_metrics(B._daily_series(book, recent_days))
                nores = B.switch_days_noregression(regimes, dir_pnl, book, universe)
                bar1 = (m_full["sharpe"] >= baseline["full"]["sharpe"] and
                        m_full["sortino"] >= baseline["full"]["sortino"] and
                        m_full["max_dd"] >= baseline["full"]["max_dd"])
                bar2 = (m_rec["max_dd"] >= baseline["recency"]["max_dd"] and
                        m_rec["total"] >= baseline["recency"]["total"])
                bar3 = nores["no_regression_pass"]
                bar4 = m_oos["total"] > 0
                all_pass = bool(bar1 and bar2 and bar3 and bar4 and not degenerate)
                cell = {
                    "trend_q": (t_lo_q, t_hi_q), "on_q": (o_lo_q, o_hi_q),
                    "policy": policy, "dist": dict(dist), "degenerate": bool(degenerate),
                    "chop_iso": chop_iso,
                    "full": m_full, "oos": m_oos, "recency": m_rec, "no_regression": nores,
                    "bar": {"1_rr_up": bool(bar1), "2_rec_dd_down": bool(bar2),
                            "3_no_regress": bool(bar3), "4_oos_pos": bool(bar4),
                            "ALL_PASS": all_pass},
                }
                cells.append(cell)
                # Track best by (ALL_PASS, then full sortino).
                key = (all_pass, m_full["sortino"], m_full["total"])
                if best is None or key > (best["bar"]["ALL_PASS"], best["full"]["sortino"],
                                          best["full"]["total"]):
                    best = cell
            # Track best thesis cell (condor beats directional on CHOP days, non-degenerate).
            if not degenerate:
                cd = chop_iso["condor_minus_directional_on_chop"]
                if best_thesis is None or cd > best_thesis["chop_iso"][
                        "condor_minus_directional_on_chop"]:
                    best_thesis = {"trend_q": (t_lo_q, t_hi_q), "on_q": (o_lo_q, o_hi_q),
                                   "chop_iso": chop_iso, "dist": dict(dist)}

    any_pass = [c for c in cells if c["bar"]["ALL_PASS"]]
    any_thesis = [c for c in cells if c["chop_iso"]["thesis_supported"]
                  and not c["degenerate"]]

    print("\n=== SWEEP SUMMARY ===", flush=True)
    print(f"cells evaluated: {len(cells)}", flush=True)
    print(f"cells passing ALL bars: {len(any_pass)}", flush=True)
    print(f"cells where condor BEATS directional on CHOP days (thesis): {len(any_thesis)}",
          flush=True)
    print(f"\nBEST cell by (ALL_PASS, sortino, total):", flush=True)
    print(f"  trend_q={best['trend_q']} on_q={best['on_q']} policy={best['policy']} "
          f"dist={best['dist']} degenerate={best['degenerate']}", flush=True)
    print(f"  full: tot=${best['full']['total']} sharpe={best['full']['sharpe']} "
          f"sortino={best['full']['sortino']} maxDD=${best['full']['max_dd']}", flush=True)
    print(f"  oos:  tot=${best['oos']['total']} | recency: tot=${best['recency']['total']} "
          f"maxDD=${best['recency']['max_dd']}", flush=True)
    print(f"  bar: {best['bar']}", flush=True)
    print(f"  chop_iso: dir=${best['chop_iso']['directional_pnl_on_chop']} "
          f"condor=${best['chop_iso']['condor_pnl_on_chop']} "
          f"(condor-dir=${best['chop_iso']['condor_minus_directional_on_chop']})", flush=True)
    if best_thesis:
        print(f"\nBEST THESIS cell (max condor-minus-directional on CHOP days):", flush=True)
        print(f"  trend_q={best_thesis['trend_q']} on_q={best_thesis['on_q']} "
              f"dist={best_thesis['dist']}", flush=True)
        print(f"  chop_iso: dir=${best_thesis['chop_iso']['directional_pnl_on_chop']} "
              f"condor=${best_thesis['chop_iso']['condor_pnl_on_chop']} "
              f"(condor-dir=${best_thesis['chop_iso']['condor_minus_directional_on_chop']}) "
              f"-> supported={best_thesis['chop_iso']['thesis_supported']}", flush=True)

    out = {
        "harness": "REGIME-SWITCH THRESHOLD + NEUTRAL SWEEP",
        "run_date": dt.date.today().isoformat(),
        "universe_days": len(universe), "universe_span": f"{universe[0]}..{universe[-1]}",
        "oos_start": str(B.OOS_START), "recency_n": B.RECENCY_N,
        "directional_always_baseline": baseline,
        "n_cells": len(cells), "n_cells_all_pass": len(any_pass),
        "n_cells_thesis_supported": len(any_thesis),
        "best_cell": best, "best_thesis_cell": best_thesis,
        "all_cells": cells,
        "DISCLOSURE": {
            "what_this_answers": "does ANY causal IS-learned threshold make regime allocation "
                                 "beat directional-always? (sweep of the base harness)",
            "condor_data_constrained": "IC sleeve is null-failing-standalone + +/-$5 OPRA band; "
                                       "a SHIP still needs wide-band condor validation (4b).",
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "sweep_results.json").write_text(json.dumps(out, indent=2, default=str),
                                                encoding="utf-8")
    print(f"\n[sweep] wrote {OUT_DIR / 'sweep_results.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
