"""A5 / A8 / A9 — J's SHARPEST entry CELLS (his data) validated forward on OURS.

Part of the profitability campaign (markdown/research/J-DATA-RESEARCH-MASTER-PLAN.md). Three
sub-angles, one anti-overfit method: his Webull data DEFINES the hypothesis (which
window / trigger / side is sharpest); OUR 2025-26 SPY real-OPRA fills VALIDATE it
forward through the SAME OP-22 stack used by gap_and_go_ratify / j_daily_pattern.

  A5  TIME-OF-DAY specificity   — his WR + size-neutral pct_move per fine window;
        find his edge zone, then RESTRICT the live VWAP-continuation detector to it
        and measure OOS expectancy lift vs the unrestricted baseline (+ freq cost).
  A8  TRIGGER x CONDITION       — cross his trigger (breakout/pullback/reclaim) x
        condition (vwap_aligned / confirmed_close / new_extreme); the sharpest cell;
        validate the cell's structural translation forward.
  A9  CALL vs PUT asymmetry     — split his calls vs puts; per-side optimal window/
        trigger/WR; validate a per-side rule forward (puts = his known weakness).

ANTI-CONFOUND (load-bearing): J's raw $pnl is SIZE-contaminated (his afternoon book
was smaller, his morning 0DTE size was big) — so the per-cell HEADLINE is WR and the
size-neutral pct_move (return on premium per contract), NOT raw $pnl. Raw $pnl is
reported but flagged as size-confounded.

VALIDATION DETECTOR: a parameterized clone of detect_j_vwap_continuation
(j_daily_pattern_ratify) — the closest live-shape match to "the book" (J's dominant
VWAP-aligned morning continuation). Adds: configurable entry_window (start,end ET)
and side_filter (C-only / P-only / both). Everything else (causality, stop, fill
next-bar-open) is identical. Run through the same _full_metrics OP-22 scorecard so
the RESTRICTED variant is comparable cell-for-cell to the unrestricted baseline.

Causal (L166): all features at/before entry-bar close; fill next-bar-open (sim).
Real fills (lib.simulator_real). Pure, $0, read-only, propose-only (Rule 9).

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/j_entry_specificity.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from collections import Counter, defaultdict
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
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real, _strike_from_spot  # noqa: E402
from lib.validation.gate import evaluate_candidate  # noqa: E402

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
J_RECORDS = PROJECT / "analysis" / "webull-j-trades" / "entry_quality.json"
OUT = PROJECT / "analysis" / "recommendations" / "j-entry-specificity.json"

# OP-22 gates (mirror j_daily_pattern_ratify)
TIERS = {"ATM": 0, "ITM1": -1}
CUT_FRACS = [0.60, 0.70, 0.80]
WF_GATE = 0.70
Q_POS_GATE = 0.60
EXIT_STOP = -0.99            # chart-stop only (live config, L51/L55/C2)
FREQ_PER_WK_FLOOR = 2.0

# Detector base params (identical to j_daily_pattern_ratify's translation)
TREND_BARS = 3
SHALLOW_DIP_TOL = 0.0010

# Fine windows for A5 (the master-plan buckets; ET).  (label, start, end_exclusive)
FINE_WINDOWS = [
    ("0935_1000", dt.time(9, 35), dt.time(10, 0)),
    ("1000_1030", dt.time(10, 0), dt.time(10, 30)),
    ("1030_1100", dt.time(10, 30), dt.time(11, 0)),
    ("1100_1130", dt.time(11, 0), dt.time(11, 30)),
    ("1130_1300", dt.time(11, 30), dt.time(13, 0)),
    ("1300_plus", dt.time(13, 0), dt.time(16, 0)),
]


# ─────────────────────────────────────────────────────────────────────────────
# PART A — mine J's data (his cells).  Headline = WR + size-neutral pct_move.
# ─────────────────────────────────────────────────────────────────────────────
def _hhmm_to_time(hhmm: str) -> dt.time:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.time(h, m)


def _fine_window_label(hhmm: str) -> str:
    t = _hhmm_to_time(hhmm)
    for label, s, e in FINE_WINDOWS:
        if s <= t < e:
            return label
    return "pre0935" if t < dt.time(9, 35) else "after1600"


def _cell_stats(recs: list[dict]) -> dict:
    """WR + size-neutral pct_move (mean) + raw $pnl (size-confounded, flagged)."""
    n = len(recs)
    if n == 0:
        return {"n": 0}
    wins = sum(1 for r in recs if r["is_win"])
    pct = [r["pct_move"] for r in recs]              # return on premium per contract
    pnl = [r["pnl"] for r in recs]                   # size-confounded
    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "pct_move_mean": round(float(np.mean(pct)), 1),     # size-NEUTRAL headline
        "pct_move_median": round(float(np.median(pct)), 1),
        "raw_pnl_mean_SIZE_CONFOUNDED": round(float(np.mean(pnl)), 1),
        "raw_pnl_total_SIZE_CONFOUNDED": round(float(np.sum(pnl)), 0),
    }


def mine_j_data() -> dict:
    recs = json.loads(J_RECORDS.read_text(encoding="utf-8"))["records"]
    overall = _cell_stats(recs)

    # --- A5: time-of-day (fine windows), all + 0DTE-only (his closest analog) ---
    def by_window(subset):
        d = defaultdict(list)
        for r in subset:
            d[_fine_window_label(r["entry_hhmm"])].append(r)
        order = [w[0] for w in FINE_WINDOWS] + ["pre0935", "after1600"]
        return {w: _cell_stats(d[w]) for w in order if d[w]}

    a5_all = by_window(recs)
    a5_0dte = by_window([r for r in recs if r["is_0dte"]])
    # rank fine windows by pct_move headline (size-neutral), min n>=15
    rankable = [(w, s) for w, s in a5_all.items() if s["n"] >= 15]
    a5_ranked = sorted(rankable, key=lambda kv: kv[1]["pct_move_mean"], reverse=True)
    a5_sharpest = a5_ranked[0][0] if a5_ranked else None

    # --- A8: trigger x condition cells ---
    triggers = ["breakout", "pullback", "reclaim"]
    conditions = {
        "vwap_aligned": lambda r: r["vwap_aligned"] is True,
        "confirmed_close": lambda r: r["confirmed_close"] is True,
        "new_session_extreme": lambda r: r["new_session_extreme"] is True,
    }
    a8 = {}
    for trig in triggers:
        trig_recs = [r for r in recs if r["trigger"] == trig]
        cell = {"_all": _cell_stats(trig_recs)}
        for cname, pred in conditions.items():
            cell[cname] = _cell_stats([r for r in trig_recs if pred(r)])
        # the sharp double-cell: trigger & vwap_aligned & confirmed_close
        cell["aligned_AND_confirmed"] = _cell_stats(
            [r for r in trig_recs if r["vwap_aligned"] and r["confirmed_close"]])
        a8[trig] = cell
    # rank all (trigger, aligned&confirmed) cells with n>=15 by pct_move
    a8_cells = [(f"{t}|aligned&confirmed", a8[t]["aligned_AND_confirmed"])
                for t in triggers if a8[t]["aligned_AND_confirmed"].get("n", 0) >= 15]
    a8_cells += [(f"{t}|all", a8[t]["_all"])
                 for t in triggers if a8[t]["_all"].get("n", 0) >= 15]
    a8_ranked = sorted(a8_cells, key=lambda kv: kv[1]["pct_move_mean"], reverse=True)
    a8_sharpest = a8_ranked[0][0] if a8_ranked else None

    # --- A9: call vs put asymmetry ---
    def side_profile(side):
        s = [r for r in recs if r["side"] == side]
        prof = {"overall": _cell_stats(s),
                "by_window": by_window(s),
                "by_trigger": {t: _cell_stats([r for r in s if r["trigger"] == t])
                               for t in triggers},
                "aligned": _cell_stats([r for r in s if r["vwap_aligned"]]),
                "counter": _cell_stats([r for r in s if not r["vwap_aligned"]]),
                "confirmed": _cell_stats([r for r in s if r["confirmed_close"]]),
                "unconfirmed": _cell_stats([r for r in s if not r["confirmed_close"]])}
        # sharpest window for this side (n>=10, pct_move)
        w = [(k, v) for k, v in prof["by_window"].items() if v["n"] >= 10]
        prof["sharpest_window"] = (sorted(w, key=lambda kv: kv[1]["pct_move_mean"],
                                          reverse=True)[0][0] if w else None)
        t = [(k, v) for k, v in prof["by_trigger"].items() if v["n"] >= 10]
        prof["sharpest_trigger"] = (sorted(t, key=lambda kv: kv[1]["pct_move_mean"],
                                           reverse=True)[0][0] if t else None)
        return prof

    a9_call = side_profile("C")
    a9_put = side_profile("P")

    return {
        "overall": overall,
        "A5_time_of_day": {"all_trades": a5_all, "zero_dte_only": a5_0dte,
                           "ranked_by_pct_move_n>=15": [{"window": w, **s}
                                                        for w, s in a5_ranked],
                           "sharpest_window": a5_sharpest},
        "A8_trigger_x_condition": {"cells": a8,
                                   "ranked_by_pct_move_n>=15": [{"cell": c, **s}
                                                               for c, s in a8_ranked],
                                   "sharpest_cell": a8_sharpest},
        "A9_call_vs_put": {"call": a9_call, "put": a9_put},
    }


# ─────────────────────────────────────────────────────────────────────────────
# PART B — validate forward on OUR data.  Parameterized VWAP-continuation detector.
# ─────────────────────────────────────────────────────────────────────────────
def detect_j_cont_param(spy_df, ribbon_df, vix, days, *,
                        win_start: dt.time, win_end: dt.time,
                        side_filter: str = "both",
                        breakout_only: bool = False) -> list[Signal]:
    """Clone of detect_j_vwap_continuation with a configurable entry WINDOW + side.

    Identical causality / stop / one-per-day logic; the ONLY changes are:
      * entry allowed only when win_start <= bar_time < win_end (A5 window restrict),
      * side_filter in {"both","C","P"} (A9 per-side restrict).
    side from first TREND_BARS closes one side of VWAP; entry = first in-window bar
    that prints a fresh in-trend extreme (breakout) OR closes back on trend side
    after a VWAP-ward dip (pullback). Stop = session extreme against the trade.
    """
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            continue
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        # trend side from first TREND_BARS
        hc, hv = closes[:TREND_BARS], vwap[:TREND_BARS]
        if len(hc) < TREND_BARS:
            continue
        if np.all(hc > hv):
            side = "C"
        elif np.all(hc < hv):
            side = "P"
        else:
            continue
        if side_filter != "both" and side != side_filter:
            continue
        for j in range(TREND_BARS, len(rth)):
            tj = times[j]
            if tj >= win_end:
                break
            if tj < win_start:
                continue
            v = vwap[j]
            if v <= 0:
                continue
            if side == "C":
                prior_ext = float(np.max(highs[:j])) if j > 0 else highs[j]
                breakout = highs[j] >= prior_ext and closes[j] > v
                dip = lows[j] <= v * (1 + SHALLOW_DIP_TOL) and closes[j] > v
                stop = float(np.min(lows[:j + 1]))
            else:
                prior_ext = float(np.min(lows[:j])) if j > 0 else lows[j]
                breakout = lows[j] <= prior_ext and closes[j] < v
                dip = highs[j] >= v * (1 - SHALLOW_DIP_TOL) and closes[j] < v
                stop = float(np.max(highs[:j + 1]))
            trig = "breakout" if breakout else ("pullback" if dip else None)
            if breakout_only:
                trig = "breakout" if breakout else None
            if trig is None:
                continue
            out.append(Signal(bar_idx=int(idxs[j]), side=side, stop_level=stop,
                              note=f"jcont_{trig}"))
            break
    return out


def _sim(signals, spy, vix, ribbon, offset):
    rows, cov = [], Counter()
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
            qty=3, setup="JSPEC", strike_override=strike, entry_vix=ev,
            premium_stop_pct=EXIT_STOP,
        )
        if f is None or f.dollar_pnl is None:
            cov["sim_none"] += 1
            continue
        cov["filled"] += 1
        rows.append({"date": str(d), "side": sg.side,
                     "pnl": round(float(f.dollar_pnl), 2),
                     "pct": round(float(f.pct_return_on_premium), 5),
                     "exit": f.exit_reason.name if f.exit_reason else "NONE",
                     "trig": sg.note})
    return rows, dict(cov)


def _wf_norm(is_p, n_is, oos_p, n_oos):
    if n_is == 0 or n_oos == 0 or is_p == 0:
        return 0.0
    return (oos_p / n_oos) / (is_p / n_is)


def _full_metrics(rows, all_dates, n_days, n_trials_dsr):
    pnl = np.array([r["pnl"] for r in rows], float)
    pct = np.array([r["pct"] for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    dated = sorted([(dt.date.fromisoformat(r["date"]), r) for r in rows],
                   key=lambda x: x[0])
    fire_days = len({r["date"] for r in rows})

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
                           "wf_norm": round(wf, 3),
                           "oos_positive": bool(sum(oosr) > 0)})
    wf_norms = [w["wf_norm"] for w in wf_windows]
    median_wf = round(statistics.median(wf_norms), 3) if wf_norms else 0.0
    all_oos_pos = all(w["oos_positive"] for w in wf_windows)

    by_q = {}
    for r in rows:
        by_q.setdefault(_quarter(r["date"]), []).append(r["pnl"])
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2),
                    "total": round(sum(v), 2)} for q, v in sorted(by_q.items())}
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
    gross_wins = float(pnl[pnl > 0].sum())
    top5_share = round(float(spnl[-5:].sum()) / gross_wins, 3) if gross_wins > 0 else 0.0

    dsr = {}
    try:
        if pct.std(ddof=0) > 0 and n >= 2:
            dsr = evaluate_candidate(pct, n_trials=n_trials_dsr).to_dict()
    except Exception as e:  # noqa: BLE001
        dsr = {"verdict": "ERROR", "error": str(e)}

    is_exp_pct = float(np.mean(is70p)) if is70p else 0.0
    oos_exp_pct = float(np.mean(oos70p)) if oos70p else 0.0
    weeks = n_days / 5.0
    return {
        "n": n, "wins": wins, "wr_pct": round(100 * wins / n, 1) if n else 0.0,
        "exp_dollar": round(float(pnl.mean()), 2) if n else 0.0,
        "total_dollar": round(float(pnl.sum()), 2),
        "exp_pct_return": round(float(pct.mean()), 5) if n else 0.0,
        "fire_days": fire_days, "trading_days": n_days,
        "fire_day_pct": round(100 * fire_days / n_days, 1) if n_days else 0.0,
        "trades_per_week": round(n / weeks, 2) if weeks else 0.0,
        "is_n": len(is70), "oos_n": len(oos70),
        "is_exp_dollar": round(float(np.mean(is70)), 2) if is70 else 0.0,
        "oos_exp_dollar": round(float(np.mean(oos70)), 2) if oos70 else 0.0,
        "is_exp_pct": round(is_exp_pct, 5), "oos_exp_pct": round(oos_exp_pct, 5),
        "oos_sign_stable": bool(is70 and oos70 and is_exp_pct > 0 and oos_exp_pct > 0),
        "wf_windows": wf_windows, "median_wf_norm": median_wf,
        "all_cuts_oos_positive": all_oos_pos,
        "quarters": quarters, "quarter_positive_fraction": q_frac,
        "by_side": by_side, "both_dirs_positive": both_pos,
        "drop_top5_mean_dollar": drop5,
        "top5_winner_share_of_gross_wins": top5_share,
        "robust_to_outliers": bool(n >= 10 and drop5 is not None and drop5 > 0),
        "dsr": dsr, "dsr_verdict": dsr.get("verdict", "UNKNOWN"),
        "exit_reason_hist": dict(Counter(r["exit"] for r in rows)),
    }


def _ship_gate(m):
    g = {
        "oos_positive": m["oos_exp_dollar"] > 0,
        "wf_median_ge_0.70": m["median_wf_norm"] >= WF_GATE,
        "all_cuts_oos_positive": m["all_cuts_oos_positive"],
        "sub_window_stable_q>=0.60": m["quarter_positive_fraction"] >= Q_POS_GATE,
        "dsr_not_fail": m["dsr_verdict"] not in ("FAIL", "ERROR", "UNKNOWN"),
        "robust_drop_top5": m["robust_to_outliers"],
    }
    # both-dirs only required when the variant trades both sides
    if m["by_side"] and len(m["by_side"]) == 2:
        g["both_dirs_positive"] = m["both_dirs_positive"]
    return g, all(g.values())


def _run_variant(name, desc, spy, vix, ribbon, days, all_dates, n_days,
                 n_trials_dsr, **detect_kw):
    signals = detect_j_cont_param(spy, ribbon, vix, days, **detect_kw)
    side_counts = {"C": sum(1 for s in signals if s.side == "C"),
                   "P": sum(1 for s in signals if s.side == "P")}
    tiers = {}
    for tname, off in TIERS.items():
        rows, cov = _sim(signals, spy, vix, ribbon, off)
        m = _full_metrics(rows, all_dates, n_days, n_trials_dsr)
        m["coverage"] = cov
        gate, ok = _ship_gate(m)
        m["ship_gate"] = gate
        m["edge_ship_pass"] = ok
        m["freq_pass_>=2/wk"] = m["trades_per_week"] >= FREQ_PER_WK_FLOOR
        m["DAILY_SURVIVOR"] = bool(ok and m["freq_pass_>=2/wk"])
        tiers[tname] = m
    return {"name": name, "description": desc,
            "window": [str(detect_kw["win_start"]), str(detect_kw["win_end"])],
            "side_filter": detect_kw.get("side_filter", "both"),
            "breakout_only": detect_kw.get("breakout_only", False),
            "signal_count": len(signals), "side_counts": side_counts, "tiers": tiers}


def _verdict_for(restricted_atm, base_atm):
    """SHIP/WATCH/DEAD for a restricted variant vs the unrestricted baseline.

    SHIP   = clears full OP-22 edge gate AND fires >=2/wk AND OOS expectancy lifts
             vs the unrestricted baseline (the restriction adds value).
    WATCH  = +EV & OOS-sign-stable & DSR-PASS & OOS lift, but fails a strict gate
             (typically all-cuts-OOS or freq) — promising, OOS-thin.
    DEAD   = no OOS lift OR not +EV — the restriction does not transfer.
    """
    lift = restricted_atm["oos_exp_dollar"] - base_atm["oos_exp_dollar"]
    if restricted_atm["DAILY_SURVIVOR"] and lift > 0:
        return "SHIP", round(lift, 2)
    if (restricted_atm["exp_dollar"] > 0 and restricted_atm["oos_sign_stable"]
            and restricted_atm["dsr_verdict"] == "PASS" and lift > 0):
        return "WATCH", round(lift, 2)
    return "DEAD", round(lift, 2)


def main() -> int:
    print("=== A5/A8/A9 — J entry specificity ===")
    print("PART A: mining J's Webull cells (WR + size-neutral pct_move)...")
    j = mine_j_data()
    print(f"  J overall: n={j['overall']['n']} WR={j['overall']['wr_pct']}% "
          f"pct_move_mean={j['overall']['pct_move_mean']}%")
    print(f"  A5 sharpest window: {j['A5_time_of_day']['sharpest_window']}")
    print(f"  A8 sharpest cell:   {j['A8_trigger_x_condition']['sharpest_cell']}")
    print(f"  A9 call sharpest win/trig: {j['A9_call_vs_put']['call']['sharpest_window']}"
          f" / {j['A9_call_vs_put']['call']['sharpest_trigger']}")
    print(f"  A9 put  sharpest win/trig: {j['A9_call_vs_put']['put']['sharpest_window']}"
          f" / {j['A9_call_vs_put']['put']['sharpest_trigger']}")

    print("\nPART B: loading OUR 2025-26 SPY/VIX + real-fills validation...")
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    n_days = len(all_dates)
    print(f"  trading_days={n_days} range {all_dates[0]}..{all_dates[-1]}")

    # The full morning band is the unrestricted BASELINE (matches j_daily_pattern's
    # <=10:30 default, expressed as a window for apples-to-apples comparison).
    FULL_MORNING = (dt.time(9, 35), dt.time(10, 30))

    variants = []
    n_trials = 18  # A5(3) + A8(2) + A9(3) windows x ~2 tiers — conservative DSR haircut

    # ---- A5: restrict to J's edge zone vs full morning baseline ----
    variants.append(_run_variant(
        "A5_baseline_full_morning",
        "Unrestricted morning VWAP-continuation (9:35-10:30) — the comparison baseline.",
        spy, vix, ribbon, days, all_dates, n_days, n_trials,
        win_start=FULL_MORNING[0], win_end=FULL_MORNING[1]))
    # J's data says afternoon (esp 11:00 / 13:00) is his sharp WR/pct zone, but the
    # live detector's structure is a MORNING-trend-established continuation; the
    # tradeable A5 lever is tightening WITHIN the morning to his sharpest morning
    # sub-band (10:00-10:30 was his least-bad morning cell). Test both the tight
    # early sub-band and an extended-to-midday window.
    variants.append(_run_variant(
        "A5_tight_1000_1030",
        "Restrict morning continuation to 10:00-10:30 (J's least-negative morning "
        "sub-band; later setups had a confirmed trend).",
        spy, vix, ribbon, days, all_dates, n_days, n_trials,
        win_start=dt.time(10, 0), win_end=dt.time(10, 30)))
    variants.append(_run_variant(
        "A5_extend_to_1300",
        "Extend the window to 13:00 to capture J's sharpest absolute cells "
        "(11:00 +$29/72%WR, 13:00 +$69/73%WR on HIS data).",
        spy, vix, ribbon, days, all_dates, n_days, n_trials,
        win_start=dt.time(9, 35), win_end=dt.time(13, 0)))

    # ---- A8: trigger x condition — his sharpest cell is breakout-dominant ----
    variants.append(_run_variant(
        "A8_breakout_only_morning",
        "Restrict to BREAKOUT trigger only (J's highest-WR/pct trigger cell, "
        "breakout & aligned & confirmed) in the morning band.",
        spy, vix, ribbon, days, all_dates, n_days, n_trials,
        win_start=FULL_MORNING[0], win_end=FULL_MORNING[1], breakout_only=True))

    # ---- A9: per-side rule ----
    variants.append(_run_variant(
        "A9_call_only_morning",
        "CALL side only (J's structurally stronger side) — morning band.",
        spy, vix, ribbon, days, all_dates, n_days, n_trials,
        win_start=FULL_MORNING[0], win_end=FULL_MORNING[1], side_filter="C"))
    variants.append(_run_variant(
        "A9_put_only_morning",
        "PUT side only (J's known weakness) — morning band. Tests whether puts are "
        "structurally worse on OUR data too.",
        spy, vix, ribbon, days, all_dates, n_days, n_trials,
        win_start=FULL_MORNING[0], win_end=FULL_MORNING[1], side_filter="P"))

    by_name = {v["name"]: v for v in variants}
    base_atm = by_name["A5_baseline_full_morning"]["tiers"]["ATM"]

    # sub-angle verdicts (ATM tier headline; restriction must LIFT OOS vs baseline)
    sub_verdicts = {}
    for key, vname in [("A5", "A5_tight_1000_1030"), ("A5_extend", "A5_extend_to_1300"),
                       ("A8", "A8_breakout_only_morning"),
                       ("A9_call", "A9_call_only_morning"),
                       ("A9_put", "A9_put_only_morning")]:
        v, lift = _verdict_for(by_name[vname]["tiers"]["ATM"], base_atm)
        sub_verdicts[key] = {"variant": vname, "verdict": v,
                             "oos_exp_lift_vs_baseline_dollar": lift}

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "campaign": "J-DATA profitability — A5 (time-of-day) / A8 (trigger x condition) "
                    "/ A9 (call vs put). markdown/research/J-DATA-RESEARCH-MASTER-PLAN.md",
        "method": (
            "His Webull data (analysis/webull-j-trades/entry_quality.json, 655 closed "
            "round-trips 2021-23) DEFINES the sharpest cell per angle. OUR 2025-26 SPY "
            "real-OPRA fills VALIDATE forward via a parameterized clone of "
            "detect_j_vwap_continuation through the SAME OP-22 _full_metrics scorecard "
            "as gap_and_go_ratify / j_daily_pattern_ratify. A restriction SHIPS only if "
            "it clears the edge gate, fires >=2/wk, AND LIFTS OOS expectancy vs the "
            "unrestricted morning baseline."),
        "anti_confound_note": (
            "J's per-cell HEADLINE is WR and size-neutral pct_move (return on premium per "
            "contract); raw $pnl is reported but flagged SIZE_CONFOUNDED (his afternoon "
            "book was smaller, morning 0DTE size larger — raw $ mixes edge with sizing)."),
        "causality": "all features at/before entry-bar close; fill next-bar-open (sim, "
                     "L166). VWAP-to-date cumulative same-session. Chart-stop only "
                     "(premium_stop=-0.99, live config).",
        "data": {"spy": SPY.name, "vix": VIX.name, "trading_days": n_days,
                 "date_range": [str(all_dates[0]), str(all_dates[-1])]},
        "edge_ship_bar": "OP-22: OOS+ AND WF_median>=0.70 AND all-cuts-OOS+ AND q>=60% "
                         "AND DSR not-FAIL AND drop-top5 robust (+ both-dirs+ when both "
                         "sides trade) AND fires >=2/wk AND OOS lift vs baseline.",
        "PART_A_j_data": j,
        "PART_B_our_data_validation": {"variants": variants,
                                       "baseline_variant": "A5_baseline_full_morning"},
        "SUB_ANGLE_VERDICTS": sub_verdicts,
        "caveats": [
            "Proxy strikes (L58): nearest-cached strike used; OPRA cache ends ~2026-05-29 "
            "(later signals = cache_miss).",
            "His-data WR absolutes are winner-date-biased UP (loser-only dates missing "
            "from the bar cache); the per-cell CONTRASTS (which window/trigger/side is "
            "sharper) are bias-robust because subsets share dates. pct_move is the "
            "size-neutral cross-check.",
            "The live detector structure is a MORNING trend-established continuation; J's "
            "sharpest ABSOLUTE cells are afternoon (11:00/13:00) — those can't be a pure "
            "window-tighten of this morning detector, so the A5_extend variant tests the "
            "window stretch directly rather than assuming transfer.",
            "Propose-only (Rule 9). Any SHIP => dormant/WATCH_ONLY wiring; OP-21 live gate "
            "(3 live J confirmations) still stands; J holds REVOKE.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print("\n=== PART B variants (ATM tier) ===")
    for v in variants:
        m = v["tiers"]["ATM"]
        print(f"[{v['name']}] sig={v['signal_count']} (C={v['side_counts']['C']} "
              f"P={v['side_counts']['P']}) n={m['n']} exp=${m['exp_dollar']:+.1f} "
              f"WR={m['wr_pct']}% | {m['trades_per_week']}/wk fires {m['fire_day_pct']}% "
              f"| OOSexp=${m['oos_exp_dollar']:+.1f} stable={m['oos_sign_stable']} "
              f"medWF={m['median_wf_norm']:+.3f} allOOS+={m['all_cuts_oos_positive']} "
              f"q+={m['quarter_positive_fraction']:.0%} DSR={m['dsr_verdict']} "
              f"SURV={m['DAILY_SURVIVOR']}")
    print("\n=== SUB-ANGLE VERDICTS (vs full-morning baseline) ===")
    for k, sv in sub_verdicts.items():
        print(f"  {k}: {sv['verdict']}  (OOS lift ${sv['oos_exp_lift_vs_baseline_dollar']:+.1f} "
              f"via {sv['variant']})")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
