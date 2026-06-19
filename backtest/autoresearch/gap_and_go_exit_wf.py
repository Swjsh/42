"""Exit-sensitivity + walk-forward for H2b gap_and_go (real OPRA fills).

WHY THIS EXISTS: the discovery scorecard (infinite-ammo-discovery.json) ran
simulate_signals(), which calls simulate_trade_real WITHOUT premium_stop_pct -> it
defaulted to -0.08 (the v14 BULL premium stop). But the project's own ratified
doctrine for first-strike / discovery-class entries is CHART-STOP ONLY, premium-stop
DISABLED (L51, L55, lesson C2): the structural stop is the trigger bar's opposite
extreme (already passed as rejection_level). The 2026-Q2 WF failure was 10/11 trades
hitting EXIT_ALL_PREMIUM_STOP at exactly -8% — an EXIT-knob artifact, possibly not an
entry-edge failure. This harness re-simulates gap_and_go directly (own simulator
calls, not the shipped discovery path) across a grid of premium stops, including
chart-stop-only, and runs the same expanding-anchor WF at each, so the ship gate
(WF>=0.70 AND every-cut-OOS-positive AND quarters-positive) is checkable under the
CORRECT exit.

Pure, $0, read-only. Reuses the EXACT detector (detect_gap_and_go) + the EXACT
real-fills simulator (simulate_trade_real). The ONLY thing swept is premium_stop_pct.

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/gap_and_go_exit_wf.py
      [--tier ATM|ITM1] [--out PATH]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    load_spy, align_vix, build_day_contexts, detect_gap_and_go,
    _nearest_cached_strike, _quarter,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real, _strike_from_spot  # noqa: E402
from lib.validation.gate import evaluate_candidate  # noqa: E402

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
TIERS = {"ATM": 0, "ITM1": -1}
CUT_FRACS = [0.60, 0.70, 0.80]
# Premium-stop grid. -0.99 == chart-stop-only (premium stop unreachable; the
# structural rejection_level stop governs). -0.08 reproduces the discovery default.
STOP_GRID = [-0.99, -0.50, -0.30, -0.20, -0.08]
WF_GATE = 0.70
Q_POS_GATE = 0.60
N_TRIALS_DSR = 30  # match discovery's deflation count


def _simulate(signals, spy, ribbon, vix, offset, premium_stop_pct):
    rows = []
    n_fill = n_miss = n_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - offset if sg.side == "P" else atm + offset
        strike = _nearest_cached_strike(d, target, sg.side, 4)
        if strike is None:
            n_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "disc"],
            side=sg.side, qty=3, setup="DISCOVERY", strike_override=strike,
            entry_vix=entry_vix, premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            n_none += 1
            continue
        n_fill += 1
        rows.append({
            "date": str(d), "side": sg.side,
            "pnl": round(float(fill.dollar_pnl), 2),
            "pct": round(float(fill.pct_return_on_premium), 5),
            "exit": fill.exit_reason.name if fill.exit_reason else "NONE",
        })
    return rows, {"filled": n_fill, "cache_miss": n_miss, "sim_none": n_none}


def _wf_norm(is_pnl, n_is, oos_pnl, n_oos):
    if n_is == 0 or n_oos == 0 or is_pnl == 0:
        return 0.0
    return (oos_pnl / n_oos) / (is_pnl / n_is)


def _analyze(rows, all_dates):
    pnl = np.array([r["pnl"] for r in rows], float)
    pct = np.array([r["pct"] for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    dated = sorted([(dt.date.fromisoformat(r["date"]), r) for r in rows], key=lambda x: x[0])

    wf_windows = []
    for frac in CUT_FRACS:
        cut_date = all_dates[int(len(all_dates) * frac)]
        isr = [r for d, r in dated if d < cut_date]
        oosr = [r for d, r in dated if d >= cut_date]
        is_p = float(sum(r["pnl"] for r in isr))
        oos_p = float(sum(r["pnl"] for r in oosr))
        wf = _wf_norm(is_p, len(isr), oos_p, len(oosr))
        wf_windows.append({
            "cut_frac": frac, "cut_date": str(cut_date),
            "is_n": len(isr), "oos_n": len(oosr),
            "is_total": round(is_p, 2), "oos_total": round(oos_p, 2),
            "oos_exp": round(oos_p / len(oosr), 2) if oosr else 0.0,
            "wf_norm": round(wf, 3), "oos_positive": bool(oos_p > 0),
        })
    wf_norms = [w["wf_norm"] for w in wf_windows]
    median_wf = statistics.median(wf_norms) if wf_norms else 0.0
    all_oos_pos = all(w["oos_positive"] for w in wf_windows)

    by_q = {}
    for r in rows:
        by_q.setdefault(_quarter(r["date"]), []).append(r["pnl"])
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)
    q_frac = round(q_pos / len(quarters), 2) if quarters else 0.0

    # drop-top-5 robustness
    spnl = np.sort(pnl)
    drop5 = round(float(spnl[:-5].mean()), 2) if n > 5 else None

    # DSR on % stream
    dsr_v = "NA"
    try:
        if pct.std(ddof=0) > 0 and n >= 2:
            dsr_v = evaluate_candidate(pct, n_trials=N_TRIALS_DSR).verdict
    except Exception as e:  # noqa: BLE001
        dsr_v = f"ERR:{e}"

    # both-direction split
    by_side = {}
    for sd in ("C", "P"):
        s = [r["pnl"] for r in rows if r["side"] == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1)}
    both_pos = bool(len(by_side) == 2 and all(b["exp"] > 0 for b in by_side.values()))

    wf_pass = bool(all_oos_pos and median_wf >= WF_GATE and q_frac >= Q_POS_GATE)
    return {
        "n": n, "wins": wins, "wr": round(100 * wins / n, 1) if n else 0.0,
        "exp_dollar": round(float(pnl.mean()), 2) if n else 0.0,
        "total_dollar": round(float(pnl.sum()), 2),
        "drop_top5_mean": drop5,
        "by_side": by_side, "both_dirs_positive": both_pos,
        "dsr_verdict": dsr_v,
        "wf_windows": wf_windows,
        "median_wf_norm": round(median_wf, 3),
        "all_cuts_oos_positive": all_oos_pos,
        "quarters": quarters, "quarter_positive_fraction": q_frac,
        "exit_reason_hist": dict(Counter(r["exit"] for r in rows)),
        "WF_PASS": wf_pass,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tier", default="ATM", choices=list(TIERS))
    ap.add_argument("--out", default=str(PROJECT / "analysis" / "recommendations" /
                                         "gap-and-go-exit-wf.json"))
    args = ap.parse_args()
    offset = TIERS[args.tier]

    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    signals = detect_gap_and_go(spy, ribbon, vix, days)
    print(f"[{args.tier}] signals={len(signals)}  sweeping premium stops {STOP_GRID}\n")

    variants = {}
    for stop in STOP_GRID:
        rows, cov = _simulate(signals, spy, ribbon, vix, offset, stop)
        res = _analyze(rows, all_dates)
        res["coverage"] = cov
        label = "chart_stop_only" if stop <= -0.99 else f"prem_{int(stop*100)}"
        variants[label] = {"premium_stop_pct": stop, **res}
        wfw = " ".join(f"{w['cut_frac']:.0%}:{w['wf_norm']:+.2f}{'+' if w['oos_positive'] else '-'}"
                       for w in res["wf_windows"])
        print(f"  stop={stop:+.2f} ({label:16}) n={res['n']:3} exp=${res['exp_dollar']:+6.1f} "
              f"WR={res['wr']:4.1f}% drop5=${res['drop_top5_mean']} DSR={res['dsr_verdict']:5} "
              f"q+={res['quarter_positive_fraction']:.0%} bothdir={res['both_dirs_positive']}")
        print(f"       WF[{wfw}] medWF={res['median_wf_norm']:+.3f} allOOS+={res['all_cuts_oos_positive']} "
              f"=> {'WF_PASS' if res['WF_PASS'] else 'WF_FAIL'}")

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "setup": "H2b_gap_and_go", "tier": args.tier,
        "purpose": ("Exit-sensitivity + expanding-anchor WF. Tests whether the "
                    "2026-Q2 WF failure is an EXIT-knob artifact (10/11 trades hit the "
                    "-8% premium stop) vs an entry-edge failure. Chart-stop-only "
                    "(-0.99) is the doctrinally-correct exit for this entry class "
                    "(L51/L55/C2)."),
        "data": {"spy": SPY.name, "days": len(days),
                 "date_range": [str(all_dates[0]), str(all_dates[-1])]},
        "stop_grid": STOP_GRID, "cut_fracs": CUT_FRACS,
        "wf_gate": WF_GATE, "q_pos_gate": Q_POS_GATE,
        "variants": variants,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
