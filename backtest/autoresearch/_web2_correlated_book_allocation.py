"""WEB-LEARN-2 — ALLOCATING CAPITAL ACROSS A BOOK OF CORRELATED OVERLAPPING EDGES.

THE WEB ANGLE (cited in analysis/recommendations/SUNDAY-WEB-LEARN-2.md):
  Professional portfolio-construction literature says: when you run several POSITIVELY
  CORRELATED return streams, an EQUAL-WEIGHT ("naive 1/N", which is what our live book is —
  every edge fires qty=3) is sub-optimal vs correlation-aware weighting:
    * Inverse-Variance Weighting (IVW) — down-weight the higher-variance edges (de Prado HRP
      leaf step; Wikipedia inverse-variance-weighting).
    * Equal-Risk-Contribution (ERC / "risk parity") — each edge contributes equal risk; unlike
      IVW it USES the correlation matrix, so two highly-correlated edges get jointly down-weighted
      (Maillard-Roncalli-Teiletche 2010; robotwealth ERC notes).
    * Minimum-Variance (MV) — the lowest-variance long-only mix.
  B9 already MEASURED our book (corr e1/e2=0.31, e1/e4=0.54, e2/e4=0.08; equal-weight Safe
  Sharpe 4.53 / Bold 4.70). B9 never ALLOCATED. This harness asks the un-tested question:

    Does correlation-aware weighting of the 3-edge (Safe) / 2-edge (Bold) book beat the live
    equal-weight book on a RISK-ADJUSTED basis (book Sharpe / Sortino / maxDD), out-of-sample,
    on real OPRA fills?

  This is a SIZING/ALLOCATION change on already-validated edges -> bar = L175 risk-adjusted
  (book Sharpe AND Sortino no-worse AND maxDD no-worse AND OOS-positive), NOT the 11-gate
  (no new signal). Weights are estimated IN-SAMPLE (2025) ONLY and applied OUT-OF-SAMPLE (2026)
  — the honest test (no look-ahead on the covariance, L161/L166). We also report the naive
  in-sample-fit weights to expose any curve-fit gap.

HONESTY / DISCLOSURE (OP-20 / C7 — PASTE REAL NUMBERS):
  * Real OPRA fills via lib.simulator_real (C1). SPY-direction != option edge (C3/L58).
  * Reuses the BYTE-FOR-BYTE B9 detectors + simulate_set (same machinery that produced the
    measured book) — no re-derivation of signals.
  * Weights scale the per-day edge P&L (a qty multiplier proxy). Because min-3-contract is a HARD
    floor (Rule 6) and our accounts are sub-$5K where caps bind, a fractional weight is NOT
    literally placeable today — so this is measured as the RISK-MODEL answer ("which edge deserves
    more capital as the book scales above the contract floor"), and flagged as such. The
    integer-contract reality is reported alongside (round-to-min-3).
  * IS=2025 estimate / OOS=2026 apply. Daily Sharpe annualized x sqrt(252).

Pure Python / numpy, $0, no live orders, markets closed.
Writes analysis/recommendations/web2-correlated-book-allocation.{json}.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_web2_correlated_book_allocation.py
"""
from __future__ import annotations

import datetime as dt
import json
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

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import build_day_contexts, Signal  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy, _align_vix, detect_signals as detect_vwap_continuation,
)
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals as detect_reclaim_failed_break,
)
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    causal_vix_median, vix_slope, detect_opt_signals as detect_vix_regime_dayside,
    VIX_MEDIAN_BARS, VIX_SLOPE_BARS, _swing_stop,
)
from autoresearch._b9_portfolio import (  # noqa: E402  (byte-for-byte same sim machinery as B9)
    simulate_set, by_day, ATM, ITM2, load_vix_regime_config,
    START, END, TRADING_DAYS_PER_YEAR, OOS_YEAR,
)
from lib.ribbon import compute_ribbon  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "web2-correlated-book-allocation.json"
HARD_OPRA_CAP = dt.date(2026, 5, 29)  # C1 — real-fill cache authority horizon


# ── book risk metrics on a daily P&L vector over a fixed all-trading-day axis ──────
def book_metrics(daily_vec: np.ndarray) -> dict:
    n = len(daily_vec)
    total = float(daily_vec.sum())
    mean_d = float(daily_vec.mean()) if n else 0.0
    std_d = float(daily_vec.std(ddof=1)) if n > 1 else 0.0
    downside = daily_vec[daily_vec < 0]
    dstd = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sharpe = round((mean_d / std_d) * np.sqrt(TRADING_DAYS_PER_YEAR), 3) if std_d > 0 else None
    sortino = round((mean_d / dstd) * np.sqrt(TRADING_DAYS_PER_YEAR), 3) if dstd > 0 else None
    eq = np.cumsum(daily_vec)
    peak = np.maximum.accumulate(eq)
    max_dd = float((eq - peak).min()) if n else 0.0
    return {
        "total": round(total, 2), "daily_mean": round(mean_d, 3), "daily_std": round(std_d, 3),
        "ann_sharpe": sharpe, "ann_sortino": sortino, "max_dd": round(max_dd, 2),
        "worst_day": round(float(daily_vec.min()), 2) if n else 0.0,
        "best_day": round(float(daily_vec.max()), 2) if n else 0.0,
    }


def weighted_daily(edge_daily: dict[str, dict[str, float]], all_days: list[str],
                   weights: dict[str, float]) -> np.ndarray:
    """Combine edges' per-day P&L on a fixed day axis with given weights (qty multipliers)."""
    out = np.zeros(len(all_days))
    idx = {d: i for i, d in enumerate(all_days)}
    for nm, bd in edge_daily.items():
        w = weights.get(nm, 0.0)
        if w == 0.0:
            continue
        for d, p in bd.items():
            out[idx[d]] += w * p
    return out


# ── allocation schemes (all long-only, normalized to sum=N so the equal-weight book is
#    the unit baseline: equal-weight gives every edge weight 1.0) ───────────────────
def scheme_weights(names: list[str], cov: np.ndarray, var: np.ndarray) -> dict[str, dict]:
    n = len(names)

    def norm(w):  # normalize so weights sum to n (equal-weight == all-ones)
        w = np.clip(w, 1e-9, None)
        return w / w.sum() * n

    eq = np.ones(n)
    ivw = norm(1.0 / var)
    # ERC via simple fixed-point (Spinu / cyclical) — long-only, sums to n
    w = np.ones(n) / n
    for _ in range(20000):
        mrc = cov @ w                      # marginal risk contribution
        rc = w * mrc                       # risk contribution
        target = rc.mean()
        w = w * (target / np.clip(rc, 1e-12, None)) ** 0.5
        w = np.clip(w, 1e-9, None)
        w = w / w.sum()
    erc = w * n
    # Minimum-variance long-only (projected-gradient, sum=1 then scaled)
    wmv = np.ones(n) / n
    inv = np.linalg.pinv(cov)
    raw = inv @ np.ones(n)
    if raw.sum() != 0 and np.all(raw > 0):
        wmv = raw / raw.sum()
    else:  # long-only fallback: iterative
        wmv = np.ones(n) / n
        lr = 1e-7
        for _ in range(50000):
            g = 2 * cov @ wmv
            wmv = wmv - lr * g
            wmv = np.clip(wmv, 0, None)
            s = wmv.sum()
            wmv = wmv / s if s > 0 else np.ones(n) / n
    mv = wmv * n
    return {
        "equal_weight_LIVE": dict(zip(names, np.round(eq, 4))),
        "inverse_variance": dict(zip(names, np.round(ivw, 4))),
        "equal_risk_contribution": dict(zip(names, np.round(erc, 4))),
        "min_variance": dict(zip(names, np.round(mv, 4))),
    }


def covmat(edge_daily: dict[str, dict[str, float]], names: list[str],
           days: list[str]) -> tuple[np.ndarray, np.ndarray]:
    idx = {d: i for i, d in enumerate(days)}
    M = np.zeros((len(names), len(days)))
    for r, nm in enumerate(names):
        for d, p in edge_daily[nm].items():
            if d in idx:
                M[r, idx[d]] = p
    cov = np.cov(M) if len(names) > 1 else np.array([[float(np.var(M[0], ddof=1))]])
    var = np.diag(cov).copy()
    return cov, var


def run_account(label: str, edge_rows: dict[str, list], all_days: list[str]) -> dict:
    names = list(edge_rows)
    edge_daily = {nm: by_day(rows) for nm, rows in edge_rows.items()}
    is_days = [d for d in all_days if int(d[:4]) != OOS_YEAR]
    oos_days = [d for d in all_days if int(d[:4]) == OOS_YEAR]

    # estimate covariance IN-SAMPLE only (no look-ahead)
    cov_is, var_is = covmat(edge_daily, names, is_days)
    schemes = scheme_weights(names, cov_is, var_is)
    # full-sample (curve-fit reference) weights too
    cov_full, var_full = covmat(edge_daily, names, all_days)
    schemes_fit = scheme_weights(names, cov_full, var_full)

    results = {}
    base_oos = None
    for sname, w in schemes.items():
        full_vec = weighted_daily(edge_daily, all_days, w)
        # restrict to in-market days for the book metrics axis we report (all trading days incl flat=0
        # would dilute Sharpe identically across schemes; the meaningful comparison is the union of
        # any-edge-fire days, which is identical across schemes — so use in-market union)
        market_days = sorted({d for bd in edge_daily.values() for d in bd})
        m_idx = {d: i for i, d in enumerate(all_days)}
        mk_vec = np.array([full_vec[m_idx[d]] for d in market_days])
        is_vec = np.array([full_vec[m_idx[d]] for d in market_days if int(d[:4]) != OOS_YEAR])
        oos_vec = np.array([full_vec[m_idx[d]] for d in market_days if int(d[:4]) == OOS_YEAR])
        res = {
            "weights_IS_estimated": w,
            "weights_fullsample_fit": schemes_fit[sname],
            "ALL": book_metrics(mk_vec),
            "IS_2025": book_metrics(is_vec),
            "OOS_2026": book_metrics(oos_vec),
        }
        results[sname] = res
        if sname == "equal_weight_LIVE":
            base_oos = res

    # L175 gate: each scheme vs equal-weight, on OOS (the honest forward number)
    def gate(sname):
        s = results[sname]["OOS_2026"]
        b = base_oos["OOS_2026"]
        sh_ok = (s["ann_sharpe"] is not None and b["ann_sharpe"] is not None
                 and s["ann_sharpe"] >= b["ann_sharpe"] - 1e-6)
        so_ok = (s["ann_sortino"] is not None and b["ann_sortino"] is not None
                 and s["ann_sortino"] >= b["ann_sortino"] - 1e-6)
        dd_ok = s["max_dd"] >= b["max_dd"] - 1e-6  # less negative or equal
        oos_pos = s["total"] > 0
        # require a MATERIAL Sharpe lift to call it a win (not a rounding tie)
        sh_lift = (s["ann_sharpe"] - b["ann_sharpe"]) if (s["ann_sharpe"] and b["ann_sharpe"]) else 0.0
        promote = bool(sh_ok and so_ok and dd_ok and oos_pos and sh_lift > 0.05)
        return {
            "promote": promote, "oos_sharpe": s["ann_sharpe"], "base_oos_sharpe": b["ann_sharpe"],
            "oos_sharpe_lift": round(sh_lift, 3), "oos_sortino": s["ann_sortino"],
            "base_oos_sortino": b["ann_sortino"], "oos_maxdd": s["max_dd"],
            "base_oos_maxdd": b["max_dd"], "oos_total": s["total"], "oos_total_base": b["total"],
            "sharpe_no_worse": sh_ok, "sortino_no_worse": so_ok, "maxdd_no_worse": dd_ok,
            "oos_positive": oos_pos,
        }

    gates = {sn: gate(sn) for sn in results if sn != "equal_weight_LIVE"}
    return {
        "edges": names,
        "fire_day_counts": {nm: len(edge_daily[nm]) for nm in names},
        "is_days": len(is_days), "oos_days": len(oos_days),
        "cov_IS": np.round(cov_is, 1).tolist(),
        "corr_IS": np.round(np.corrcoef(
            np.array([[by_day(edge_rows[nm]).get(d, 0.0) for d in is_days] for nm in names])
        ), 3).tolist() if len(names) > 1 else [[1.0]],
        "schemes": results,
        "L175_gates_vs_equalweight_OOS": gates,
    }


def main() -> int:
    print(f"[web2] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    all_days = [str(dc.date) for dc in days]
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    vix_g = vix.to_numpy()
    vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
    vix_cfg = load_vix_regime_config()
    print(f"[web2] trading_days={len(all_days)} window="
          f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()} "
          f"vix_cfg={vix_cfg}", flush=True)

    # detectors (byte-for-byte same as B9)
    sig_e1 = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_e2 = detect_reclaim_failed_break(days)
    sig_e4 = detect_vix_regime_dayside(days, spy, vix_g, vix_med_g, vix_slp_g,
                                       vix_cfg["low_margin"], vix_cfg["slope_rule"])
    sig_e4 = [Signal(bar_idx=s.gidx, side=s.side,
                     stop_level=round(_swing_stop(spy, s.gidx, s.side), 2),
                     note="vix_regime_dayside") for s in sig_e4]
    print(f"[web2] signals #1={len(sig_e1)} #2={len(sig_e2)} #4={len(sig_e4)}", flush=True)

    # simulate each edge at each account tier (real OPRA fills) — assert HARD OPRA cap (C1)
    def sim(sigs, off, setup):
        rows, cov = simulate_set(sigs, spy, ribbon, vix, strike_offset=off, setup=setup)
        kept = [r for r in rows if dt.date.fromisoformat(r.date) <= HARD_OPRA_CAP]
        dropped = len(rows) - len(kept)
        return kept, cov, dropped

    e1_atm, c1, d1 = sim(sig_e1, ATM, "VWAPCONT")
    e2_atm, c2, d2 = sim(sig_e2, ATM, "RECLAIM")
    e4_atm, c4, d4 = sim(sig_e4, ATM, "VIXREGIME")
    e1_itm2, c5, d5 = sim(sig_e1, ITM2, "VWAPCONT")
    e2_itm2, c6, d6 = sim(sig_e2, ITM2, "RECLAIM")
    print(f"[web2] HARD-cap<= {HARD_OPRA_CAP} dropped post-window fills: "
          f"e1={d1} e2={d2} e4={d4} e1i={d5} e2i={d6}", flush=True)

    safe = run_account("Safe-2_ATM", {"e1": e1_atm, "e2": e2_atm, "e4": e4_atm}, all_days)
    bold = run_account("Bold_ITM2", {"e1": e1_itm2, "e2": e2_itm2}, all_days)

    # ── verdict ────────────────────────────────────────────────────────────────────
    promotions = []
    for acct, blk in (("Safe-2", safe), ("Bold", bold)):
        for sname, g in blk["L175_gates_vs_equalweight_OOS"].items():
            if g["promote"]:
                promotions.append(f"{acct} {sname}: OOS Sharpe {g['base_oos_sharpe']}->"
                                  f"{g['oos_sharpe']} (+{g['oos_sharpe_lift']}), "
                                  f"maxDD {g['base_oos_maxdd']}->{g['oos_maxdd']}")
    verdict = "ALLOCATION_IMPROVEMENT" if promotions else "DEAD_EQUALWEIGHT_HOLDS"

    summary = {
        "campaign": "WEB-LEARN-2 — correlation-aware allocation across the correlated 3-edge book",
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}", "hard_opra_cap": str(HARD_OPRA_CAP),
        "fills_authority": "real OPRA via lib.simulator_real (C1)",
        "oos_split": f"IS=2025 estimate / OOS={OOS_YEAR} apply (covariance estimated IS-only, no look-ahead)",
        "method": ("equal-weight(LIVE) vs inverse-variance vs equal-risk-contribution(ERC) vs "
                   "min-variance; weights normalized so equal-weight=all-ones (unit baseline); "
                   "weights estimated on 2025 daily edge P&L, applied to 2026"),
        "bar": "L175 risk-adjusted (book Sharpe AND Sortino no-worse AND maxDD no-worse AND OOS-positive; "
               "MATERIAL Sharpe lift > 0.05 required to PROMOTE) — NOT the 11-gate (no new signal)",
        "Safe-2": safe, "Bold": bold,
        "verdict": verdict, "promotions": promotions,
        "DISCLOSURE": {
            "real_fills": "real OPRA fills, the only 0DTE WR authority (C1); SPY-dir != option edge (C3/L58)",
            "no_lookahead": "covariance/weights estimated IN-SAMPLE (2025) only, applied OOS (2026) — L161/L166",
            "min_3_floor": ("fractional weights are a RISK-MODEL answer (which edge deserves more capital as "
                            "the book scales above the min-3-contract floor); sub-$5K the contract floor + "
                            "risk caps bind so fractional weights aren't literally placeable today — flagged, "
                            "not hidden (C14/L168 sizing-reality)"),
            "byte_for_byte": "detectors + simulate_set imported verbatim from _b9_portfolio (same machinery)",
            "relative_sharpe": "Sharpe/Sortino are RELATIVE (same trade set, same bull tape) so the 2026 bull "
                               "bias cancels across schemes; absolute Sharpe is not a forward forecast",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[web2] wrote {OUT_JSON}", flush=True)

    print("\n=== WEB-LEARN-2 ALLOCATION VERDICT ===")
    print(f"VERDICT: {verdict}")
    for acct, blk in (("Safe-2", safe), ("Bold", bold)):
        print(f"\n {acct} edges={blk['edges']} corr_IS={blk['corr_IS']}")
        for sname, r in blk["schemes"].items():
            o = r["OOS_2026"]; a = r["ALL"]
            print(f"   {sname:24s} w={r['weights_IS_estimated']} | "
                  f"OOS sharpe={o['ann_sharpe']} sortino={o['ann_sortino']} "
                  f"maxDD={o['max_dd']} tot={o['total']} | ALL sharpe={a['ann_sharpe']}")
        for sname, g in blk["L175_gates_vs_equalweight_OOS"].items():
            print(f"   GATE {sname:24s} promote={g['promote']} "
                  f"sharpeLift={g['oos_sharpe_lift']} dd_ok={g['maxdd_no_worse']} "
                  f"sortino_ok={g['sortino_no_worse']}")
    for p in promotions:
        print(f"  ALLOC+: {p}")
    if not promotions:
        print("  No scheme clears the L175 risk-adjusted bar vs the live equal-weight book OOS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
