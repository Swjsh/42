"""FOCUSED re-score of the premium-selling pivot leaders (fast subset of the full grid).

The full 900-cell grid is cold-cache expensive (~700 CPU-s). The full run already
established the leaders are all IC (iron condor) off2/w2/pt0.5 across entry times, with
positive OOS expectancy + high WR + tail-survivable. This script re-scores ONLY that
leader neighbourhood with the FIXED posQ (monthly OOS sub-windows, was unreachable
calendar-quarter), adds the recency-OOS chop-window breakout, and prints the gate verdict.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_pivot_premium_selling_focus.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from dataclasses import asdict
from pathlib import Path

_HERE = Path(__file__).resolve()
_BT = _HERE.parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

import _pivot_premium_selling as piv  # noqa: E402

OOS_START = piv.OOS_2026_START

# Leader neighbourhood from the full run (IC off2 w2 pt0.5, all entries + mgmt) + a few
# off3 and pt0.25 controls + the best PCS/CCS/IB for contrast.
FOCUS = [
    ("IC", dt.time(9, 40), 2, 2, 0.5, 2.0),
    ("IC", dt.time(9, 40), 2, 2, 0.5, None),
    ("IC", dt.time(10, 30), 2, 2, 0.5, 1.5),
    ("IC", dt.time(10, 30), 2, 2, 0.5, 2.0),
    ("IC", dt.time(10, 30), 2, 2, 0.5, None),
    ("IC", dt.time(11, 0), 2, 2, 0.5, 1.5),
    ("IC", dt.time(11, 0), 2, 2, 0.5, None),
    ("IC", dt.time(10, 30), 2, 2, 0.25, None),
    ("IC", dt.time(10, 30), 3, 2, 0.5, None),
    ("IC", dt.time(13, 0), 2, 2, 0.5, None),
    ("PCS", dt.time(10, 30), 2, 2, 0.5, None),
    ("CCS", dt.time(10, 30), 2, 2, 0.5, None),
    ("IB", dt.time(10, 30), 0, 2, 0.5, None),
]


def recency_oos(fills, n=25):
    taken = [f for f in fills if not f.skipped]
    oos = sorted([f for f in taken if dt.date.fromisoformat(f.date) >= OOS_START],
                 key=lambda x: x.date)
    rec = oos[-n:]
    pnls = [f.realized_pnl for f in rec]
    return len(rec), (statistics.mean(pnls) if pnls else 0.0), (min(pnls) if pnls else 0.0)


def main():
    spy = piv._load_spy_master()
    cache_dates = piv._option_cache_dates()
    day_list = sorted(cache_dates & set(spy["date"].unique()))
    print(f"[focus] days={len(day_list)} ({day_list[0]}..{day_list[-1]})\n")

    rows = []
    for (structure, et, off, wing, pt, stop) in FOCUS:
        fills = piv.run_variant(structure, et, off, wing, pt, stop, spy, day_list)
        vs = piv.score_variant(structure, et, off, wing, pt, stop, fills)
        rn, rexp, rworst = recency_oos(fills)
        d = asdict(vs)
        d["recency_oos_n"] = rn
        d["recency_oos_exp"] = round(rexp, 2)
        d["recency_oos_worst"] = round(rworst, 2)
        rows.append(d)
        sm = "EOD" if stop is None else f"{stop}x"
        print(f"{structure:4} {et.strftime('%H:%M')} off{off} w{wing} pt{pt} {sm:4} | "
              f"n={vs.n:3} skip={vs.skip_rate:.2f} WR={vs.wr:.2f} "
              f"exp=${vs.expectancy:6.1f} OOSexp=${vs.expectancy_oos:6.1f}(n{vs.n_oos}) "
              f"posQ={vs.posq_oos}/6 IS25=${vs.expectancy_is25:6.1f} "
              f"recOOS=${rexp:6.1f}(n{rn}) maxDayL=${vs.max_single_day_loss:7.0f} "
              f"bookDD=${vs.book_max_dd:7.0f} dWorst5=${vs.drop_worst5_expectancy:6.1f} "
              f"tail={str(vs.tail_survivable)[:1]} GATE={str(vs.gate_pass)[:1]}")

    out = piv.OUT_DIR / "focus_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(rows, fh, indent=2, default=str)
    print(f"\n[focus] wrote {out}")


if __name__ == "__main__":
    main()
