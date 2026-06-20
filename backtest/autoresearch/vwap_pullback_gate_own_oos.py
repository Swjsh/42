"""vwap_pullback_gate_own_oos — does the regime GATE itself generalize (anti-overfit)?

A regime gate that "kills the bimodality" is worthless if the THRESHOLD was curve-fit
to the known bad window. This harness proves (or disproves) that the leading gate
candidates generalize, with the strictest test available on this data:

  THRESHOLD-OWN-OOS: derive the gate threshold on the IS half ONLY (pick the IS-best
  cut from a grid), then apply that SAME threshold UNSEEN to the OOS half. If the gate
  is real, the IS-picked threshold is still +EV (and sub-window stable) OOS. If it was
  fit to the bad months, OOS collapses.

It also dumps the full per-side + per-month detail for the two surviving candidates
(`vix < X` and `vix_falling`) on BOTH exit configs (chart-stop-only = live; -0.08 =
scorecard), so the verdict is auditable and the C29/L149 exit-config mismatch is
explicit.

Reuses backtest/autoresearch/vwap_pullback_regime_gate.py (same detector, fills,
features, metrics). Propose-only (Rule 9), pure-Python, $0.

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/vwap_pullback_gate_own_oos.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from autoresearch.infinite_ammo_discovery import (   # noqa: E402
    load_spy, align_vix, build_day_contexts,
)
from lib.ribbon import compute_ribbon               # noqa: E402
from autoresearch.vwap_pullback_regime_gate import (  # noqa: E402
    build_gated_trades, subset_metrics, rolling_month_wf,
    SPY_CSV, VIX_CSV, OOS_SPLIT_FRAC, EXIT_CONFIGS, LIVE_EXIT_KEY,
)

OUT = PROJECT / "analysis" / "recommendations" / "vwap-trend-pullback-gate-own-oos.json"


def _exp(trades):
    return float(np.mean([t.pnl for t in trades])) if trades else 0.0


def _all_sub_positive(trades, k=4):
    """k contiguous chronological sub-windows all mean-positive?"""
    if len(trades) < k:
        return False, []
    tr = sorted(trades, key=lambda t: (t.date, t.bar_idx))
    pnl = [t.pnl for t in tr]
    n = len(pnl)
    bounds = [round(i * n / k) for i in range(k + 1)]
    subs, hurt = [], 0
    for i in range(k):
        seg = pnl[bounds[i]:bounds[i + 1]]
        m = float(np.mean(seg)) if seg else 0.0
        if m < 0:
            hurt += 1
        subs.append(round(m, 2))
    return hurt == 0, subs


def threshold_own_oos_vix(trades, oos_cut_date, grid=(15, 16, 17, 18, 19, 20, 22)) -> dict:
    """Derive the best `VIX < X` threshold on IS ONLY, then apply it UNSEEN to OOS.

    IS-best = the threshold with the highest IS mean P&L among those that keep >= 20 IS
    trades (so we don't pick a degenerate tiny-n cut). Then that one threshold is scored
    on the OOS half it never saw. Real gate => OOS still +EV & sub-window stable.
    """
    is_tr = [t for t in trades if t.date < oos_cut_date]
    oos_tr = [t for t in trades if t.date >= oos_cut_date]
    # 1. pick IS-best threshold (no OOS peeking)
    best_thr, best_is_exp, best_is_n = None, -1e9, 0
    is_grid = []
    for x in grid:
        kept_is = [t for t in is_tr if t.vix < x]
        e = _exp(kept_is)
        is_grid.append({"thr": x, "is_n": len(kept_is), "is_exp": round(e, 2)})
        if len(kept_is) >= 20 and e > best_is_exp:
            best_thr, best_is_exp, best_is_n = x, e, len(kept_is)
    if best_thr is None:
        return {"verdict": "NO_VALID_IS_THRESHOLD", "is_grid": is_grid}
    # 2. apply UNSEEN to OOS
    kept_oos = [t for t in oos_tr if t.vix < best_thr]
    oos_exp = _exp(kept_oos)
    # 3. full-series metrics at the IS-picked threshold
    kept_all = [t for t in trades if t.vix < best_thr]
    m = subset_metrics(kept_all, oos_cut_date)
    allsub, subs = _all_sub_positive(kept_all)
    return {
        "method": "derive `VIX < X` on IS-only (IS-best, >=20 IS trades), apply UNSEEN to OOS",
        "is_grid": is_grid,
        "is_picked_threshold": best_thr,
        "is_n": best_is_n, "is_exp_dollar": round(best_is_exp, 2),
        "oos_n_at_is_threshold": len(kept_oos),
        "oos_exp_dollar_at_is_threshold": round(oos_exp, 2),
        "oos_generalizes": bool(oos_exp > 0 and len(kept_oos) >= 8),
        "full_series_at_is_threshold": {
            "n": m["n"], "exp_dollar": m["exp_dollar"], "wr_pct": m["wr_pct"],
            "oos_sign_stable": m["oos_sign_stable"], "n_sub_hurt": m["n_sub_hurt"],
            "all_sub_windows_positive": allsub, "sub_window_means": subs,
            "both_dirs_positive": m["both_dirs_positive"], "dsr_verdict": m["dsr_verdict"],
            "robust_to_outliers": m["robust_to_outliers"],
        },
    }


def detail_for_gate(trades, oos_cut_date, name, pred) -> dict:
    kept = [t for t in trades if pred(t)]
    m = subset_metrics(kept, oos_cut_date)
    wf = rolling_month_wf(kept)
    allsub, subs = _all_sub_positive(kept)
    return {
        "gate": name, "n_kept": m.get("n"), "retention": round(len(kept) / len(trades), 3),
        "exp_dollar": m.get("exp_dollar"), "wr_pct": m.get("wr_pct"),
        "is_exp_dollar": m.get("is_exp_dollar"), "oos_exp_dollar": m.get("oos_exp_dollar"),
        "oos_sign_stable": m.get("oos_sign_stable"),
        "all_sub_windows_positive": allsub, "sub_window_means": subs, "n_sub_hurt": m.get("n_sub_hurt"),
        "by_side": m.get("by_side"), "both_dirs_positive": m.get("both_dirs_positive"),
        "dsr_verdict": m.get("dsr_verdict"), "robust_to_outliers": m.get("robust_to_outliers"),
        "drop_top5_mean_dollar": m.get("drop_top5_mean_dollar"),
        "rolling_month_wf_median": wf.get("median_wf_norm"),
        "rolling_month_negative_oos_months": wf.get("negative_oos_months"),
        "rolling_month_oos_positive_frac": wf.get("oos_positive_frac"),
        "oos_months": m.get("oos_months"),
    }


def main() -> int:
    spy = load_spy(str(SPY_CSV))
    vix = align_vix(spy, str(VIX_CSV))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    oos_cut_date = str(all_dates[int(len(all_dates) * OOS_SPLIT_FRAC)])

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "script": "backtest/autoresearch/vwap_pullback_gate_own_oos.py",
        "purpose": "Anti-overfit: does the leading regime gate's THRESHOLD generalize "
                   "(derived IS-only, applied unseen OOS)? + full per-side/per-month "
                   "detail for the surviving candidates on both exit configs.",
        "oos_cut_date": oos_cut_date,
        "by_exit_config": {},
    }
    for cfg_name, stop in EXIT_CONFIGS.items():
        trades = build_gated_trades(spy, ribbon, vix, days, premium_stop_pct=stop)
        own_oos = threshold_own_oos_vix(trades, oos_cut_date)
        details = {
            "vix_falling": detail_for_gate(
                trades, oos_cut_date, "vix_falling", lambda t: t.vix_falling),
            "vix_lt_18": detail_for_gate(
                trades, oos_cut_date, "vix_lt_18", lambda t: t.vix < 18),
            "vix_lt_17": detail_for_gate(
                trades, oos_cut_date, "vix_lt_17", lambda t: t.vix < 17),
        }
        out["by_exit_config"][cfg_name] = {
            "premium_stop_pct": stop,
            "vix_threshold_own_oos": own_oos,
            "candidate_detail": details,
        }
        print(f"\n==== {cfg_name} (stop={stop}) ====")
        print(f"  VIX threshold-own-OOS: IS-picked X={own_oos.get('is_picked_threshold')} "
              f"IS_exp=${own_oos.get('is_exp_dollar')} -> OOS_exp=${own_oos.get('oos_exp_dollar_at_is_threshold')} "
              f"(n_oos={own_oos.get('oos_n_at_is_threshold')}) generalizes={own_oos.get('oos_generalizes')}")
        fs = own_oos.get("full_series_at_is_threshold", {})
        print(f"    full-series @X: n={fs.get('n')} exp=${fs.get('exp_dollar')} "
              f"allsub+={fs.get('all_sub_windows_positive')} bothdirs={fs.get('both_dirs_positive')} "
              f"DSR={fs.get('dsr_verdict')} robust={fs.get('robust_to_outliers')}")
        for gname, gd in details.items():
            print(f"  {gname:14s} keep={gd['n_kept']:3d} exp=${gd['exp_dollar']:+6.1f} "
                  f"allsub+={gd['all_sub_windows_positive']} bothdirs={gd['both_dirs_positive']} "
                  f"OOS_stbl={gd['oos_sign_stable']} DSR={gd['dsr_verdict']} "
                  f"robust={gd['robust_to_outliers']} by_side={gd['by_side']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
