"""Sweep strike_offset from -2 (ITM-2) to +3 (OTM-3) and find what matches J best.

Tests on:
- J's 3 winners: ENGINE SHOULD MAKE MONEY
- J's 3 losers: ENGINE SHOULD SKIP (or make less negative)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import runner

REPO = Path(__file__).resolve().parent.parent
PARAMS_BASE = json.loads((REPO.parent / "automation" / "state" / "params.json").read_text(encoding="utf-8-sig"))

DAYS_WIN = ["2026-04-29", "2026-05-01", "2026-05-04"]
DAYS_LOSS = ["2026-05-05", "2026-05-06", "2026-05-07"]

J_PNL_BY_DAY = {
    "2026-04-29": 342, "2026-05-01": 470, "2026-05-04": 730,
    "2026-05-05": -260, "2026-05-06": -300, "2026-05-07": -45 - 120,  # both 5/7 trades
}


def run_with_offset(offset: int, day: str) -> tuple[int, float]:
    p = dict(PARAMS_BASE)
    p["strike_offset_bear"] = offset
    p["strike_offset_bull"] = offset
    p.pop("strike_offset_itm", None)
    d = dt.date.fromisoformat(day)
    spy, vix = runner.load_data(d, d)
    if spy.empty:
        return 0, 0.0
    result, m = runner.run_with_params(p, d, d, spy, vix)
    return m.n_trades, m.total_pnl


def main() -> int:
    offsets = [-2, -1, 0, 1, 2, 3]  # -2=ITM-2, 0=ATM, +2=OTM-2, +3=OTM-3
    print(f"{'offset':>8} {'label':<8} | {'4/29':>10} {'5/01':>10} {'5/04':>10} | {'5/05':>10} {'5/06':>10} {'5/07':>10} | {'win-tot':>10} {'loss-tot':>10} {'NET':>10}")
    print("-" * 130)
    print(f"{'J actual':>17} | {342:>10} {470:>10} {730:>10} | {-260:>10} {-300:>10} {-165:>10} | {1542:>10} {-725:>10} {817:>10}")
    print("-" * 130)

    for off in offsets:
        label = (f"ITM-{abs(off)}" if off < 0 else
                 "ATM" if off == 0 else
                 f"OTM-{off}")
        win_pnls = []
        loss_pnls = []
        for d in DAYS_WIN:
            _, pnl = run_with_offset(off, d)
            win_pnls.append(pnl)
        for d in DAYS_LOSS:
            _, pnl = run_with_offset(off, d)
            loss_pnls.append(pnl)
        win_tot = sum(win_pnls)
        loss_tot = sum(loss_pnls)
        net = win_tot + loss_tot
        cells = [f"${p:+10.0f}" for p in win_pnls + loss_pnls]
        print(f"{off:>+8d} {label:<8} | {cells[0]:>10} {cells[1]:>10} {cells[2]:>10} | {cells[3]:>10} {cells[4]:>10} {cells[5]:>10} | ${win_tot:+10.0f} ${loss_tot:+10.0f} ${net:+10.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
