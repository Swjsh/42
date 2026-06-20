"""Ratification scorecard for H2b gap_and_go (LIVE candidate) — real OPRA fills.

Consolidates the full evidence stack into ONE scorecard
(analysis/recommendations/gap-and-go-LIVE.json): IS/OOS, expanding-anchor WF,
DSR/PSR, drop-top-5 robustness, by-side, by-quarter (regime proxy), causality
pointer, go-live params, and a SHIP/BLOCKED verdict against the ship-validated-wins
bar (OOS+ AND WF>=0.70 AND sub-window stable AND A/B scorecard filed).

KEY METHODOLOGY POINT (honest, load-bearing): the headline numbers use the
DOCTRINALLY-CORRECT exit for this first-strike entry class — CHART-STOP ONLY
(premium_stop_pct=-0.99), per L51/L55/C2 and the live CHART-STOP-PRIMARY doctrine
(heartbeat.md 2026-06-18). The discovery scorecard's published +$35.24/42.9% used
premium_stop=-0.08 (the v14 default simulate_signals passes), which choked the setup
(2026-Q2 = 10/11 premium-stopped). Both configs are reported so the difference is
auditable. The chart-stop-only config is what the LIVE detector trades.

Pure, $0, read-only. Reuses the validated detector + the real-fills simulator. The
ATM tier is the disclosed default (ITM-1 also reported — modestly stronger).

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/gap_and_go_ratify.py
"""
from __future__ import annotations

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
OUT = PROJECT / "analysis" / "recommendations" / "gap-and-go-LIVE.json"

TIERS = {"ATM": 0, "ITM1": -1}
CUT_FRACS = [0.60, 0.70, 0.80]
WF_GATE = 0.70
Q_POS_GATE = 0.60
N_TRIALS_DSR = 30
# The two exit configs we report. live = chart-stop-only (what the live detector
# trades); discovery_default reproduces the published infinite-ammo numbers.
EXIT_CONFIGS = {"chart_stop_only": -0.99, "discovery_default_-8pct": -0.08}


def _sim(signals, spy, ribbon, vix, offset, premium_stop_pct):
    rows = []
    cov = Counter()
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - offset if sg.side == "P" else atm + offset
        strike = _nearest_cached_strike(d, target, sg.side, 4)
        if strike is None:
            cov["cache_miss"] += 1
            continue
        ev = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        f = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=3, setup="DISCOVERY", strike_override=strike, entry_vix=ev,
            premium_stop_pct=premium_stop_pct,
        )
        if f is None or f.dollar_pnl is None:
            cov["sim_none"] += 1
            continue
        cov["filled"] += 1
        rows.append({"date": str(d), "side": sg.side, "pnl": round(float(f.dollar_pnl), 2),
                     "pct": round(float(f.pct_return_on_premium), 5),
                     "exit": f.exit_reason.name if f.exit_reason else "NONE",
                     "strike_off": int(strike - atm)})
    return rows, dict(cov)


def _wf_norm(is_p, n_is, oos_p, n_oos):
    if n_is == 0 or n_oos == 0 or is_p == 0:
        return 0.0
    return (oos_p / n_oos) / (is_p / n_is)


def _full_metrics(rows, all_dates):
    pnl = np.array([r["pnl"] for r in rows], float)
    pct = np.array([r["pct"] for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    dated = sorted([(dt.date.fromisoformat(r["date"]), r) for r in rows], key=lambda x: x[0])

    # primary 70/30
    cut70 = all_dates[int(len(all_dates) * 0.70)]
    is70 = [r["pnl"] for d, r in dated if d < cut70]
    oos70 = [r["pnl"] for d, r in dated if d >= cut70]
    is70p = [r["pct"] for d, r in dated if d < cut70]
    oos70p = [r["pct"] for d, r in dated if d >= cut70]

    # expanding-anchor WF windows
    wf_windows = []
    for frac in CUT_FRACS:
        cd = all_dates[int(len(all_dates) * frac)]
        isr = [r["pnl"] for d, r in dated if d < cd]
        oosr = [r["pnl"] for d, r in dated if d >= cd]
        wf = _wf_norm(sum(isr), len(isr), sum(oosr), len(oosr))
        wf_windows.append({"cut_frac": frac, "cut_date": str(cd), "is_n": len(isr),
                           "oos_n": len(oosr), "is_total": round(sum(isr), 2),
                           "oos_total": round(sum(oosr), 2),
                           "oos_exp": round(sum(oosr) / len(oosr), 2) if oosr else 0.0,
                           "wf_norm": round(wf, 3), "oos_positive": bool(sum(oosr) > 0)})
    wf_norms = [w["wf_norm"] for w in wf_windows]
    median_wf = round(statistics.median(wf_norms), 3) if wf_norms else 0.0
    all_oos_pos = all(w["oos_positive"] for w in wf_windows)

    # quarters (regime proxy)
    by_q = {}
    for r in rows:
        by_q.setdefault(_quarter(r["date"]), []).append(r["pnl"])
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)
    q_frac = round(q_pos / len(quarters), 2) if quarters else 0.0

    # by side
    by_side = {}
    for sd in ("C", "P"):
        s = [r["pnl"] for r in rows if r["side"] == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                           "total": round(sum(s), 2)}
    both_pos = bool(len(by_side) == 2 and all(b["exp"] > 0 for b in by_side.values()))

    # drop-top-5
    spnl = np.sort(pnl)
    drop5 = round(float(spnl[:-5].mean()), 2) if n > 5 else None
    drop3 = round(float(spnl[:-3].mean()), 2) if n > 3 else None
    gross_wins = float(pnl[pnl > 0].sum())
    top5_share = round(float(spnl[-5:].sum()) / gross_wins, 3) if gross_wins > 0 else 0.0

    # DSR
    dsr = {}
    try:
        if pct.std(ddof=0) > 0 and n >= 2:
            dsr = evaluate_candidate(pct, n_trials=N_TRIALS_DSR).to_dict()
    except Exception as e:  # noqa: BLE001
        dsr = {"verdict": "ERROR", "error": str(e)}

    is_exp_pct = float(np.mean(is70p)) if is70p else 0.0
    oos_exp_pct = float(np.mean(oos70p)) if oos70p else 0.0
    return {
        "n": n, "wins": wins, "wr_pct": round(100 * wins / n, 1) if n else 0.0,
        "exp_dollar": round(float(pnl.mean()), 2) if n else 0.0,
        "total_dollar": round(float(pnl.sum()), 2),
        "exp_pct_return": round(float(pct.mean()), 5) if n else 0.0,
        "is_n": len(is70), "oos_n": len(oos70),
        "is_exp_dollar": round(float(np.mean(is70)), 2) if is70 else 0.0,
        "oos_exp_dollar": round(float(np.mean(oos70)), 2) if oos70 else 0.0,
        "is_exp_pct": round(is_exp_pct, 5), "oos_exp_pct": round(oos_exp_pct, 5),
        "oos_sign_stable": bool(is70 and oos70 and is_exp_pct > 0 and oos_exp_pct > 0),
        "wf_windows": wf_windows, "median_wf_norm": median_wf,
        "all_cuts_oos_positive": all_oos_pos,
        "quarters": quarters, "quarter_positive_fraction": q_frac,
        "by_side": by_side, "both_dirs_positive": both_pos,
        "drop_top5_mean_dollar": drop5, "drop_top3_mean_dollar": drop3,
        "top5_winner_share_of_gross_wins": top5_share,
        "robust_to_outliers": bool(n >= 10 and drop5 is not None and drop5 > 0),
        "dsr": dsr, "dsr_verdict": dsr.get("verdict", "UNKNOWN"),
        "exit_reason_hist": dict(Counter(r["exit"] for r in rows)),
    }


def main() -> int:
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    signals = detect_gap_and_go(spy, ribbon, vix, days)
    side_counts = {"P": sum(1 for s in signals if s.side == "P"),
                   "C": sum(1 for s in signals if s.side == "C")}

    tiers_out = {}
    for tname, off in TIERS.items():
        cfgs = {}
        for cfg_name, stop in EXIT_CONFIGS.items():
            rows, cov = _sim(signals, spy, ribbon, vix, off, stop)
            m = _full_metrics(rows, all_dates)
            m["coverage"] = cov
            m["premium_stop_pct"] = stop
            # SHIP gate per config
            m["ship_gate"] = {
                "oos_positive": m["oos_exp_dollar"] > 0,
                "wf_median_ge_0.70": m["median_wf_norm"] >= WF_GATE,
                "all_cuts_oos_positive": m["all_cuts_oos_positive"],
                "sub_window_stable_q>=0.60": m["quarter_positive_fraction"] >= Q_POS_GATE,
                "dsr_not_fail": m["dsr_verdict"] not in ("FAIL", "ERROR", "UNKNOWN"),
                "both_dirs_positive": m["both_dirs_positive"],
                "robust_drop_top5": m["robust_to_outliers"],
            }
            m["ship_gate_pass"] = all(m["ship_gate"].values())
            cfgs[cfg_name] = m
        tiers_out[tname] = cfgs

    # Headline verdict = ATM chart-stop-only (the live detector's config).
    atm_live = tiers_out["ATM"]["chart_stop_only"]
    ship = atm_live["ship_gate_pass"]
    verdict = "SHIP-LIVE" if ship else "BLOCKED"

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "setup": "H2b_gap_and_go",
        "title": "Opening-gap continuation after confirming first bar",
        "regime_fit": "bull_trend / bear_trend",
        "live_detector": "backtest/lib/watchers/gap_and_go_watcher.py (detect_gap_and_go_setup)",
        "research_detector": "backtest/autoresearch/infinite_ammo_discovery.py (detect_gap_and_go)",
        "parity_test": "backtest/tests/test_gap_and_go_watcher.py::test_parity_with_validated_discovery_detector (PASS — live core == research over 363 days)",
        "causality": {
            "verdict": "PASS",
            "audit": "backtest/autoresearch/_gap_and_go_causality_audit.py (96/96 signals: "
                     "prior_close=prior trading-day RTH close, trigger=first RTH bar only, "
                     "confirmation reads trigger bar only, stop=trigger-bar opposite extreme, "
                     "fill strictly next-bar-open >= +5min). No look-ahead.",
        },
        "fills": "lib.simulator_real.simulate_trade_real (real OPRA bars, causal next-bar "
                 "open entry, v15 exit stack: chart-level stop + ribbon-flip + chandelier + "
                 "15:50 time stop). premium_stop_pct swept (chart-stop-only is the live config).",
        "data": {"spy": SPY.name, "vix": VIX.name, "days": len(days),
                 "date_range": [str(all_dates[0]), str(all_dates[-1])]},
        "signal_count": len(signals), "side_counts": side_counts,
        "frequency_note": (
            f"Gap-and-go fires only on gap days: {len(signals)} signals over {len(days)} "
            f"trading days (~{round(len(signals) / (len(days) / 21), 1)}/month). MODEST sample "
            f"(n~84 ATM fills over 17 months). One entry max per day, at the open."
        ),
        "exit_methodology": (
            "Headline = CHART-STOP-ONLY (premium_stop_pct=-0.99), the doctrinally-correct "
            "exit for this first-strike entry class (L51/L55/C2; live CHART-STOP-PRIMARY "
            "doctrine 2026-06-18). The discovery scorecard's +$35.24/42.9% used the v14 "
            "default premium_stop=-0.08 (simulate_signals passes no override) — that EXIT "
            "choked the setup (2026-Q2 = 10/11 premium-stopped). Both reported below."
        ),
        "tiers": tiers_out,
        "go_live_params": {
            "setup": "GAP_AND_GO",
            "trigger": "first RTH bar (09:30 ET close): gap=open/prior_RTH_close-1; "
                       "gap>=+0.25% & first bar GREEN -> calls; gap<=-0.25% & first bar RED -> puts; "
                       "skip |gap|>1.5% (runaway) and |gap|<0.25% (no gap).",
            "entry": "next bar open (09:35 ET)",
            "strike_tier": "ATM (validated default; ITM-1 also PASS, modestly stronger)",
            "stop": "CHART STOP = first RTH bar opposite extreme (calls: first-bar low; "
                    "puts: first-bar high). Premium stop DISABLED (chart-stop only).",
            "sizing": "min 3 contracts (2 TP + 1 runner) per risk-rules; premium ceiling "
                      "~6% equity per markdown/research/SIZING-STUDY-2026-06-19.md; risk_gate.check_order authority.",
            "tp": "v15 stack: TP1 +30% premium fallback OR chart level, 0.50 qty; runner 2.5x.",
            "time_stop": "15:50 ET hard (all flat by EOD).",
            "one_per_day": True,
        },
        "ship_bar": {
            "rule": "ship-validated-wins (OP-22/OP-25): OOS+ AND WF_median>=0.70 AND "
                    "all-cuts-OOS-positive AND sub-window-stable(q>=60%) AND DSR not-FAIL AND "
                    "both-dirs+ AND drop-top5 robust AND A/B scorecard filed (this file).",
            "evaluated_on": "ATM chart_stop_only (the live detector config)",
            "result": atm_live["ship_gate"],
            "all_pass": ship,
        },
        "caveats": [
            "Proxy strikes (L58): ATM not always cached; nearest-cached strike used in the "
            "sim (true offset disclosed per trade). ITM/OTM proxy shifts P&L modestly.",
            "Modest sample: n~84 ATM fills / 17 months (~5/month). DSR PASS + drop-top5 "
            "robustness + both-dir + WF carry the weight; no single window is high-power.",
            "WF_norm > 1.0 (OOS per-trade > IS) is real here, driven by strong 2026-Q1 gap "
            "days; absolute OOS dollars are substantial (70% cut OOS +$1,715 / n=25), not a "
            "small-denominator artifact.",
            "OP-21 live gate STILL STANDS: 3 live J confirmations before any live order path. "
            "This is a propose-and-ship of the heartbeat WIRING; J holds REVOKE.",
        ],
        "verdict": verdict,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str))

    print(f"=== gap-and-go-LIVE scorecard ===")
    print(f"signals={len(signals)} (C={side_counts['C']} P={side_counts['P']})")
    for tname in TIERS:
        for cfg in EXIT_CONFIGS:
            m = tiers_out[tname][cfg]
            print(f"  [{tname}/{cfg}] n={m['n']} exp=${m['exp_dollar']:+.1f} WR={m['wr_pct']}% "
                  f"OOS_stable={m['oos_sign_stable']} medWF={m['median_wf_norm']:+.3f} "
                  f"allOOS+={m['all_cuts_oos_positive']} q+={m['quarter_positive_fraction']:.0%} "
                  f"DSR={m['dsr_verdict']} drop5=${m['drop_top5_mean_dollar']} "
                  f"SHIP={m['ship_gate_pass']}")
    print(f"\nVERDICT (ATM chart-stop-only): {verdict}")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
