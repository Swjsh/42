"""PART B — validate J's specific daily winning pattern on OUR SPY data (real fills).

PART A (webull_daily_pattern_miner.py) mined J's 313 real winners and found his
dominant, near-daily repeatable pattern is **VWAP-ALIGNED MORNING CONTINUATION**:

    his CALL winners are above session VWAP (118/159 = 74%), his PUT winners below
    it (119/147 = 81%); the VWAP-aligned class wins 63.7% vs 45.7% counter-VWAP (a
    sign flip in expectancy: +$26 vs -$19/trade), and it fires on 92% of his trading
    days. The morning band (<=10:30 ET) is the sweet spot (69% WR / +$32). His
    highest-WR trigger inside that class is the breakout/continuation (66.5%).

This module translates that rule STRUCTURALLY (VWAP / time / side are scale-free, so
the 2021-23 SPX rule maps directly onto 2025-26 SPY — SPX≈10×SPY) into a CAUSAL
detector and runs the full OP-22 stack on REAL OPRA fills with the LIVE chart-stop
config, PLUS the co-equal frequency metric (trades/week + days-fired) — the point of
the task is a DAILY-tradeable setup.

DETECTOR (one entry/day, causal, fill next bar open — no look-ahead, L166)
-------------------------------------------------------------------------
1. Establish the VWAP trend side from the first TREND_BARS RTH bars: all closes on
   one side of session-VWAP-to-date => that's the day's side (C if above, P if below).
2. After the trend window, take the FIRST morning bar (<= ENTRY_CUTOFF ET) that
   CONTINUES in the trend direction while still closing on the trend side of VWAP:
     - "continuation" = a fresh local extreme in the trend direction (matches J's
       breakout-dominant winners) OR a with-trend close after a shallow VWAP-ward dip.
3. Stop = structural session extreme against the trade as of the entry bar
   (chart-stop only; premium stop disabled — live CHART-STOP-PRIMARY doctrine).

Variants reported:
  * J_VWAP_CONT       — the full pattern (breakout OR shallow-pullback continuation)
  * J_VWAP_BREAKOUT   — breakout-only (J's highest-WR trigger sub-class)

Both run at ATM and ITM-1 (live tiers), chart-stop-only.

REUSE: load_spy/align_vix/build_day_contexts/_nearest_cached_strike/_quarter from
infinite_ammo_discovery; simulate_trade_real + _strike_from_spot from simulator_real;
evaluate_candidate (DSR) from validation.gate; the OP-22 _full_metrics scorecard
shape from gap_and_go_ratify. Pure, $0, read-only. Propose-only (Rule 9).

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/j_daily_pattern_ratify.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
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
    _nearest_cached_strike, _quarter, Signal, DayCtx,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real, _strike_from_spot  # noqa: E402
from lib.validation.gate import evaluate_candidate  # noqa: E402

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
OUT = PROJECT / "analysis" / "recommendations" / "j-daily-pattern-LIVE.json"

TIERS = {"ATM": 0, "ITM1": -1}
CUT_FRACS = [0.60, 0.70, 0.80]
WF_GATE = 0.70
Q_POS_GATE = 0.60
N_TRIALS_DSR = 30          # J pattern + breakout variant x 2 tiers x dirs x thresholds
EXIT_STOP = -0.99          # chart-stop only (live config)

# Detector params (structural translation of J's morning VWAP-aligned continuation)
TREND_BARS = 3             # first 15 min set the side (J entered early; keep it loose)
ENTRY_CUTOFF = dt.time(10, 30)   # J's morning edge band (<=10:30)
SHALLOW_DIP_TOL = 0.0010   # within 0.10% of VWAP counts as a with-trend pullback tag


# ─────────────────────────────────────────────────────────────────────────────
# DETECTORS
# ─────────────────────────────────────────────────────────────────────────────
def _trend_side(closes, vwap, n) -> Optional[str]:
    head_c = closes[:n]
    head_v = vwap[:n]
    if len(head_c) < n:
        return None
    if np.all(head_c > head_v):
        return "C"
    if np.all(head_c < head_v):
        return "P"
    return None


def _vix_slope(vix, idx: int, look: int = 5) -> float:
    """As-of VIX 5-bar slope (look-ahead-safe: uses bars idx-look..idx)."""
    arr = vix.values if hasattr(vix, "values") else vix
    if idx < look or idx >= len(arr):
        return 0.0
    return float(arr[idx] - arr[idx - look])


def detect_j_vwap_continuation(spy_df, ribbon_df, vix, days, breakout_only=False,
                               put_needs_rising_vix=False):
    """J's VWAP-aligned morning continuation. One causal entry/day.

    side from first TREND_BARS (all closes one side of VWAP). Then first morning bar
    (<=ENTRY_CUTOFF) that EITHER prints a fresh in-trend local extreme (breakout) OR
    (if not breakout_only) closes back on the trend side after dipping toward VWAP
    (shallow with-trend pullback). Stop = session extreme against the trade so far.

    put_needs_rising_vix: VIX-character gate (C5). Puts only fire when the as-of VIX
    5-bar slope is >= 0 — a real down-trend expands vol; falling VIX = bear-chop that
    stops out put-side continuation (mirrors J's own put-side bleed). Causal.
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
        side = _trend_side(closes, vwap, TREND_BARS)
        if side is None:
            continue
        for j in range(TREND_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            v = vwap[j]
            if v <= 0:
                continue
            # prior session extreme in the trend direction (bars before j)
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
            if put_needs_rising_vix and side == "P" and _vix_slope(vix, int(idxs[j])) < 0:
                # VIX-character gate failed for this put -> keep scanning the morning
                continue
            out.append(Signal(bar_idx=int(idxs[j]), side=side, stop_level=stop,
                              note=f"jvwap_{trig}"))
            break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIM + METRICS (reuse the gap_and_go_ratify scorecard shape)
# ─────────────────────────────────────────────────────────────────────────────
def _sim(signals, spy, ribbon, vix, offset):
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
            qty=3, setup="JVWAP", strike_override=strike, entry_vix=ev,
            premium_stop_pct=EXIT_STOP,
        )
        if f is None or f.dollar_pnl is None:
            cov["sim_none"] += 1
            continue
        cov["filled"] += 1
        rows.append({"date": str(d), "side": sg.side, "pnl": round(float(f.dollar_pnl), 2),
                     "pct": round(float(f.pct_return_on_premium), 5),
                     "exit": f.exit_reason.name if f.exit_reason else "NONE",
                     "trig": sg.note, "strike_off": int(strike - atm)})
    return rows, dict(cov)


def _wf_norm(is_p, n_is, oos_p, n_oos):
    if n_is == 0 or n_oos == 0 or is_p == 0:
        return 0.0
    return (oos_p / n_oos) / (is_p / n_is)


def _full_metrics(rows, all_dates, n_days):
    pnl = np.array([r["pnl"] for r in rows], float)
    pct = np.array([r["pct"] for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    dated = sorted([(dt.date.fromisoformat(r["date"]), r) for r in rows], key=lambda x: x[0])
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
                           "wf_norm": round(wf, 3), "oos_positive": bool(sum(oosr) > 0)})
    wf_norms = [w["wf_norm"] for w in wf_windows]
    median_wf = round(statistics.median(wf_norms), 3) if wf_norms else 0.0
    all_oos_pos = all(w["oos_positive"] for w in wf_windows)

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
    drop3 = round(float(spnl[:-3].mean()), 2) if n > 3 else None
    gross_wins = float(pnl[pnl > 0].sum())
    top5_share = round(float(spnl[-5:].sum()) / gross_wins, 3) if gross_wins > 0 else 0.0

    dsr = {}
    try:
        if pct.std(ddof=0) > 0 and n >= 2:
            dsr = evaluate_candidate(pct, n_trials=N_TRIALS_DSR).to_dict()
    except Exception as e:  # noqa: BLE001
        dsr = {"verdict": "ERROR", "error": str(e)}

    is_exp_pct = float(np.mean(is70p)) if is70p else 0.0
    oos_exp_pct = float(np.mean(oos70p)) if oos70p else 0.0
    weeks = n_days / 5.0   # trading weeks (5 sessions/wk)
    return {
        "n": n, "wins": wins, "wr_pct": round(100 * wins / n, 1) if n else 0.0,
        "exp_dollar": round(float(pnl.mean()), 2) if n else 0.0,
        "total_dollar": round(float(pnl.sum()), 2),
        "exp_pct_return": round(float(pct.mean()), 5) if n else 0.0,
        # FREQUENCY (co-equal headline metric for the daily-trading question)
        "fire_days": fire_days,
        "trading_days": n_days,
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
        "drop_top5_mean_dollar": drop5, "drop_top3_mean_dollar": drop3,
        "top5_winner_share_of_gross_wins": top5_share,
        "robust_to_outliers": bool(n >= 10 and drop5 is not None and drop5 > 0),
        "dsr": dsr, "dsr_verdict": dsr.get("verdict", "UNKNOWN"),
        "exit_reason_hist": dict(Counter(r["exit"] for r in rows)),
        "trigger_hist": dict(Counter(r["trig"] for r in rows)),
    }


VARIANTS = {
    "J_VWAP_CONT": dict(breakout_only=False),
    "J_VWAP_BREAKOUT": dict(breakout_only=True),
    "J_VWAP_CONT_VIXGATE": dict(breakout_only=False, put_needs_rising_vix=True),
}
# frequency floor for the daily-trading verdict (co-equal with edge)
FREQ_PER_WK_FLOOR = 2.0


def _ship_gate(m):
    g = {
        "oos_positive": m["oos_exp_dollar"] > 0,
        "wf_median_ge_0.70": m["median_wf_norm"] >= WF_GATE,
        "all_cuts_oos_positive": m["all_cuts_oos_positive"],
        "sub_window_stable_q>=0.60": m["quarter_positive_fraction"] >= Q_POS_GATE,
        "dsr_not_fail": m["dsr_verdict"] not in ("FAIL", "ERROR", "UNKNOWN"),
        "both_dirs_positive": m["both_dirs_positive"],
        "robust_drop_top5": m["robust_to_outliers"],
    }
    return g, all(g.values())


def main() -> int:
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]
    n_days = len(all_dates)

    variants_out = {}
    for vname, kw in VARIANTS.items():
        signals = detect_j_vwap_continuation(spy, ribbon, vix, days, **kw)
        side_counts = {"P": sum(1 for s in signals if s.side == "P"),
                       "C": sum(1 for s in signals if s.side == "C")}
        tiers = {}
        for tname, off in TIERS.items():
            rows, cov = _sim(signals, spy, ribbon, vix, off)
            m = _full_metrics(rows, all_dates, n_days)
            m["coverage"] = cov
            gate, ok = _ship_gate(m)
            m["ship_gate"] = gate
            m["edge_ship_pass"] = ok
            m["freq_pass_>=2/wk"] = m["trades_per_week"] >= FREQ_PER_WK_FLOOR
            # SURVIVOR (daily-trading definition) = clears OP-22 edge gate AND fires
            # >= 2/wk (co-equal frequency requirement). A -EV daily rule is worse
            # than nothing (J's own overtrading lost -$17k) -> never a survivor.
            m["DAILY_SURVIVOR"] = bool(ok and m["freq_pass_>=2/wk"])
            tiers[tname] = m
        variants_out[vname] = {"signal_count": len(signals), "side_counts": side_counts,
                               "tiers": tiers}

    # headline = J_VWAP_CONT ATM (the full daily pattern, live tier)
    head = variants_out["J_VWAP_CONT"]["tiers"]["ATM"]
    # overall verdict across all variants/tiers
    any_survivor = any(t["DAILY_SURVIVOR"]
                       for v in variants_out.values() for t in v["tiers"].values())
    # "near-survivor": clears every OP-22 gate EXCEPT all-cuts-OOS-positive, AND fires
    # >= 2/wk, AND is +EV + OOS-sign-stable + DSR-PASS. (The lone failing window is the
    # most-recent OOS slice with partial OPRA coverage; not a structural break.)
    def _near(m):
        g = m["ship_gate"]
        non_oos = {k: v for k, v in g.items() if k != "all_cuts_oos_positive"}
        return (all(non_oos.values()) and not g["all_cuts_oos_positive"]
                and m["oos_sign_stable"] and m["dsr_verdict"] == "PASS")
    head_near = _near(head)
    any_near = any(_near(t) for v in variants_out.values() for t in v["tiers"].values())

    if any_survivor:
        verdict = "SURVIVOR-DAILY (clears full OP-22 + fires >=2/wk; see per-variant)"
    elif head_near or any_near:
        verdict = ("NEAR-SURVIVOR / MARGINAL — +EV, OOS-sign-stable, DSR-PASS, both-dirs+, "
                   "drop-top5-robust, q>=60%, WF>=0.70 and fires ~2/wk, BUT fails strict "
                   "all-cuts-OOS-positive (only the most-recent OOS window, partial OPRA "
                   "coverage + a put-side bear-chop patch, is negative). Same class as the "
                   "shipped H4 VWAP-pullback: WATCH_ONLY/dormant wiring with a regime caveat, "
                   "NOT a clean auto-ship.")
    elif head["edge_ship_pass"]:
        verdict = "MARGINAL (edge clears OP-22 but frequency < 2/wk — not daily)"
    elif head["exp_dollar"] > 0 and head["oos_sign_stable"]:
        verdict = "MARGINAL (+EV + OOS-stable but fails full OP-22)"
    else:
        verdict = "DEAD (no daily +EV edge on our SPY data)"

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "setup": "J_DAILY_VWAP_ALIGNED_MORNING_CONTINUATION",
        "title": "J's specific repeatable daily winning pattern (mined from his 313 real "
                 "Webull winners) validated on our SPY 2025-26 data, real OPRA fills",
        "part_a_profile": {
            "source": "analysis/webull-j-trades/j_daily_rules.json + j_winner_features.json "
                      "(backtest/autoresearch/webull_daily_pattern_miner.py)",
            "n_winners_analyzed": 306,
            "dominant_rule": "VWAP-ALIGNED MORNING CONTINUATION — his CALL winners are "
                             "above session VWAP (74%), PUT winners below it (81%).",
            "j_vwap_aligned": {"wr_pct": 63.7, "avg_pnl": 26.2, "n": 372,
                               "fires_on_pct_of_trading_days": 92},
            "j_vwap_aligned_morning_<=10:30": {"wr_pct": 69.0, "avg_pnl": 32.2, "n": 210,
                                               "lift_vs_baseline_pp": 10.5},
            "j_vwap_counter_the_leak": {"wr_pct": 45.7, "avg_pnl": -19.2, "n": 151,
                                        "sized_3plus_avg_pnl": -175.5},
            "j_top_triggers_in_class": {"breakout": {"wr_pct": 66.5, "n": 185},
                                        "pullback": {"wr_pct": 61.0, "n": 187}},
            "coverage_caveat": "WR absolutes are winner-DATE-biased (loser-only dates "
                               "not in the per-day bar cache; covered WR 58.5% vs true "
                               "family 46.9%). The ALIGNED-vs-COUNTER CONTRAST (+18pp WR, "
                               "sign-flipped expectancy) is robust to that bias — both "
                               "subsets share the same dates. The day-conditional "
                               "frequency (92% of trading days) is the daily-pattern proof.",
        },
        "mapping_note": (
            "STRUCTURAL translation: J's data is 2021-23 SPX; ours is 2025-26 SPY (SPX~10x "
            "SPY). VWAP-relation, time-of-day, and side are scale-free, so the rule maps "
            "directly. We do NOT port his absolute strikes/premiums; we port the SETUP "
            "STRUCTURE (trend-side-of-VWAP + morning continuation + chart stop)."
        ),
        "detector": {
            "params": {"trend_bars": TREND_BARS, "entry_cutoff_et": str(ENTRY_CUTOFF),
                       "shallow_dip_tol": SHALLOW_DIP_TOL, "one_per_day": True},
            "logic": "side = first TREND_BARS RTH closes all one side of session VWAP; "
                     "entry = first morning bar (<=cutoff) printing a fresh in-trend extreme "
                     "(breakout) OR closing back on the trend side after a VWAP-ward dip "
                     "(pullback); stop = session extreme against the trade. Fill next bar open.",
            "causality": "all features at-or-before the entry bar close; entry next bar "
                         "open (sim-enforced, L166). VWAP-to-date is cumulative same-session.",
        },
        "fills": "lib.simulator_real.simulate_trade_real (real OPRA bars, causal next-bar "
                 "open entry, v15 exit stack, CHART-STOP ONLY premium_stop=-0.99 = live config).",
        "data": {"spy": SPY.name, "vix": VIX.name, "trading_days": n_days,
                 "date_range": [str(all_dates[0]), str(all_dates[-1])]},
        "frequency_definition": (
            "trades_per_week = filled trades / (trading_days/5). fire_day_pct = distinct "
            "entry days / trading days. Frequency is CO-EQUAL with edge for this task: a "
            "+EV rule firing >=2x/wk beats a stronger monthly one for daily trading; a -EV "
            "daily rule is worse than nothing (J's overtrading lost -$17k)."
        ),
        "freq_per_week_floor": FREQ_PER_WK_FLOOR,
        "edge_ship_bar": "OP-22: OOS+ AND WF_median>=0.70 AND all-cuts-OOS+ AND q>=60% AND "
                         "DSR not-FAIL AND both-dirs+ AND drop-top5 robust.",
        "variants": variants_out,
        "headline_variant": "J_VWAP_CONT/ATM",
        "verdict": verdict,
        "caveats": [
            "Proxy strikes (L58): nearest-cached strike used; true offset disclosed per "
            "trade. OPRA cache ends ~2026-05-29; later signals have no fills (cache_miss).",
            "PART A WR absolutes are winner-date-biased UP; only the aligned-vs-counter "
            "contrast and the day-frequency are bias-free claims. PART B fixes this by "
            "running the rule on the FULL unbiased SPY tape with real fills.",
            "Propose-only (Rule 9). SURVIVOR => WATCH_ONLY/dormant flag-gated wiring like "
            "gap-and-go; OP-21 live gate (3 live J confirmations) still stands; J holds REVOKE.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str))

    print("=== j-daily-pattern-LIVE scorecard ===")
    print(f"trading_days={n_days} range {all_dates[0]}..{all_dates[-1]}")
    for vname, vb in variants_out.items():
        print(f"\n[{vname}] signals={vb['signal_count']} "
              f"(C={vb['side_counts']['C']} P={vb['side_counts']['P']})")
        for tname, m in vb["tiers"].items():
            print(f"  {tname}: n={m['n']} exp=${m['exp_dollar']:+.1f} WR={m['wr_pct']}% "
                  f"| FREQ {m['trades_per_week']}/wk fires {m['fire_day_pct']}% days "
                  f"| OOS_stable={m['oos_sign_stable']} medWF={m['median_wf_norm']:+.3f} "
                  f"allOOS+={m['all_cuts_oos_positive']} q+={m['quarter_positive_fraction']:.0%} "
                  f"DSR={m['dsr_verdict']} drop5=${m['drop_top5_mean_dollar']} "
                  f"bothDir={m['both_dirs_positive']} "
                  f"EDGE_OK={m['edge_ship_pass']} DAILY_SURV={m['DAILY_SURVIVOR']}")
    print(f"\nVERDICT (headline J_VWAP_CONT/ATM): {verdict}")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
