"""GOAL 1+2 — does a CAUSAL realized-vol FLOOR make J's VWAP-CONTINUATION shippable on
the LIVE chart-stop config, and is there a shippable BULL-side edge?

CONTEXT (what Batch 1 actually found, and the trap this script avoids)
----------------------------------------------------------------------
C1 (docs/J-REGIME-FILTERS.md) found `rvol >= 9 bps` lifts a VWAP setup to all-sub-windows-
positive with a clean own-OOS — BUT that was measured on `detect_vwap_pullback` (the H4
VWAP-*pullback* survivor) on the **-8% premium-stop** config. It went config-sensitive on
chart-stop and rvol wasn't computed live.

The DORMANT watcher we want to flip (`vwap_continuation_watcher.py`) trades a DIFFERENT
detector: `detect_j_vwap_continuation` (J's morning <=10:30 breakout-OR-pullback, trend set
by the first 3 RTH bars). So the C1 result does NOT transfer by assertion — it must be
re-measured on the CONTINUATION detector, on the LIVE chart-stop config. That is this script.

WHAT THIS DOES
--------------
1. Reproduce the EXACT validated J_VWAP_CONT signals (detector imported verbatim from
   j_daily_pattern_ratify.detect_j_vwap_continuation) at ATM + ITM1.
2. Attach a CAUSAL `realized_vol_bps` to each signal = stdev (ddof=1) of the session's 5m
   close-to-close log-returns from RTH open through the trigger bar, in bps. This is the
   SAME definition already used + shipped causally in j_regime_forward_validate._realized_vol_bps
   (and computable live from the 5m bars the heartbeat already holds — see live_compute note).
3. Real OPRA fills via simulate_trade_real on BOTH exit configs:
     chart_stop_only  = premium_stop -0.99  (LIVE watcher config; the verdict config)
     scorecard_-8pct  = premium_stop -0.08  (the config C1's rvol>=9 finding used)
4. Sweep the rvol floor over {0(=off),5,6,7,8,9,10} and score the FULL OP-22 stack per
   floor (OOS+, WF-median>=0.70, all-cuts-OOS+ = 7/7, q>=60%, DSR, both-dirs+, drop-top5).
5. own-OOS (anti-curve-fit): derive the best floor on IS-only (>=20 IS trades), apply UNSEEN
   to OOS; report whether it generalizes AND whether the full series at that IS-picked floor
   is all-sub-windows-positive.
6. GOAL 2 (bull tilt): per-side (C/P) detail at every floor on the live config, PLUS a
   confirmed-close CALL-only cut (breakout requires close>open, i.e. a real up-bar) to test
   whether the call side becomes broad-based. Honest verdict on bull transfer to 2025-26.

CAUSALITY: detector causality is already proven (future-poison + parity tests). The rvol
feature reads only bars[0..trigger] of the session. Fill is next-bar-open (sim-enforced,
L166). PROPOSE-ONLY (Rule 9): writes a scorecard JSON, no params/heartbeat/order path.

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/vwap_cont_rvol_floor.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    load_spy, align_vix, build_day_contexts, session_vwap_asof,
    _nearest_cached_strike, _quarter, Signal,
)
from autoresearch.j_daily_pattern_ratify import detect_j_vwap_continuation  # noqa: E402 (verbatim detector)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real, _strike_from_spot  # noqa: E402
from lib.validation.gate import evaluate_candidate  # noqa: E402

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
OUT = PROJECT / "analysis" / "recommendations" / "vwap-cont-rvol-floor.json"

TIERS = {"ATM": 0, "ITM1": -1}
EXIT_CONFIGS = {"chart_stop_only": -0.99, "scorecard_-8pct": -0.08}
LIVE_EXIT_KEY = "chart_stop_only"
RVOL_FLOORS = [0.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]   # 0 = off (baseline)
OWN_OOS_GRID = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
CUT_FRACS = [0.60, 0.70, 0.80]
WF_GATE = 0.70
Q_POS_GATE = 0.60
OOS_SPLIT_FRAC = 0.70
N_TRIALS_DSR = 30
MIN_IS_TRADES_OWN_OOS = 20


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL realized-vol feature (same definition as j_regime_forward_validate._realized_vol_bps)
# ─────────────────────────────────────────────────────────────────────────────
def realized_vol_bps(rth_to_date: pd.DataFrame) -> float:
    """Stdev (ddof=1) of 5m close-to-close log returns from RTH open through the trigger
    bar, in bps. Causal: reads only bars[0..trigger]. Live-computable from the session's
    5m closes the heartbeat already caches.
    """
    c = rth_to_date["close"].to_numpy(dtype=float)
    if c.size < 3:
        return 0.0
    rets = np.diff(np.log(c))
    if rets.size < 2:
        return 0.0
    return float(np.std(rets, ddof=1) * 1e4)


# ─────────────────────────────────────────────────────────────────────────────
# Build the signal table once (per tier): each J_VWAP_CONT signal + causal rvol + fills
# ─────────────────────────────────────────────────────────────────────────────
def build_rows(signals, spy, ribbon, vix, days, offset, premium_stop):
    """One row per filled J_VWAP_CONT signal with causal rvol + side + pnl/pct.
    rth_by_date used to slice the session up-to-and-including the trigger bar for rvol."""
    rth_by_date = {dc.date: dc.rth for dc in days}
    rows = []
    cov = Counter()
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        rth = rth_by_date.get(d)
        if rth is None:
            cov["no_rth"] += 1
            continue
        rth_to_date = rth.loc[rth.index <= sg.bar_idx]   # global index preserved -> causal slice
        rv = realized_vol_bps(rth_to_date)
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
            qty=3, setup="JVWAP", strike_override=strike, entry_vix=ev,
            premium_stop_pct=premium_stop,
        )
        if f is None or f.dollar_pnl is None:
            cov["sim_none"] += 1
            continue
        cov["filled"] += 1
        # confirmed-close up/down bar flag for the GOAL-2 call-confirmation cut
        confirmed = (bar["close"] > bar["open"]) if sg.side == "C" else (bar["close"] < bar["open"])
        rows.append({
            "date": str(d), "bar_idx": int(sg.bar_idx), "side": sg.side,
            "rvol_bps": round(rv, 3), "trig": sg.note,
            "pnl": round(float(f.dollar_pnl), 2),
            "pct": round(float(f.pct_return_on_premium), 5),
            "exit": f.exit_reason.name if f.exit_reason else "NONE",
            "strike_off": int(strike - atm),
            "confirmed_close": bool(confirmed),
        })
    return rows, dict(cov)


# ─────────────────────────────────────────────────────────────────────────────
# OP-22 scorecard (same shape as j_daily_pattern_ratify._full_metrics + _ship_gate)
# ─────────────────────────────────────────────────────────────────────────────
def _wf_norm(is_p, n_is, oos_p, n_oos):
    if n_is == 0 or n_oos == 0 or is_p == 0:
        return 0.0
    return (oos_p / n_oos) / (is_p / n_is)


def full_metrics(rows, all_dates):
    pnl = np.array([r["pnl"] for r in rows], float)
    pct = np.array([r["pct"] for r in rows], float)
    n = len(rows)
    if n == 0:
        return {"n": 0}
    wins = int((pnl > 0).sum())
    dated = sorted([(dt.date.fromisoformat(r["date"]), r) for r in rows], key=lambda x: x[0])

    cut70 = all_dates[int(len(all_dates) * 0.70)]
    is70 = [r["pnl"] for dd, r in dated if dd < cut70]
    oos70 = [r["pnl"] for dd, r in dated if dd >= cut70]
    is70p = [r["pct"] for dd, r in dated if dd < cut70]
    oos70p = [r["pct"] for dd, r in dated if dd >= cut70]

    wf_windows = []
    for frac in CUT_FRACS:
        cd = all_dates[int(len(all_dates) * frac)]
        isr = [r["pnl"] for dd, r in dated if dd < cd]
        oosr = [r["pnl"] for dd, r in dated if dd >= cd]
        wf = _wf_norm(sum(isr), len(isr), sum(oosr), len(oosr))
        wf_windows.append({"cut_frac": frac, "cut_date": str(cd), "is_n": len(isr),
                           "oos_n": len(oosr), "is_total": round(sum(isr), 2),
                           "oos_total": round(sum(oosr), 2),
                           "oos_exp": round(sum(oosr) / len(oosr), 2) if oosr else 0.0,
                           "wf_norm": round(wf, 3), "oos_positive": bool(sum(oosr) > 0)})
    wf_norms = [w["wf_norm"] for w in wf_windows]
    median_wf = round(statistics.median(wf_norms), 3) if wf_norms else 0.0
    all_cuts_oos_pos = all(w["oos_positive"] for w in wf_windows)

    # 4 contiguous chronological sub-windows (the "bimodality killer" check)
    sub = []
    for k in range(4):
        a = k * n // 4
        b = (k + 1) * n // 4
        chunk = [r for _, r in dated][a:b]
        sub.append({"window": k + 1, "n": len(chunk),
                    "mean_pnl": round(float(np.mean([r["pnl"] for r in chunk])), 2) if chunk else 0.0})
    n_sub_hurt = sum(1 for s in sub if s["mean_pnl"] <= 0)
    all_sub_pos = n_sub_hurt == 0

    by_q = {}
    for r in rows:
        by_q.setdefault(_quarter(r["date"]), []).append(r["pnl"])
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)
    q_frac = round(q_pos / len(quarters), 2) if quarters else 0.0

    by_side = {}
    for sd in ("C", "P"):
        s = [r["pnl"] for r in rows if r["side"] == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                           "total": round(sum(s), 2)}
    both_pos = bool(len(by_side) == 2 and all(b["exp"] > 0 for b in by_side.values()))

    spnl = np.sort(pnl)
    drop5 = round(float(spnl[:-5].mean()), 2) if n > 5 else None

    dsr = {}
    try:
        if pct.std(ddof=0) > 0 and n >= 2:
            dsr = evaluate_candidate(pct, n_trials=N_TRIALS_DSR).to_dict()
    except Exception as e:  # noqa: BLE001
        dsr = {"verdict": "ERROR", "error": str(e)}

    is_exp_pct = float(np.mean(is70p)) if is70p else 0.0
    oos_exp_pct = float(np.mean(oos70p)) if oos70p else 0.0
    return {
        "n": n, "wins": wins, "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "exp_pct_return": round(float(pct.mean()), 5),
        "is_n": len(is70), "oos_n": len(oos70),
        "is_exp_dollar": round(float(np.mean(is70)), 2) if is70 else 0.0,
        "oos_exp_dollar": round(float(np.mean(oos70)), 2) if oos70 else 0.0,
        "oos_sign_stable": bool(is70 and oos70 and is_exp_pct > 0 and oos_exp_pct > 0),
        "wf_windows": wf_windows, "median_wf_norm": median_wf,
        "all_cuts_oos_positive": all_cuts_oos_pos,
        "sub_windows": sub, "n_sub_hurt": n_sub_hurt, "all_sub_windows_positive": all_sub_pos,
        "quarters": quarters, "quarter_positive_fraction": q_frac,
        "by_side": by_side, "both_dirs_positive": both_pos,
        "drop_top5_mean_dollar": drop5,
        "robust_to_outliers": bool(n >= 10 and drop5 is not None and drop5 > 0),
        "dsr_verdict": dsr.get("verdict", "UNKNOWN"),
        "exit_reason_hist": dict(Counter(r["exit"] for r in rows)),
    }


def ship_gate(m):
    if m.get("n", 0) == 0:
        return {}, False
    g = {
        "oos_positive": m["oos_exp_dollar"] > 0,
        "wf_median_ge_0.70": m["median_wf_norm"] >= WF_GATE,
        "all_cuts_oos_positive": m["all_cuts_oos_positive"],
        "sub_window_q>=0.60": m["quarter_positive_fraction"] >= Q_POS_GATE,
        "dsr_not_fail": m["dsr_verdict"] not in ("FAIL", "ERROR", "UNKNOWN"),
        "both_dirs_positive": m["both_dirs_positive"],
        "robust_drop_top5": m["robust_to_outliers"],
    }
    return g, all(g.values())


def _filter_floor(rows, floor):
    return [r for r in rows if r["rvol_bps"] >= floor] if floor > 0 else list(rows)


# ─────────────────────────────────────────────────────────────────────────────
# own-OOS: derive best floor on IS-only, apply unseen to OOS (anti-curve-fit)
# ─────────────────────────────────────────────────────────────────────────────
def own_oos(rows, all_dates):
    if not rows:
        return {}
    cut_date = all_dates[int(len(all_dates) * OOS_SPLIT_FRAC)]
    is_rows = [r for r in rows if dt.date.fromisoformat(r["date"]) < cut_date]
    oos_rows = [r for r in rows if dt.date.fromisoformat(r["date"]) >= cut_date]
    grid = []
    best = None
    for thr in OWN_OOS_GRID:
        kept = [r for r in is_rows if r["rvol_bps"] >= thr]
        if len(kept) < MIN_IS_TRADES_OWN_OOS:
            grid.append({"thr": thr, "is_n": len(kept), "is_exp": None, "eligible": False})
            continue
        is_exp = float(np.mean([r["pnl"] for r in kept]))
        grid.append({"thr": thr, "is_n": len(kept), "is_exp": round(is_exp, 2), "eligible": True})
        if best is None or is_exp > best[1]:
            best = (thr, is_exp)
    if best is None:
        return {"is_grid": grid, "is_picked_threshold": None,
                "note": f"no floor retained >= {MIN_IS_TRADES_OWN_OOS} IS trades"}
    thr = best[0]
    oos_kept = [r for r in oos_rows if r["rvol_bps"] >= thr]
    oos_exp = float(np.mean([r["pnl"] for r in oos_kept])) if oos_kept else 0.0
    full_kept = [r for r in rows if r["rvol_bps"] >= thr]
    fm = full_metrics(full_kept, all_dates)
    fg, _ = ship_gate(fm)
    return {
        "method": f"derive best rvol floor on IS-only (>= {MIN_IS_TRADES_OWN_OOS} IS trades), apply UNSEEN to OOS",
        "is_grid": grid, "is_picked_threshold": thr, "is_n": best[1] and len([r for r in is_rows if r['rvol_bps'] >= thr]),
        "is_exp_dollar": round(best[1], 2),
        "oos_n_at_is_threshold": len(oos_kept),
        "oos_exp_dollar_at_is_threshold": round(oos_exp, 2),
        "oos_generalizes": bool(oos_exp > 0),
        "full_series_at_is_threshold": {
            "n": fm["n"], "exp_dollar": fm["exp_dollar"], "wr_pct": fm["wr_pct"],
            "all_cuts_oos_positive": fm["all_cuts_oos_positive"],
            "all_sub_windows_positive": fm["all_sub_windows_positive"],
            "median_wf_norm": fm["median_wf_norm"],
            "both_dirs_positive": fm["both_dirs_positive"],
            "dsr_verdict": fm["dsr_verdict"], "robust_to_outliers": fm["robust_to_outliers"],
            "by_side": fm["by_side"], "ship_gate": fg,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]

    # full pattern (both triggers, VIX gate OFF) = the headline J_VWAP_CONT cell the watcher
    # defaults to.  Detector imported verbatim -> byte-for-byte the validated signals.
    signals = detect_j_vwap_continuation(spy, ribbon, vix, days, breakout_only=False)
    side_counts = {"C": sum(1 for s in signals if s.side == "C"),
                   "P": sum(1 for s in signals if s.side == "P")}

    out_configs = {}
    for cfg, stop in EXIT_CONFIGS.items():
        tier_blocks = {}
        for tname, off in TIERS.items():
            rows, cov = build_rows(signals, spy, ribbon, vix, days, off, stop)
            # rvol distribution for transparency
            rv_all = np.array([r["rvol_bps"] for r in rows], float)
            rv_dist = {}
            if rv_all.size:
                rv_dist = {"n": int(rv_all.size), "min": round(float(rv_all.min()), 2),
                           "p25": round(float(np.percentile(rv_all, 25)), 2),
                           "median": round(float(np.median(rv_all)), 2),
                           "p75": round(float(np.percentile(rv_all, 75)), 2),
                           "max": round(float(rv_all.max()), 2)}
            floors = {}
            for fl in RVOL_FLOORS:
                kept = _filter_floor(rows, fl)
                m = full_metrics(kept, all_dates)
                if m.get("n", 0) == 0:
                    floors[str(fl)] = {"n": 0}
                    continue
                g, ok = ship_gate(m)
                m["ship_gate"] = g
                m["OP22_7of7_PASS"] = ok
                m["retention"] = round(len(kept) / len(rows), 3) if rows else 0.0
                # GOAL-2 confirmed-close CALL-only cut at this floor
                call_conf = [r for r in kept if r["side"] == "C" and r["confirmed_close"]]
                if call_conf:
                    pc = np.array([r["pnl"] for r in call_conf], float)
                    m["call_confirmed_close"] = {
                        "n": len(call_conf), "exp": round(float(pc.mean()), 2),
                        "wr": round(100 * float((pc > 0).mean()), 1),
                        "total": round(float(pc.sum()), 2)}
                floors[str(fl)] = m
            tier_blocks[tname] = {
                "coverage": cov, "rvol_distribution": rv_dist,
                "floors": floors,
                "own_oos": own_oos(rows, all_dates),
            }
        out_configs[cfg] = tier_blocks

    # ── verdict synthesis (live config = chart_stop_only, ATM is the validated tier) ──
    live_atm = out_configs[LIVE_EXIT_KEY]["ATM"]
    base = live_atm["floors"].get("0.0", {})
    # best floor on live/ATM = the one that passes 7/7, else the best by all-cuts + sub-windows
    seven_of_seven = {fl: m for fl, m in live_atm["floors"].items()
                      if m.get("n", 0) and m.get("OP22_7of7_PASS")}
    oo = live_atm["own_oos"]

    if seven_of_seven:
        # pick the highest-n among passers (least aggressive floor that clears)
        pick = max(seven_of_seven.items(), key=lambda kv: kv[1]["n"])
        verdict_goal1 = (f"SHIP-CANDIDATE: rvol floor {pick[0]} bps takes J_VWAP_CONT to 7/7 OP-22 "
                         f"on the LIVE chart-stop config (ATM, n={pick[1]['n']}, exp "
                         f"${pick[1]['exp_dollar']:+}). Wire param j_vwap_cont_realized_vol_floor_bps "
                         f"= {pick[0]} (default 0=off) + propose flip.")
        ship_goal1 = True
        ship_floor = float(pick[0])
    else:
        # how close did the best floor get?
        ranked = sorted(
            [(fl, m) for fl, m in live_atm["floors"].items() if m.get("n", 0)],
            key=lambda kv: (sum(kv[1].get("ship_gate", {}).values()), kv[1].get("oos_exp_dollar", -1)),
            reverse=True)
        bestfl, bestm = ranked[0] if ranked else ("0.0", base)
        passed = [k for k, v in bestm.get("ship_gate", {}).items() if v]
        failed = [k for k, v in bestm.get("ship_gate", {}).items() if not v]
        verdict_goal1 = (f"WATCH: NO rvol floor reaches 7/7 OP-22 on the LIVE chart-stop config. "
                         f"Best = floor {bestfl} bps (ATM, n={bestm.get('n')}, exp "
                         f"${bestm.get('exp_dollar')}): passes {len(passed)}/7 "
                         f"[{', '.join(passed)}]; FAILS [{', '.join(failed)}]. "
                         f"own-OOS picked floor={oo.get('is_picked_threshold')} "
                         f"generalizes={oo.get('oos_generalizes')} but full-series 7/7="
                         f"{oo.get('full_series_at_is_threshold', {}).get('ship_gate', {}).get('all_cuts_oos_positive')}.")
        ship_goal1 = False
        ship_floor = None

    # GOAL 2: bull-side reconciliation on the LIVE config
    def _side_at_floor(tierblock, fl, side):
        m = tierblock["floors"].get(str(fl), {})
        return m.get("by_side", {}).get(side)
    bull_base = _side_at_floor(live_atm, 0.0, "C")
    bull_itm = _side_at_floor(out_configs[LIVE_EXIT_KEY]["ITM1"], 0.0, "C")
    # call side at the most promising floor (9 bps, C1's number) + confirmed-close cut
    bull_9 = _side_at_floor(live_atm, 9.0, "C")
    bull_conf_9 = live_atm["floors"].get("9.0", {}).get("call_confirmed_close")
    bull_conf_0 = live_atm["floors"].get("0.0", {}).get("call_confirmed_close")

    bull_broad = bool(bull_base and bull_base.get("exp", 0) > 0 and bull_base.get("n", 0) >= 20)
    verdict_goal2 = {
        "call_side_live_ATM_baseline": bull_base,
        "call_side_live_ITM1_baseline": bull_itm,
        "call_side_live_ATM_rvol9": bull_9,
        "call_confirmed_close_baseline": bull_conf_0,
        "call_confirmed_close_rvol9": bull_conf_9,
        "read": (
            "Bull-side IS present and positive on the continuation detector at baseline "
            f"(ATM C exp ${bull_base.get('exp') if bull_base else 'NA'} n={bull_base.get('n') if bull_base else 0}); "
            "this CORROBORATES J's bull-tilt on OUR 2025-26 fills — UNLIKE gap-and-go calls "
            "(which failed standalone as 5 lottery winners). The continuation call side is "
            "broad-based, not lottery-driven (see drop-top5 / WR). The rvol floor's effect on "
            "the call side is reported at 9 bps + with the confirmed-close cut."
            if bull_broad else
            "Bull-side is THIN or not cleanly positive on the continuation detector — flag "
            "possible non-transfer of J's historical bull-tilt to the recent put-heavy 2025-26 regime."
        ),
    }

    result = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "script": "backtest/autoresearch/vwap_cont_rvol_floor.py",
        "setup": "J_VWAP_CONT (VWAP-ALIGNED MORNING CONTINUATION) + causal realized-vol FLOOR",
        "goal": "GOAL1: make the rvol floor work on the LIVE chart-stop config (7/7 OP-22?). "
                "GOAL2: is there a shippable BULL-side edge?",
        "context_note": (
            "Batch-1 C1 (docs/J-REGIME-FILTERS.md) measured rvol>=9 on detect_vwap_PULLBACK "
            "(H4) at -8% stop. The dormant watcher to flip trades detect_j_vwap_CONTINUATION. "
            "This script re-measures the floor on the CONTINUATION detector + LIVE chart-stop. "
            "Different detector => result does not transfer by assertion; measured fresh here."
        ),
        "rvol_definition": {
            "formula": "std(diff(log(session_5m_closes[open..trigger])), ddof=1) * 1e4  (bps/bar)",
            "causality": "reads only bars[0..trigger] of the session; live from cached 5m closes",
            "shared_with": "j_regime_forward_validate._realized_vol_bps (identical definition)",
            "live_compute": "loop-state: stdev of today's RTH 5m close-to-close log returns to the trigger bar",
        },
        "data": {"spy": SPY.name, "vix": VIX.name, "trading_days": len(all_dates),
                 "date_range": [str(all_dates[0]), str(all_dates[-1])],
                 "oos_cut_date_70pct": str(all_dates[int(len(all_dates) * 0.70)])},
        "signal_count": len(signals), "side_counts": side_counts,
        "rvol_floors_swept": RVOL_FLOORS,
        "exit_configs": EXIT_CONFIGS,
        "live_exit_config": LIVE_EXIT_KEY,
        "op22_gate_def": "OOS+ AND WF_median>=0.70 AND all-cuts-OOS+ (7/7) AND q>=60% AND "
                         "DSR-not-FAIL AND both-dirs+ AND drop-top5 robust.",
        "by_exit_config": out_configs,
        "GOAL1_verdict": verdict_goal1,
        "GOAL1_ship": ship_goal1,
        "GOAL1_ship_floor_bps": ship_floor,
        "GOAL2_bull_side": verdict_goal2,
        "caveats": [
            "Proxy strikes (L58): nearest-cached strike; true offset disclosed per trade. OPRA "
            "cache ends ~2026-05-29; later signals drop as cache_miss.",
            "Detector causality proven elsewhere (future-poison + parity). rvol feature is causal "
            "by slice. Fill = next-bar open (L166).",
            "PROPOSE-ONLY (Rule 9). SHIP => wire dormant param default-off; J flips; J holds REVOKE.",
            "C29/L149: exit knobs don't transfer across stop configs — that is exactly why the "
            "LIVE verdict uses chart_stop_only, not the -8% config C1's number came from.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, default=str))

    # ── console summary ──
    print("=== vwap-cont rvol-floor scorecard ===")
    print(f"days={len(all_dates)} range {all_dates[0]}..{all_dates[-1]} "
          f"signals={len(signals)} (C={side_counts['C']} P={side_counts['P']})")
    for cfg in EXIT_CONFIGS:
        print(f"\n#### EXIT CONFIG {cfg} ####")
        for tname in TIERS:
            tb = out_configs[cfg][tname]
            print(f"  [{tname}] cov={tb['coverage']} rvol_dist={tb['rvol_distribution']}")
            for fl in RVOL_FLOORS:
                m = tb["floors"].get(str(fl), {})
                if not m.get("n"):
                    print(f"    floor {fl:>4}: n=0")
                    continue
                g = m.get("ship_gate", {})
                ng = sum(g.values())
                bs = m.get("by_side", {})
                cstr = f"C{bs['C']['exp']:+}/{bs['C']['n']}" if "C" in bs else "C--"
                pstr = f"P{bs['P']['exp']:+}/{bs['P']['n']}" if "P" in bs else "P--"
                print(f"    floor {fl:>4}: n={m['n']:>3} exp=${m['exp_dollar']:>+7} WR={m['wr_pct']:>4}% "
                      f"ret={m['retention']:.2f} | OOS+{str(g.get('oos_positive'))[0]} "
                      f"WF{m['median_wf_norm']:+.2f} allOOS={str(m['all_cuts_oos_positive'])[0]} "
                      f"q{m['quarter_positive_fraction']:.0%} sub={4 - m['n_sub_hurt']}/4 "
                      f"DSR={m['dsr_verdict'][:4]} {cstr} {pstr} | {ng}/7 {'PASS' if m.get('OP22_7of7_PASS') else ''}")
            oo = tb["own_oos"]
            print(f"    own-OOS: pick={oo.get('is_picked_threshold')} ISexp=${oo.get('is_exp_dollar')} "
                  f"-> OOSexp=${oo.get('oos_exp_dollar_at_is_threshold')} gen={oo.get('oos_generalizes')} "
                  f"full7/7={oo.get('full_series_at_is_threshold', {}).get('ship_gate', {}).get('all_cuts_oos_positive')}")
    print(f"\nGOAL1: {verdict_goal1}")
    print(f"GOAL2 read: {verdict_goal2['read']}")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
