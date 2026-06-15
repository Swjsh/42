"""Test 'v15-J-edge' params: change strike picker to OTM (matches J's pattern).

The single-knob change vs v14:
  strike_offset_itm: 2  -> -2  (effectively flips ITM-2 to OTM-2 for both puts and calls)

In orchestrator.py the param is normalised to negative for puts. Setting
strike_offset to +2 means strike = atm + 2 for puts = OTM by 2 dollars
(below spot for a put, since put strikes BELOW spot are OTM).

Validates by running engine on:
- J's 3 winners (4/29, 5/1, 5/4)  -> expect engine to match strike + capture more $
- J's 3 losers (5/5, 5/6, 5/7)    -> expect engine to skip OR lose less
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import runner

REPO = Path(__file__).resolve().parent.parent
PARAMS_V14 = json.loads((REPO.parent / "automation" / "state" / "params.json").read_text(encoding="utf-8-sig"))

# v15-j-edge override -- ONE change from v14
PARAMS_J_EDGE = dict(PARAMS_V14)
# Add explicit asymmetric strike offsets (OTM for both directions)
# In orchestrator: strike_offset_bear/bull are passed directly as kwargs to the simulator
# In simulator: for puts: strike = atm - strike_offset.  strike_offset = +2 -> strike = atm + 2 -> OTM put
# In simulator: for calls: strike = atm + strike_offset.  strike_offset = +2 -> strike = atm + 2 -> OTM call
# So +2 = OTM-2 for both. -2 = ITM-2 for both.
PARAMS_J_EDGE["strike_offset_bear"] = 2  # OTM-2 puts (J pattern)
PARAMS_J_EDGE["strike_offset_bull"] = 1  # OTM-1 calls (less aggressive than puts; J's only call was 1 OTM)
# Remove the legacy strike_offset_itm so it doesn't override
PARAMS_J_EDGE.pop("strike_offset_itm", None)

DAYS = [
    ("2026-04-29", "WINNER", "J 710P +$342"),
    ("2026-05-01", "WINNER", "J 721P +$470"),
    ("2026-05-04", "WINNER", "J 721P +$730"),
    ("2026-05-05", "LOSER",  "J 722P -$260 manual"),
    ("2026-05-06", "LOSER",  "J 730P -$300 hold-to-zero"),
    ("2026-05-07", "MIXED",  "FOMC; system 734C -$45 + manual 737C -$120"),
]


def run_one(params: dict, label: str, date_str: str) -> dict:
    d = dt.date.fromisoformat(date_str)
    spy, vix = runner.load_data(d, d)
    if spy.empty:
        return {"label": label, "date": date_str, "error": "no data"}
    result, m = runner.run_with_params(params, d, d, spy, vix)
    trades = []
    for t in result.trades:
        trades.append({
            "side": getattr(t, "side", "?"),
            "strike": getattr(t, "strike", "?"),
            "entry_premium": round(getattr(t, "entry_premium", 0), 3),
            "exit_premium": round(getattr(t, "exit_premium", 0), 3),
            "pnl": round(getattr(t, "pnl_dollars", 0), 2),
            "exit_reason": str(getattr(t, "exit_reason", "?")),
        })
    return {"label": label, "date": date_str, "n_trades": m.n_trades,
            "n_winners": m.n_winners, "total_pnl": round(m.total_pnl, 2),
            "trades": trades}


def main() -> int:
    print("=" * 80)
    print("v14 (current production) vs v15-J-edge (OTM strike picker)")
    print("=" * 80)

    print("\n--- v14 (ITM-2 strikes) ---")
    v14_total = 0
    for d, kind, note in DAYS:
        r = run_one(PARAMS_V14, kind, d)
        v14_total += r.get("total_pnl", 0)
        print(f"  {d} [{kind:6s}] n={r.get('n_trades',0)} pnl=${r.get('total_pnl',0):+5.0f}  ({note})")
        for t in r.get("trades", []):
            print(f"      {t['side']} {t['strike']}  ${t['entry_premium']:.2f}->${t['exit_premium']:.2f}  pnl=${t['pnl']:+.0f}  ({t['exit_reason'][:40]})")
    print(f"  v14 TOTAL: ${v14_total:+.0f}")

    print("\n--- v15-J-edge (OTM-2 puts, OTM-1 calls) ---")
    je_total = 0
    for d, kind, note in DAYS:
        r = run_one(PARAMS_J_EDGE, kind, d)
        je_total += r.get("total_pnl", 0)
        print(f"  {d} [{kind:6s}] n={r.get('n_trades',0)} pnl=${r.get('total_pnl',0):+5.0f}  ({note})")
        for t in r.get("trades", []):
            print(f"      {t['side']} {t['strike']}  ${t['entry_premium']:.2f}->${t['exit_premium']:.2f}  pnl=${t['pnl']:+.0f}  ({t['exit_reason'][:40]})")
    print(f"  v15-J-edge TOTAL: ${je_total:+.0f}")

    print()
    print("=" * 80)
    print(f"  Diff vs v14: ${je_total - v14_total:+.0f}")
    print("=" * 80)

    # J's actual P&L sum across these 6 days for reference
    j_actual = 342 + 470 + 730 - 260 - 300 - 45 - 120
    print(f"J's actual P&L across same 6 days: ${j_actual:+.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
