"""Bull vs bear edge on REAL fills, counted in INDEPENDENT SIGNALS not round trips.

WHY THE UNIT MATTERS (this is the whole point of the script). LEVER-CORRELATION-2026-08-06
established that the fleet is "one bet in five sizes" (r = 0.846, 95.7% sign agreement),
forward-checked 2026-08-16. So when four arms buy the same contract in the same minute, the
book has taken ONE decision and booked FOUR round trips. Counting round trips therefore
measures arm count as much as edge.

Measured inflation: 2.3x - 3.5x. Two consequences:

  1. Raw win rate FLATTERS the bear side and REVERSES the ranking. Raw WR since 2026-07-20 is
     bear 31.9% vs bull 28.3%; per independent signal it is bear 14.3% vs bull 27.0%. Bear's
     losing signals are spread across more arms than its winning ones.

  2. CLAUDE.md OP-16's "re-eval at n >= 20" bar is stated in the inflated unit -- n=20 round
     trips can be as few as 6-7 independent decisions.

ONE SIGNAL = one (date, symbol) cluster, however many arms took it. That is the same
definition LEVER-CORRELATION uses for a contract-day.

DESCRIPTIVE ONLY. Reads the fills ledger, writes nothing, arms nothing.

Run:  backtest/.venv/Scripts/python.exe backtest/tools/direction_edge_by_signal_2026_08_16.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from fills_fifo import mine_real_arm_fills  # noqa: E402  the ONE FIFO implementation

ARMS = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")
WINDOWS = (("2026-06-26", "ALL"), ("2026-07-20", "since 07-20"), ("2026-08-01", "since 08-01"))


def round_trips() -> list[dict]:
    out = []
    for arm in ARMS:
        for rt in mine_real_arm_fills(arm):
            out.append({**rt, "arm": arm})
    out.sort(key=lambda r: r["entry_ts_et"])
    return out


def raw_stats(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    n = len(rows)
    net = sum(r["real_pnl"] for r in rows)
    wins = [r for r in rows if r["real_pnl"] > 0]
    losses = [r for r in rows if r["real_pnl"] <= 0]
    return {
        "n": n, "net": net, "exp": net / n, "wr": 100.0 * len(wins) / n,
        "avg_win": (sum(r["real_pnl"] for r in wins) / len(wins)) if wins else 0.0,
        "avg_loss": (sum(r["real_pnl"] for r in losses) / len(losses)) if losses else 0.0,
    }


def signal_stats(rows: list[dict]) -> dict:
    """Collapse to independent signals: one (date, symbol) cluster = one decision."""
    if not rows:
        return {"n": 0}
    clusters = collections.defaultdict(list)
    for r in rows:
        clusters[(r["date"], r["symbol"])].append(r)
    sigs = [sum(x["real_pnl"] for x in v) for v in clusters.values()]
    n = len(sigs)
    net = sum(sigs)
    wins = [s for s in sigs if s > 0]
    return {"n": n, "raw": len(rows), "inflation": len(rows) / n, "net": net,
            "per_signal": net / n, "wr": 100.0 * len(wins) / n}


def main() -> int:
    rts = round_trips()
    print(f"real engine round trips: {len(rts)}  "
          f"({rts[0]['date']} .. {rts[-1]['date']})")
    print("ONE SIGNAL = one (date, symbol) cluster, however many arms took it.\n")

    for cut, label in WINDOWS:
        sel = [r for r in rts if r["date"] >= cut]
        print(f"=== {label} ===")
        print(f"{'':<7}{'raw n':>7}{'net':>10}{'exp/tr':>9}{'raw WR':>8}{'avgW':>8}"
              f"{'  |':>3}{'signals':>9}{'infl':>7}{'per sig':>9}{'sig WR':>8}")
        for side, name in (("C", "BULL"), ("P", "BEAR")):
            rows = [r for r in sel if r["side"] == side]
            a, b = raw_stats(rows), signal_stats(rows)
            if not a.get("n"):
                print(f"{name:<7}  (none)")
                continue
            print(f"{name:<7}{a['n']:>7}{a['net']:>10,.0f}{a['exp']:>9.2f}{a['wr']:>7.1f}%"
                  f"{a['avg_win']:>8.0f}{'  |':>3}{b['n']:>9}{b['inflation']:>6.1f}x"
                  f"{b['per_signal']:>9.1f}{b['wr']:>7.1f}%")
        print()

    print("Read the RIGHT half. The left half counts arms as well as decisions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
