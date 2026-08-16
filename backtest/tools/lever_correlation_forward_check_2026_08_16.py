"""FORWARD CHECK on LEVER-CORRELATION-2026-08-06's central claim.

THE FROZEN CLAIM: "concentration is NOT where the loss dollars live" -- 1-arm contract-days
were -$1,896 while 3/4/5-arm were +$1,769/+$238/+$2,350. That slope is what killed every
arm-concurrency cap {1,2,3}. The doc itself flagged "n-small, 26 dates, one 5-arm observation".

It froze 2026-08-06. Ten sessions have happened since, including 2026-08-14 where a FOUR-arm
cluster lost -$1,497 -- the opposite sign from the frozen 4-arm bucket.

METHOD: reuse the frozen `positions_from_scratch()` and `max_concurrent` definitions verbatim
(L251 -- a second implementation would silently disagree). Reproduce the frozen table on the
frozen window FIRST; only if it reproduces is the new-window cut trustworthy.
"""
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve()
REPO = Path("C:/Users/jackw/Desktop/42")
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import lever_correlation_verify_2026_08_06 as frozen  # the FROZEN implementation

FREEZE = "2026-08-06"


def max_concurrent(plist):
    """Verbatim from the frozen verifier: max arms simultaneously holding a contract-day."""
    plist = sorted(plist, key=lambda z: z["entry_ts"])
    best = 0
    for p in plist:
        n = sum(1 for q in plist if q["entry_ts"] <= p["entry_ts"] < q["exit_ts"])
        best = max(best, n)
    return best


def table(positions, label):
    cl = defaultdict(list)
    for p in positions:
        cl[(p["date_et"], p["symbol"])].append(p)
    buckets = defaultdict(lambda: {"cdays": 0, "pos": 0, "pnl": 0.0})
    for (_d, _s), plist in cl.items():
        mc = max_concurrent(plist)
        b = buckets[mc]
        b["cdays"] += 1
        b["pos"] += len(plist)
        b["pnl"] += sum(x["pnl"] for x in plist)
    print(f"\n### {label}")
    print(f"{'max concurrent arms':<22}{'contract-days':>15}{'positions':>11}{'net P&L':>12}")
    tot = 0.0
    for mc in sorted(buckets):
        b = buckets[mc]
        tot += b["pnl"]
        print(f"{mc:<22}{b['cdays']:>15}{b['pos']:>11}{b['pnl']:>12,.2f}")
    print(f"{'TOTAL':<22}{'':>15}{'':>11}{tot:>12,.2f}")
    return buckets


def main() -> int:
    allpos = frozen.positions_from_scratch()
    days = sorted({p["date_et"] for p in allpos})
    print(f"positions reconstructed: {len(allpos)} over {len(days)} dates "
          f"({days[0]} .. {days[-1]})")

    frozen_pos = [p for p in allpos if p["date_et"] <= FREEZE]
    new_pos = [p for p in allpos if p["date_et"] > FREEZE]
    print(f"frozen window (<= {FREEZE}): {len(frozen_pos)} positions")
    print(f"NEW window    (>  {FREEZE}): {len(new_pos)} positions, "
          f"{len({p['date_et'] for p in new_pos})} sessions")

    fb = table(frozen_pos, f"FROZEN WINDOW (<= {FREEZE}) -- must reproduce the published table")
    print("\n   published: 1=-1895.99(35cd/54p) 2=-679(12/40) 3=+1769(11/41) "
          "4=+238(12/66) 5=+2350(1/7)")
    ok = (abs(fb[1]["pnl"] - (-1895.99)) < 0.02 and abs(fb[3]["pnl"] - 1769.0) < 0.02
          and abs(fb[5]["pnl"] - 2350.0) < 0.02)
    print(f"   REPRODUCES PUBLISHED TABLE: {ok}")
    if not ok:
        print("   -> method does NOT match the frozen doc; new-window numbers are NOT trustworthy")
        return 1

    nb = table(new_pos, f"NEW WINDOW (> {FREEZE}) -- the forward check")

    print("\n### THE SLOPE, frozen vs new")
    print(f"{'bucket':<10}{'frozen P&L':>14}{'new P&L':>14}{'sign flip?':>12}")
    for mc in sorted(set(fb) | set(nb)):
        f = fb.get(mc, {}).get("pnl", 0.0)
        n = nb.get(mc, {}).get("pnl", 0.0)
        flip = "YES" if (f and n and (f > 0) != (n > 0)) else ""
        print(f"{mc:<10}{f:>14,.2f}{n:>14,.2f}{flip:>12}")

    lonely_f = fb.get(1, {}).get("pnl", 0.0)
    lonely_n = nb.get(1, {}).get("pnl", 0.0)
    pile_f = sum(fb.get(m, {}).get("pnl", 0.0) for m in (3, 4, 5))
    pile_n = sum(nb.get(m, {}).get("pnl", 0.0) for m in (3, 4, 5))
    print(f"\n1-arm (lonely):  frozen {lonely_f:,.2f}   new {lonely_n:,.2f}")
    print(f"3+arm (pile-on): frozen {pile_f:,.2f}   new {pile_n:,.2f}")
    print()
    if pile_n < 0 and lonely_n > pile_n:
        print("CLAIM WEAKENED on new data: the pile-on end is now the LOSING end.")
    elif pile_n >= 0:
        print("CLAIM HOLDS on new data: the pile-on end is still not where losses live.")
    else:
        print("MIXED -- read the buckets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
