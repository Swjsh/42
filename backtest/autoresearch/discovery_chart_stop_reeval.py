"""discovery_chart_stop_reeval — re-evaluate the discovery hypotheses on the LIVE exit.

THE BUG THIS FIXES (load-bearing, OP-16/OP-22): the two discovery scorecards
(``infinite-ammo-discovery.json`` + ``j-archetype-discovery.json``) were produced
by ``simulate_signals``, which passes NO ``premium_stop_pct`` override — so every
signal was filled under the v14 default **-8% premium stop**. That exit is exactly
what choked gap-and-go (H2b): WR 42.9% on -8% but 72.6% on chart-stop-only, and a
walk-forward that FAILED on -8% (WF 0.51) but PASSED on chart-stop-only (WF 1.87).
The LIVE engine trades CHART-STOP-ONLY (``premium_stop_pct=-0.99``, the
CHART-STOP-PRIMARY doctrine, L51/L55/C2). So every "marginal" or "dead" hypothesis
on -8% deserves a re-run on the config the engine actually trades.

WHAT THIS DOES
--------------
Re-runs, on REAL OPRA fills, every NOT-yet-shipped / NOT-clearly-dead discovery
hypothesis under BOTH exit configs (chart-stop-only AND the -8% default, shown
side-by-side like ``gap-and-go-LIVE.json``), and applies the FULL OP-22 rigor stack
on the chart-stop-only config:

  * IS / OOS expectancy ($ and %), OOS sign-stability (L166)
  * expanding-anchor WF at cut-fracs 0.60/0.70/0.80, WF median gate >= 0.70,
    all-cuts-OOS-positive
  * DSR/PSR (Bailey-Lopez de Prado, selection-bias deflated, n_trials=30)
  * drop-top-5 robustness (kills lottery edges)
  * by-side (both directions positive)
  * by-quarter regime proxy (q-positive fraction)

SURVIVOR (strict, ALL must hold on chart-stop-only):
  OOS+ ($ AND %)  AND  WF_median >= 0.70  AND  all-cuts-OOS-positive
  AND  DSR != FAIL  AND  drop-top5 mean > 0 (broad-based, not outlier-driven)

HYPOTHESES RE-RUN (per the re-eval mandate):
  H1_intraday_momentum, H2a_gap_fade, H3_orb_rvol, H5_power_hour  (infinite-ammo)
  A2_ma_pullback_resumption                                       (j-archetype)
SKIPPED (conclusively handled elsewhere — see docstring of each):
  A1_vwap_extreme_reversal (DSR FAIL, fade dies on 0DTE per C3),
  H4_vwap_pullback (already re-ratified: chart-stop FAILS WF 0.239),
  H2b_gap_and_go (already shipped: gap-and-go-LIVE.json).

Causality for these detectors is ALREADY established (discovery docstrings +
gap_and_go/vwap causality audits); the trigger logic is unchanged here — only the
EXIT swaps — so no causality re-audit is needed (re-audit only if the trigger
changes, per the re-eval mandate).

PROPOSE-ONLY (Rule 9): reads data, writes per-survivor scorecards to
``analysis/recommendations/{hyp}-LIVE.json``. Touches no params, no heartbeat, no
order path. Pure-Python, $0, deterministic. ATM + ITM1 tiers.

Usage
-----
    backtest/.venv/Scripts/python.exe backtest/autoresearch/discovery_chart_stop_reeval.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # ...\42\backtest
PROJECT = REPO.parent                               # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Reuse the validated discovery detectors + harness verbatim — apples-to-apples.
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    OOS_SPLIT_FRAC,
    align_vix,
    build_day_contexts,
    detect_intraday_momentum,
    detect_gap_fade,
    detect_orb_rvol,
    detect_power_hour,
    load_spy,
    _nearest_cached_strike,
    _quarter,
)
from autoresearch.j_archetype_discovery import (  # noqa: E402
    detect_ma_pullback_resumption,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real, _strike_from_spot  # noqa: E402
from lib.validation.gate import evaluate_candidate  # noqa: E402

SPY_CSV = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_CSV = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
OUT_DIR = PROJECT / "analysis" / "recommendations"

TIERS = {"ATM": 0, "ITM1": -1}
CUT_FRACS = [0.60, 0.70, 0.80]
WF_GATE = 0.70
Q_POS_GATE = 0.60
N_TRIALS_DSR = 30
MAX_STRIKE_STEPS = 4
QTY = 3
# The two exit configs reported side-by-side. live = chart-stop-only (what the
# engine trades); discovery_default reproduces the published discovery numbers.
EXIT_CONFIGS = {"chart_stop_only": -0.99, "discovery_default_-8pct": -0.08}

# Hypotheses to re-run: (key, title, detector, regime_fit, source_scorecard).
HYPOTHESES = {
    "H1_intraday_momentum": (
        "Intraday momentum standalone afternoon entry (Gao-Han-Li-Zhou)",
        detect_intraday_momentum, "bull_trend / bear_trend",
        "analysis/recommendations/infinite-ammo-discovery.json"),
    "H2a_gap_fade": (
        "Opening-gap fade toward prior close",
        detect_gap_fade, "range_pin / neutral",
        "analysis/recommendations/infinite-ammo-discovery.json"),
    "H3_orb_rvol": (
        "Opening-range breakout on elevated RVOL (Zarattini)",
        detect_orb_rvol, "high_vol / bull_trend / bear_trend",
        "analysis/recommendations/infinite-ammo-discovery.json"),
    "H5_power_hour": (
        "Power-hour continuation (ribbon-corroborated)",
        detect_power_hour, "bull_trend / bear_trend",
        "analysis/recommendations/infinite-ammo-discovery.json"),
    "A2_ma_pullback_resumption": (
        "EMA(9/21) trend pullback to the fast EMA that resumes (resumption candle)",
        detect_ma_pullback_resumption, "bull_trend / bear_trend",
        "analysis/recommendations/j-archetype-discovery.json"),
}

# Detectors whose live counterpart already exists (so the scorecard can point at it).
LIVE_DETECTOR = {
    # none of these five have a live watcher yet; survivors get one wired dormant.
}


# ─────────────────────────────────────────────────────────────────────────────
# REAL-FILLS SIM OF A SIGNAL SET AT ONE TIER + ONE EXIT CONFIG
# ─────────────────────────────────────────────────────────────────────────────
def _sim(signals, spy, ribbon, vix, offset, premium_stop_pct):
    """Mirror gap_and_go_ratify._sim — same fill harness, swept premium stop."""
    rows = []
    cov = Counter()
    cov["signals"] = len(signals)
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - offset if sg.side == "P" else atm + offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            cov["cache_miss"] += 1
            continue
        ev = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        f = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup="DISCOVERY", strike_override=strike, entry_vix=ev,
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
    cov["fill_rate"] = round(cov["filled"] / cov["signals"], 3) if cov["signals"] else 0.0
    return rows, dict(cov)


def _wf_norm(is_p, n_is, oos_p, n_oos):
    if n_is == 0 or n_oos == 0 or is_p == 0:
        return 0.0
    return (oos_p / n_oos) / (is_p / n_is)


def _full_metrics(rows, all_dates):
    """Full OP-22 rigor stack on one (tier, exit-config) trade set. Mirrors
    gap_and_go_ratify._full_metrics so the scorecards are directly comparable."""
    if not rows:
        return {"n": 0, "verdict": "NO_TRADES"}
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
    median_wf = round(float(np.median(wf_norms)), 3) if wf_norms else 0.0
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
    drop1 = round(float(spnl[:-1].mean()), 2) if n > 1 else None
    gross_wins = float(pnl[pnl > 0].sum())
    top5_share = round(float(spnl[-5:].sum()) / gross_wins, 3) if gross_wins > 0 else 0.0

    # DSR
    dsr = {}
    try:
        if pct.std(ddof=0) > 0 and n >= 2:
            dsr = evaluate_candidate(pct, n_trials=N_TRIALS_DSR).to_dict()
        else:
            dsr = {"verdict": "DEGENERATE", "note": "zero-variance returns"}
    except Exception as e:  # noqa: BLE001 — surface, never crash the run
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
        "drop_top1_mean_dollar": drop1,
        "top5_winner_share_of_gross_wins": top5_share,
        "robust_to_outliers": bool(n >= 10 and drop5 is not None and drop5 > 0),
        "dsr": dsr, "dsr_verdict": dsr.get("verdict", "UNKNOWN"),
        "exit_reason_hist": dict(Counter(r["exit"] for r in rows)),
    }


def _survivor_gate(m):
    """The STRICT OP-22 SURVIVOR gate on the chart-stop-only config metrics."""
    if m.get("n", 0) == 0:
        return {"_no_trades": False}, False
    gate = {
        "oos_positive_dollar": m["oos_exp_dollar"] > 0,
        "oos_sign_stable_pct": m["oos_sign_stable"],
        "wf_median_ge_0.70": m["median_wf_norm"] >= WF_GATE,
        "all_cuts_oos_positive": m["all_cuts_oos_positive"],
        "dsr_not_fail": m["dsr_verdict"] not in ("FAIL", "ERROR", "UNKNOWN", "DEGENERATE"),
        "robust_drop_top5": m["robust_to_outliers"],
        "both_dirs_positive": m["both_dirs_positive"],
        "sub_window_stable_q>=0.60": m["quarter_positive_fraction"] >= Q_POS_GATE,
    }
    return gate, all(gate.values())


def _print_row(key, tname, cfg, m):
    if m.get("n", 0) == 0:
        print(f"  [{key}/{tname}/{cfg}] NO_TRADES")
        return
    print(f"  [{key}/{tname}/{cfg}] n={m['n']} exp=${m['exp_dollar']:+.1f} WR={m['wr_pct']}% "
          f"OOS$={m['oos_exp_dollar']:+.1f} OOS_stable={m['oos_sign_stable']} "
          f"medWF={m['median_wf_norm']:+.3f} allOOS+={m['all_cuts_oos_positive']} "
          f"q+={m['quarter_positive_fraction']:.0%} DSR={m['dsr_verdict']} "
          f"drop5={m['drop_top5_mean_dollar']} bothDir={m['both_dirs_positive']}")


def main() -> int:
    print(f"Loading SPY {SPY_CSV.name}")
    spy = load_spy(str(SPY_CSV))
    vix = align_vix(spy, str(VIX_CSV))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    cut_i = int(len(all_dates) * OOS_SPLIT_FRAC)
    oos_cut_date = str(all_dates[cut_i])
    print(f"days={len(days)} oos_cut={oos_cut_date}\n")

    summary_table = []          # for the deliverable table (chart-stop-only, ATM)
    survivors = []

    for key, (title, detector, regime_fit, src) in HYPOTHESES.items():
        print(f"=== {key}: {title} ===")
        signals = detector(spy, ribbon, vix, days)
        side_counts = {"P": sum(1 for s in signals if s.side == "P"),
                       "C": sum(1 for s in signals if s.side == "C")}
        print(f"  signals={len(signals)} (C={side_counts['C']} P={side_counts['P']})")

        tiers_out = {}
        for tname, off in TIERS.items():
            cfgs = {}
            for cfg_name, stop in EXIT_CONFIGS.items():
                rows, cov = _sim(signals, spy, ribbon, vix, off, stop)
                m = _full_metrics(rows, all_dates)
                m["coverage"] = cov
                m["premium_stop_pct"] = stop
                if cfg_name == "chart_stop_only":
                    gate, passed = _survivor_gate(m)
                    m["survivor_gate"] = gate
                    m["SURVIVOR"] = passed
                cfgs[cfg_name] = m
                _print_row(key, tname, cfg_name, m)
            tiers_out[tname] = cfgs

        # SURVIVOR decision = ATM chart-stop-only is the live-config headline; a
        # hypothesis SURVIVES if EITHER tier passes the strict gate on chart-stop-only.
        atm_live = tiers_out["ATM"]["chart_stop_only"]
        itm_live = tiers_out["ITM1"]["chart_stop_only"]
        atm_surv = bool(atm_live.get("SURVIVOR"))
        itm_surv = bool(itm_live.get("SURVIVOR"))
        is_survivor = atm_surv or itm_surv
        verdict = "SURVIVOR" if is_survivor else "DEAD"

        # honest one-line verdict for the scorecard
        if is_survivor:
            best = "ATM" if atm_surv else "ITM1"
            one_line = (f"SURVIVOR on chart-stop-only ({best} tier passes all OP-22 gates). "
                        f"Hidden by the -8% discovery exit; +EV on the live config.")
        else:
            # diagnose the dominant failure on ATM chart-stop-only
            if atm_live.get("n", 0) == 0:
                one_line = "DEAD: no fills on chart-stop-only (coverage)."
            else:
                g, _ = _survivor_gate(atm_live)
                fails = [k for k, v in g.items() if not v]
                one_line = (f"DEAD on chart-stop-only: ATM exp ${atm_live['exp_dollar']:+.1f}/"
                            f"WR {atm_live['wr_pct']}%, OOS$ {atm_live['oos_exp_dollar']:+.1f}, "
                            f"medWF {atm_live['median_wf_norm']:+.3f}, DSR {atm_live['dsr_verdict']}. "
                            f"Failed gates: {fails}.")

        # delta vs the -8% default (the whole point: did the exit hide an edge?)
        atm_default = tiers_out["ATM"]["discovery_default_-8pct"]
        exit_delta = None
        if atm_live.get("n") and atm_default.get("n"):
            exit_delta = {
                "chart_stop_exp_dollar": atm_live["exp_dollar"],
                "default_-8pct_exp_dollar": atm_default["exp_dollar"],
                "exp_dollar_lift": round(atm_live["exp_dollar"] - atm_default["exp_dollar"], 2),
                "chart_stop_wr": atm_live["wr_pct"],
                "default_-8pct_wr": atm_default["wr_pct"],
                "chart_stop_medWF": atm_live["median_wf_norm"],
                "default_-8pct_medWF": atm_default["median_wf_norm"],
            }

        scorecard = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "script": "backtest/autoresearch/discovery_chart_stop_reeval.py",
            "setup": key,
            "title": title,
            "regime_fit": regime_fit,
            "source_discovery": src,
            "purpose": (
                "Re-evaluation of a discovery hypothesis on the LIVE exit config "
                "(CHART-STOP-ONLY, premium_stop_pct=-0.99). The source discovery scorecard "
                "used the v14 default -8% premium stop (simulate_signals passes no override) "
                "— the exact exit that choked gap-and-go. Both configs are shown side-by-side "
                "(like gap-and-go-LIVE.json). The chart-stop-only result is what the live "
                "engine would trade; the SURVIVOR verdict is decided on it alone."
            ),
            "research_detector": (
                f"backtest/autoresearch/"
                f"{'j_archetype_discovery.py (detect_ma_pullback_resumption)' if key.startswith('A') else 'infinite_ammo_discovery.py'}"
            ),
            "causality": {
                "verdict": "PASS (established at discovery time)",
                "note": "These detectors' trigger logic is UNCHANGED here — only the EXIT "
                        "config swaps. Causality (all features at-or-before trigger bar; fill "
                        "= next bar open) was established in the discovery docstrings + the "
                        "gap_and_go/vwap causality audits. No re-audit needed (re-audit only "
                        "if the trigger changes).",
            },
            "fills": (
                "lib.simulator_real.simulate_trade_real (real OPRA bars, causal next-bar-open "
                "entry, v15 exit stack: chart-level stop + ribbon-flip + chandelier + 15:50 "
                "time stop). premium_stop_pct swept: chart_stop_only=-0.99 (live) vs "
                "discovery_default=-0.08 (the choking exit)."
            ),
            "data": {"spy": SPY_CSV.name, "vix": VIX_CSV.name, "days": len(days),
                     "date_range": [str(all_dates[0]), str(all_dates[-1])],
                     "oos_cut_date": oos_cut_date},
            "signal_count": len(signals), "side_counts": side_counts,
            "exit_methodology": (
                "Headline/verdict = CHART-STOP-ONLY (premium_stop_pct=-0.99), the "
                "doctrinally-correct exit for these first-strike entry classes (L51/L55/C2; "
                "live CHART-STOP-PRIMARY doctrine). The source discovery numbers used "
                "premium_stop=-0.08. Both reported in tiers.{TIER}.{config}."
            ),
            "exit_config_delta_ATM": exit_delta,
            "tiers": tiers_out,
            "survivor_bar": {
                "rule": "OP-22 SURVIVOR (all on chart-stop-only): OOS+ ($ AND %) AND "
                        "WF_median>=0.70 AND all-cuts-OOS-positive AND DSR not-FAIL AND "
                        "drop-top5 mean>0 AND both-dirs+ AND sub-window-stable (q>=60%).",
                "evaluated_on": "ATM chart_stop_only (+ ITM1 as the alternate tier)",
                "ATM_gate": atm_live.get("survivor_gate"),
                "ITM1_gate": itm_live.get("survivor_gate"),
                "ATM_pass": atm_surv, "ITM1_pass": itm_surv,
            },
            "verdict": verdict,
            "verdict_one_line": one_line,
            "caveats": [
                "Proxy strikes (L58): ATM not always cached; nearest-cached strike used in "
                "the sim (true offset disclosed per trade). ITM/OTM proxy shifts P&L modestly.",
                "Standalone single-setup eval — measured on proxy strikes, not real ★★★ "
                "levels. A survivor is a candidate worth a real-level re-test + the dormant "
                "wiring below; OP-21 live gate (3 live J confirmations) STILL STANDS before "
                "any live order path.",
            ],
        }
        out_path = OUT_DIR / f"{key}-LIVE.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(scorecard, indent=2, default=str))
        print(f"  -> {verdict}: {one_line}")
        print(f"  -> wrote {out_path.name}\n")

        # deliverable table row (chart-stop-only, ATM)
        summary_table.append({
            "hyp": key, "tier": "ATM",
            "n": atm_live.get("n", 0),
            "is_exp": atm_live.get("is_exp_dollar"),
            "oos_exp": atm_live.get("oos_exp_dollar"),
            "wf": atm_live.get("median_wf_norm"),
            "all_cuts": atm_live.get("all_cuts_oos_positive"),
            "dsr": atm_live.get("dsr_verdict"),
            "drop5": atm_live.get("drop_top5_mean_dollar"),
            "verdict": verdict,
        })
        if is_survivor:
            survivors.append({"hyp": key, "title": title, "regime_fit": regime_fit,
                              "atm_survivor": atm_surv, "itm_survivor": itm_surv,
                              "scorecard": str(out_path.relative_to(PROJECT))})

    # ── Deliverable table ─────────────────────────────────────────────────────
    print("=" * 100)
    print("RE-EVAL ON CHART-STOP-ONLY (ATM tier) — SURVIVOR/DEAD")
    print("=" * 100)
    hdr = f"{'hypothesis':<28}{'n':>5}{'IS$':>9}{'OOS$':>9}{'WF':>8}{'allOOS+':>9}{'DSR':>7}{'drop5$':>9}  verdict"
    print(hdr)
    print("-" * 100)
    for r in summary_table:
        is_s = f"{r['is_exp']:+.1f}" if r["is_exp"] is not None else "—"
        oos_s = f"{r['oos_exp']:+.1f}" if r["oos_exp"] is not None else "—"
        wf_s = f"{r['wf']:+.3f}" if r["wf"] is not None else "—"
        d5_s = f"{r['drop5']:+.1f}" if r["drop5"] is not None else "—"
        print(f"{r['hyp']:<28}{r['n']:>5}{is_s:>9}{oos_s:>9}{wf_s:>8}"
              f"{str(r['all_cuts']):>9}{str(r['dsr']):>7}{d5_s:>9}  {r['verdict']}")
    print("-" * 100)
    print(f"SURVIVORS: {len(survivors)} -> {[s['hyp'] for s in survivors]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
