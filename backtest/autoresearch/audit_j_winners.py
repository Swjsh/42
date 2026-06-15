"""Read trades.csv and extract J's winning-trade details for engine audit.

For each winner, dumps:
- Exact entry/exit time (5m bar boundary)
- Strike, side, qty, entry/exit premium
- Setup name
- Notes (which describe what J observed at entry)

Plus prints what the engine WOULD have done on those same days with v14 production params.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
TRADES_CSV = REPO.parent / "journal" / "trades.csv"
PARAMS = REPO.parent / "automation" / "state" / "params.json"

sys.path.insert(0, str(REPO))
from autoresearch import runner


def main() -> int:
    with TRADES_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print("=" * 80)
    print("ALL TRADES IN JOURNAL")
    print("=" * 80)
    for r in rows:
        pnl = int(r["dollar_pnl"])
        marker = "+" if pnl > 0 else "-" if pnl < 0 else " "
        print(f"  {marker} {r['date']} {r['time_entry']:>8} -> {r['time_exit']:>8}  "
              f"{r['setup']:<42} {r['c_or_p']} {r['strike']:>5} qty={r['qty']:>3}  "
              f"pnl=${pnl:+5d}  grade={r['trade_grade']}")

    winners = [r for r in rows if int(r["dollar_pnl"]) > 0]
    print()
    print("=" * 80)
    print(f"J'S WINNERS ({len(winners)} trades) -- ENGINE MUST REPRODUCE THESE")
    print("=" * 80)

    params = json.loads(PARAMS.read_text(encoding="utf-8"))

    for w in winners:
        date = dt.date.fromisoformat(w["date"])
        print()
        print(f"--- {w['date']} {w['time_entry']} ---")
        print(f"  setup:       {w['setup']}")
        print(f"  contract:    SPY {w['date']} {w['strike']}{w['c_or_p']}")
        print(f"  qty:         {w['qty']}")
        print(f"  entry:       ${w['entry_px']} ({w['time_entry']})")
        print(f"  exit:        ${w['exit_px']} ({w['time_exit']})  reason: {w.get('stop_px', '?')}")
        print(f"  pnl:         ${w['dollar_pnl']}  hold: {w['hold_minutes']} min")
        print(f"  notes:       {w['notes_short'][:280]}")

        print()
        print(f"  >>> WHAT THE ENGINE DID ON THIS DAY (v14 params):")
        try:
            spy, vix = runner.load_data(date, date)
            if spy.empty:
                print(f"      no SPY data for {date}")
                continue
            result, m = runner.run_with_params(params, date, date, spy, vix)
            print(f"      n_trades={m.n_trades} winners={m.n_winners} losers={m.n_losers} pnl=${m.total_pnl:+.0f}")
            for t in result.trades:
                eside = getattr(t, 'side', '?')
                etime = getattr(t, 'entry_time', '?')
                xtime = getattr(t, 'exit_time', '?')
                eprem = getattr(t, 'entry_premium', 0)
                xprem = getattr(t, 'exit_premium', 0)
                pnl = getattr(t, 'pnl_dollars', 0)
                exit_r = getattr(t, 'exit_reason', '?')
                strike = getattr(t, 'strike', '?')
                print(f"      ENGINE TRADE: {eside} {strike}{w['c_or_p'] if eside == w['c_or_p'] else 'X'} "
                      f"@{etime}  entry=${eprem:.2f} exit=${xprem:.2f} ({exit_r}) pnl=${pnl:+.0f}")
            if m.n_trades == 0:
                print(f"      ENGINE TOOK ZERO TRADES -- need to find what blocked it")
        except Exception as exc:
            print(f"      ERROR: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
