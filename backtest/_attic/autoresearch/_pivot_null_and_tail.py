"""PIVOT premium-selling: random-entry/random-strike NULL test (L172) + tail analysis.

Companion to _pivot_premium_selling.py. Answers the gate's beats-null requirement:
is the BEST cell's edge in the STRUCTURE/selection, or is it generic theta that any
condor at any time harvests? We build a null distribution by running the SAME best
structure with RANDOMIZED entry time + RANDOMIZED short_offset per day, many seeds,
and compare the real cell's OOS expectancy against the null mean +/- spread.

Also reports, for the best cell, the full kill-switch tail accounting in DOLLARS at
the sizes Gamma actually trades (Safe -30%/$600/day, Bold -50%/$835/day).

Pure python, $0, offline cache only.
"""
from __future__ import annotations

import datetime as dt
import random
import statistics
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BT = _HERE.parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

from autoresearch import _pivot_premium_selling as P  # noqa: E402

OOS_START = P.OOS_2026_START


def _oos_exp(fills):
    p = [f.realized_pnl for f in fills
         if not f.skipped and dt.date.fromisoformat(f.date) >= OOS_START]
    return (statistics.mean(p) if p else 0.0), len(p)


def run_null(structure, wing_width, pt_frac, stop_mult, spy, days, seeds=40):
    """Null: each day, pick a RANDOM entry time and RANDOM short_offset from the grid.
    Returns the distribution of OOS per-trade expectancies across seeds."""
    null_exps = []
    for s in range(seeds):
        rng = random.Random(1000 + s)
        fills = []
        for d in days:
            spy_day = spy[spy["date"] == d]
            if spy_day.empty:
                continue
            et = rng.choice(P.ENTRY_TIMES_ET)
            off = rng.choice(P.SHORT_OFFSETS)
            decision_dt, spot, _ = P._spot_and_decision(spy_day, et)
            if decision_dt is None or spot is None or spot <= 0:
                continue
            legs = P._build_variant_legs(structure, spot, off, wing_width)
            from lib.multileg_structures import legs_in_band
            from lib import simulator_credit as sc
            if not legs_in_band(legs, spot, half_width=5):
                continue
            binding = wing_width + (1 if structure == "BWIC" else 0)
            f = sc.simulate_credit_trade(d, legs, decision_dt, spot, wing_width=binding,
                                         structure_name=structure, contracts=1,
                                         pt_frac=pt_frac, stop_mult=stop_mult,
                                         commission_per_contract=0.65)
            fills.append(f)
        e, n = _oos_exp(fills)
        if n >= 20:
            null_exps.append(e)
    return null_exps


def main():
    spy = P._load_spy_master()
    days = sorted(P._option_cache_dates() & set(spy["date"].unique()))

    # BEST cell from results: IC 10:30 off2 w2 pt0.5 stop1.5x
    best = dict(structure="IC", entry_time=dt.time(10, 30), short_offset=2,
                wing_width=2, pt_frac=0.5, stop_mult=1.5)
    print(f"[null] BEST cell = {best}")
    fills = P.run_variant(best["structure"], best["entry_time"], best["short_offset"],
                          best["wing_width"], best["pt_frac"], best["stop_mult"], spy, days)
    real_oos_exp, real_n = _oos_exp(fills)
    print(f"[null] REAL best-cell OOS exp/trade = ${real_oos_exp:.2f} (n={real_n})")

    null = run_null(best["structure"], best["wing_width"], best["pt_frac"],
                    best["stop_mult"], spy, days, seeds=40)
    if null:
        nm, nsd = statistics.mean(null), (statistics.pstdev(null) if len(null) > 1 else 0.0)
        pctile = sum(1 for x in null if x < real_oos_exp) / len(null)
        print(f"[null] NULL (random entry+offset, same IC) OOS exp: "
              f"mean=${nm:.2f} sd=${nsd:.2f} n_seeds={len(null)}")
        print(f"[null] real - null_mean = ${real_oos_exp - nm:.2f}; "
              f"real beats {pctile*100:.0f}% of null seeds")
        print(f"[null] VERDICT beats-null: {real_oos_exp > nm + nsd}")
    else:
        print("[null] null produced no valid seeds (band too tight)")

    # ---- Tail accounting in kill-switch dollars ----
    taken = [f for f in fills if not f.skipped]
    pnls = [f.realized_pnl for f in taken]
    oos = [f for f in taken if dt.date.fromisoformat(f.date) >= OOS_START]
    oos_pnls = [f.realized_pnl for f in oos]
    worst = sorted(pnls)[:5]
    worst_oos = sorted(oos_pnls)[:5]
    maxloss_1lot = min(pnls)
    print(f"\n[tail] per 1-lot (wing=$2 => max-loss-defined ~= ${200 - statistics.mean([f.net_credit for f in taken]):.0f}):")
    print(f"[tail] worst 5 single days (all): {[round(x) for x in worst]}")
    print(f"[tail] worst 5 single days (OOS): {[round(x) for x in worst_oos]}")
    print(f"[tail] max single-day loss 1-lot = ${maxloss_1lot:.0f}")
    # how many lots fit the kill switch? Safe -$600/day, Bold -$835/day
    if maxloss_1lot < 0:
        safe_lots = int(600 / abs(maxloss_1lot))
        bold_lots = int(835 / abs(maxloss_1lot))
        print(f"[tail] lots before a single worst-day breaches kill: Safe={safe_lots}, Bold={bold_lots}")
    # drop-worst-5 expectancy (steamroller-removed)
    dw5 = statistics.mean(sorted(pnls)[5:]) if len(pnls) > 5 else 0.0
    dw5_oos = statistics.mean(sorted(oos_pnls)[5:]) if len(oos_pnls) > 5 else 0.0
    print(f"[tail] expectancy drop-WORST-5 (all)=${dw5:.2f} (OOS)=${dw5_oos:.2f}")
    # share of total OOS losses concentrated in worst-5 days
    tot_loss = sum(p for p in oos_pnls if p < 0)
    w5_loss = sum(worst_oos)
    if tot_loss < 0:
        print(f"[tail] worst-5 OOS days = {w5_loss/tot_loss*100:.0f}% of all OOS losses")


if __name__ == "__main__":
    main()
