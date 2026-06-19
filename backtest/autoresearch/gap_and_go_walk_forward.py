"""Walk-forward + sub-window stability for H2b gap_and_go (real OPRA fills).

Standalone, $0, read-only. The discovery scorecard (infinite-ammo-discovery.json)
already reports a single chronological 70/30 IS/OOS split + per-quarter expectancy.
This harness adds the project's expanding-window WALK-FORWARD discipline to the
gap_and_go survivor specifically, so the ship-validated-wins gate (WF >= 0.70 AND
sub-window stable) is checkable on THIS setup with real numbers.

Why a bespoke WF here (not rolling_walk_forward.py): that harness runs the full
orchestrator engine (the BEARISH_REJECTION book), not a standalone detector. We
reuse the EXACT discovery detector (detect_gap_and_go) + the EXACT real-fills
simulator (simulate_signals) so the WF measures the same edge the scorecard found.

Sample reality (stated, not hidden): gap_and_go fires only on gap days — ~96 signals
/ ~84 ATM fills over 17 months (~5/month). Monthly OOS windows would be 4-6 trades —
too thin for a per-window ratio. So we use:

  1. EXPANDING-ANCHOR WF at multiple chronological cut points (60/70/80% of days):
     train on [start, cut], test on (cut, end]; WF_norm = (oos$/n_oos)/(is$/n_is).
     A robust edge holds WF_norm >= 0.70 across cuts AND keeps OOS$ > 0.
  2. PER-QUARTER sub-window stability: fraction of quarters with positive expectancy
     (carried from the same real-fills stream) — the sub-window-stable signal.
  3. Both-direction split per window (a real intraday edge survives on calls AND puts).

Verdict: WF_PASS iff every cut has OOS$ > 0 AND median WF_norm >= 0.70 AND
quarter-positive-fraction >= 0.60. Honest about n at each step.

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/gap_and_go_walk_forward.py
      [--tier ATM|ITM1] [--out PATH]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    load_spy,
    align_vix,
    build_day_contexts,
    detect_gap_and_go,
    simulate_signals,
    _quarter,
)
from lib.ribbon import compute_ribbon  # noqa: E402

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

# Strike tier -> simulator offset (sim convention; ATM=0, ITM1=-1, matching discovery).
TIERS = {"ATM": 0, "ITM1": -1}
CUT_FRACS = [0.60, 0.70, 0.80]
WF_GATE = 0.70
Q_POS_GATE = 0.60


def _rows_to_pnl(rows):
    return [r.dollar_pnl for r in rows]


def _wf_norm(is_pnl, n_is, oos_pnl, n_oos):
    if n_is == 0 or n_oos == 0 or is_pnl == 0:
        return 0.0
    return (oos_pnl / n_oos) / (is_pnl / n_is)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tier", default="ATM", choices=list(TIERS))
    ap.add_argument("--out", default=str(PROJECT / "analysis" / "recommendations" /
                                         "gap-and-go-walk-forward.json"))
    args = ap.parse_args()
    offset = TIERS[args.tier]

    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]

    signals = detect_gap_and_go(spy, ribbon, vix, days)
    rows, cov = simulate_signals(signals, spy, ribbon, vix, qty=3,
                                 strike_offset=offset, max_strike_steps=4)
    print(f"[{args.tier}] gap_and_go signals={len(signals)} filled={len(rows)} "
          f"(fill_rate={cov['fill_rate']})")

    # Attach a date object to each row for chronological splitting.
    dated = [(dt.date.fromisoformat(r.date), r) for r in rows]
    dated.sort(key=lambda x: x[0])

    # ---- (1) expanding-anchor WF at several cut points --------------------------
    wf_windows = []
    for frac in CUT_FRACS:
        cut_i = int(len(all_dates) * frac)
        cut_date = all_dates[cut_i]
        is_rows = [r for d, r in dated if d < cut_date]
        oos_rows = [r for d, r in dated if d >= cut_date]
        is_pnl = float(sum(_rows_to_pnl(is_rows)))
        oos_pnl = float(sum(_rows_to_pnl(oos_rows)))
        n_is, n_oos = len(is_rows), len(oos_rows)
        wf = _wf_norm(is_pnl, n_is, oos_pnl, n_oos)
        is_exp = is_pnl / n_is if n_is else 0.0
        oos_exp = oos_pnl / n_oos if n_oos else 0.0

        def _side_exp(rs, sd):
            s = [r.dollar_pnl for r in rs if r.side == sd]
            return (round(sum(s) / len(s), 2), len(s)) if s else (None, 0)

        wf_windows.append({
            "cut_frac": frac,
            "cut_date": str(cut_date),
            "is_n": n_is, "oos_n": n_oos,
            "is_total_dollar": round(is_pnl, 2), "oos_total_dollar": round(oos_pnl, 2),
            "is_exp_dollar": round(is_exp, 2), "oos_exp_dollar": round(oos_exp, 2),
            "wf_norm": round(wf, 3),
            "oos_positive": bool(oos_pnl > 0),
            "oos_C_exp": _side_exp(oos_rows, "C")[0], "oos_C_n": _side_exp(oos_rows, "C")[1],
            "oos_P_exp": _side_exp(oos_rows, "P")[0], "oos_P_n": _side_exp(oos_rows, "P")[1],
            "wf_pass": bool(wf >= WF_GATE and oos_pnl > 0),
        })
        print(f"  cut={frac:.0%} ({cut_date}): IS n={n_is} ${is_pnl:+.0f} (exp ${is_exp:+.1f}) "
              f"| OOS n={n_oos} ${oos_pnl:+.0f} (exp ${oos_exp:+.1f}) | WF_norm={wf:+.3f} "
              f"{'PASS' if wf >= WF_GATE and oos_pnl > 0 else 'fail'}")

    wf_norms = [w["wf_norm"] for w in wf_windows]
    median_wf = statistics.median(wf_norms) if wf_norms else 0.0
    all_oos_pos = all(w["oos_positive"] for w in wf_windows)

    # ---- (2) per-quarter sub-window stability ----------------------------------
    by_q = {}
    for r in rows:
        by_q.setdefault(_quarter(r.date), []).append(r.dollar_pnl)
    quarters = {q: {"n": len(v), "exp_dollar": round(sum(v) / len(v), 2),
                    "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp_dollar"] > 0)
    q_frac = round(q_pos / len(quarters), 2) if quarters else 0.0
    print(f"  quarters positive: {q_pos}/{len(quarters)} ({q_frac:.0%})")

    # ---- verdict ---------------------------------------------------------------
    wf_pass = bool(all_oos_pos and median_wf >= WF_GATE and q_frac >= Q_POS_GATE)
    verdict = "WF_PASS" if wf_pass else "WF_FAIL"

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "setup": "H2b_gap_and_go",
        "tier": args.tier,
        "data": {"spy": SPY.name, "days": len(days),
                 "date_range": [str(all_dates[0]), str(all_dates[-1])]},
        "method": {
            "detector": "autoresearch.infinite_ammo_discovery.detect_gap_and_go",
            "fills": "lib.simulator_real (real OPRA, next-bar-open, v15 exit stack)",
            "wf": "expanding-anchor at cut fracs " + str(CUT_FRACS) +
                  "; WF_norm=(oos$/n_oos)/(is$/n_is)",
            "gates": f"every cut OOS$>0 AND median WF_norm>={WF_GATE} AND "
                     f"quarter-positive-frac>={Q_POS_GATE}",
        },
        "coverage": cov,
        "wf_windows": wf_windows,
        "median_wf_norm": round(median_wf, 3),
        "all_cuts_oos_positive": all_oos_pos,
        "quarters": quarters,
        "quarter_positive_fraction": q_frac,
        "n_total_fills": len(rows),
        "caveat": (
            "Gap-and-go fires only on gap days (~5 fills/month). Per-cut OOS samples "
            "are modest (n~17-34); WF_norm is a directional generalization check, not a "
            "high-power estimate. Read with the DSR PASS + drop-top-5 robustness from "
            "the discovery scorecard, not alone."
        ),
        "verdict": verdict,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n{verdict}  (median WF_norm={median_wf:+.3f}, all_cuts_oos_pos={all_oos_pos}, "
          f"q_pos_frac={q_frac:.0%})")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
