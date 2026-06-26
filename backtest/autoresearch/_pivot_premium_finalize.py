"""PIVOT premium-selling FINALIZER — gate-6 null + monthly posQ + scorecard inputs.

The grid sweep (_pivot_premium_selling.py --full) already wrote 900 scored variants
to _state/pivot_premium_selling/results.json. Two gate components were NOT computable
from that summary file:

  (G6) BEATS-RANDOM null (L172): is the IC edge in the STRUCTURE/strike-selection, or
       is it generic theta any condor harvests? We re-run the BEST cells with (a) the
       real selection and (b) random-strike / random-entry-time controls, same days.
  (posQ /6) the grid used CALENDAR QUARTERS (2026 spans only Q1+Q2 -> max posQ=2, so
       the posQ>=4 gate was STRUCTURALLY unreachable). The spec intends 6 sub-windows;
       we recompute posQ over 6 MONTHLY OOS sub-windows (Jan..Jun 2026) here.

This re-runs only a handful of TOP cells (cheap), reusing run_variant/score machinery.
Pure offline, $0. Writes _state/pivot_premium_selling/finalize.json.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import statistics
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BT = _HERE.parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

from lib import simulator_credit as sc                       # noqa: E402
from lib.multileg_structures import build_legs, legs_in_band, Leg  # noqa: E402
import _pivot_premium_selling as P                            # noqa: E402

OUT = _BT / "autoresearch" / "_state" / "pivot_premium_selling" / "finalize.json"
OOS_START = dt.date(2026, 1, 1)
RECENCY_N = 25
RANDOM_SEED = 13


def _month_key(d: dt.date) -> str:
    return f"{d.year}-{d.month:02d}"


def _expc(xs):
    return statistics.mean(xs) if xs else 0.0


def _drop_top(xs, n):
    return sorted(xs, reverse=True)[n:] if len(xs) > n else []


def _drop_worst(xs, n):
    return sorted(xs)[n:] if len(xs) > n else []


def _book_dd(dated):
    eq = peak = mdd = 0.0
    for _, p in sorted(dated, key=lambda x: x[0]):
        eq += p
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return mdd


def run_real(structure, entry_time, off, wing, pt, stop, spy, days, commission=0.65):
    """Real selection — returns list[(date, pnl)] for TAKEN trades only."""
    out = []
    for d in days:
        spy_day = spy[spy["date"] == d]
        if spy_day.empty:
            continue
        decision_dt, spot, _ = P._spot_and_decision(spy_day, entry_time)
        if decision_dt is None or spot is None or spot <= 0:
            continue
        legs = P._build_variant_legs(structure, spot, off, wing)
        if not legs_in_band(legs, spot, half_width=5):
            continue
        binding = wing + (1 if structure == "BWIC" else 0)
        f = sc.simulate_credit_trade(d, legs, decision_dt, spot, wing_width=binding,
                                     structure_name=structure, contracts=1, pt_frac=pt,
                                     stop_mult=stop, commission_per_contract=commission)
        if not f.skipped:
            out.append((d, f.realized_pnl))
    return out


def run_random_strike(structure, entry_time, wing, pt, stop, spy, days, rng, commission=0.65):
    """NULL-A: random short-offset in {2,3,4} each day (same structure/entry/wing/mgmt)."""
    out = []
    for d in days:
        spy_day = spy[spy["date"] == d]
        if spy_day.empty:
            continue
        decision_dt, spot, _ = P._spot_and_decision(spy_day, entry_time)
        if decision_dt is None or spot is None or spot <= 0:
            continue
        off = rng.choice([2, 3, 4])
        legs = P._build_variant_legs(structure, spot, off, wing)
        if not legs_in_band(legs, spot, half_width=5):
            continue
        binding = wing + (1 if structure == "BWIC" else 0)
        f = sc.simulate_credit_trade(d, legs, decision_dt, spot, wing_width=binding,
                                     structure_name=structure, contracts=1, pt_frac=pt,
                                     stop_mult=stop, commission_per_contract=commission)
        if not f.skipped:
            out.append((d, f.realized_pnl))
    return out


def run_random_entry(structure, off, wing, pt, stop, spy, days, rng, commission=0.65):
    """NULL-B: random entry-time each day from the grid (same structure/offset/wing/mgmt)."""
    times = P.ENTRY_TIMES_ET
    out = []
    for d in days:
        spy_day = spy[spy["date"] == d]
        if spy_day.empty:
            continue
        et = rng.choice(times)
        decision_dt, spot, _ = P._spot_and_decision(spy_day, et)
        if decision_dt is None or spot is None or spot <= 0:
            continue
        legs = P._build_variant_legs(structure, spot, off, wing)
        if not legs_in_band(legs, spot, half_width=5):
            continue
        binding = wing + (1 if structure == "BWIC" else 0)
        f = sc.simulate_credit_trade(d, legs, decision_dt, spot, wing_width=binding,
                                     structure_name=structure, contracts=1, pt_frac=pt,
                                     stop_mult=stop, commission_per_contract=commission)
        if not f.skipped:
            out.append((d, f.realized_pnl))
    return out


def summarize(dated, label):
    pnls = [p for _, p in dated]
    oos = [(d, p) for d, p in dated if d >= OOS_START]
    oos_pnls = [p for _, p in oos]
    by_m = {}
    for d, p in oos:
        by_m.setdefault(_month_key(d), []).append(p)
    posq6 = sum(1 for v in by_m.values() if _expc(v) > 0)
    recency = sorted(dated, key=lambda x: x[0])[-RECENCY_N:]
    rec_pnls = [p for _, p in recency]
    return {
        "label": label, "n": len(pnls), "n_oos": len(oos_pnls),
        "expectancy": round(_expc(pnls), 2),
        "expectancy_oos": round(_expc(oos_pnls), 2),
        "wr": round(sum(1 for p in pnls if p > 0) / len(pnls), 3) if pnls else 0.0,
        "wr_oos": round(sum(1 for p in oos_pnls if p > 0) / len(oos_pnls), 3) if oos_pnls else 0.0,
        "posq6_oos": posq6, "n_oos_months": len(by_m),
        "recency_n": len(rec_pnls), "recency_expectancy": round(_expc(rec_pnls), 2),
        "max_single_day_loss": round(min(pnls), 2) if pnls else 0.0,
        "book_max_dd": round(_book_dd(dated), 2),
        "drop_top5_expectancy": round(_expc(_drop_top(pnls, 5)), 2),
        "drop_worst5_expectancy": round(_expc(_drop_worst(pnls, 5)), 2),
        "oos_drop_top5_expectancy": round(_expc(_drop_top(oos_pnls, 5)), 2),
        "oos_drop_worst5_expectancy": round(_expc(_drop_worst(oos_pnls, 5)), 2),
        "total_pnl": round(sum(pnls), 2),
    }


def main():
    spy = P._load_spy_master()
    cache_dates = P._option_cache_dates()
    days = sorted(cache_dates & set(spy["date"].unique()))
    print(f"[finalize] days={len(days)} ({days[0]}..{days[-1]})")

    # Top cells to finalize (the OOS-leaders; offset-2/wing-2 IC family + a stop variant).
    cells = [
        ("IC", dt.time(10, 30), 2, 2, 0.5, None),
        ("IC", dt.time(10, 30), 2, 2, 0.5, 1.5),
        ("IC", dt.time(9, 40), 2, 2, 0.5, 2.0),
        ("IC", dt.time(11, 0), 2, 2, 0.5, 1.5),
    ]

    report = []
    for (struct, et, off, wing, pt, stop) in cells:
        real = run_real(struct, et, off, wing, pt, stop, spy, days)
        real_sum = summarize(real, "REAL")

        # Null distributions: 30 random-strike + 30 random-entry seeds.
        rng = random.Random(RANDOM_SEED)
        rs_oos, re_oos = [], []
        for _ in range(30):
            rs = run_random_strike(struct, et, wing, pt, stop, spy, days, rng)
            rs_oos.append(_expc([p for d, p in rs if d >= OOS_START]))
            rei = run_random_entry(struct, off, wing, pt, stop, spy, days, rng)
            re_oos.append(_expc([p for d, p in rei if d >= OOS_START]))

        real_oos = real_sum["expectancy_oos"]
        rs_mean, re_mean = _expc(rs_oos), _expc(re_oos)
        rs_p95 = sorted(rs_oos)[int(0.95 * len(rs_oos))]
        re_p95 = sorted(re_oos)[int(0.95 * len(re_oos))]
        # "Beats null" = real OOS expectancy strictly above the 95th pct of the null dist.
        beats_strike = real_oos > rs_p95
        beats_entry = real_oos > re_p95
        beats_null = beats_strike and beats_entry

        cell = {
            "cell": f"{struct} {et.strftime('%H:%M')} off{off} w{wing} pt{pt} stop{stop}",
            "real": real_sum,
            "null_strike_oos_mean": round(rs_mean, 2),
            "null_strike_oos_p95": round(rs_p95, 2),
            "null_entry_oos_mean": round(re_mean, 2),
            "null_entry_oos_p95": round(re_p95, 2),
            "real_oos_expectancy": real_oos,
            "beats_random_strike": beats_strike,
            "beats_random_entry": beats_entry,
            "beats_null": beats_null,
        }
        report.append(cell)
        print(f"\n{cell['cell']}")
        print(f"  REAL: n={real_sum['n']} nOOS={real_sum['n_oos']} OOSexp=${real_oos} "
              f"WR={real_sum['wr_oos']} posQ6={real_sum['posq6_oos']}/{real_sum['n_oos_months']} "
              f"rec=${real_sum['recency_expectancy']} dWorst5=${real_sum['drop_worst5_expectancy']} "
              f"maxDayL=${real_sum['max_single_day_loss']} bookDD=${real_sum['book_max_dd']}")
        print(f"  NULL strike: mean=${rs_mean:.2f} p95=${rs_p95:.2f}  entry: mean=${re_mean:.2f} p95=${re_p95:.2f}")
        print(f"  BEATS NULL: strike={beats_strike} entry={beats_entry} -> {beats_null}")

    OUT.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n[finalize] wrote {OUT}")


if __name__ == "__main__":
    main()
