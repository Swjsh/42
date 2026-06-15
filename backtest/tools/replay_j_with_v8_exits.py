"""Replay J's actual entries through the v8 tiered-exit logic.

Rather than re-running the engine (which fires at different times than J),
this takes J's documented entries (date/time/strike/qty) and runs them through
simulator_real.py with `use_tiered_exits=True`. Compares the result to:
  (a) J's actual closing P&L (broker-validated)
  (b) what v7 ribbon-flip-only exits would have produced on the same entries

Tells us: does v8's tiered exit logic capture more of J's edge?
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.option_pricing_real import option_symbol  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.ribbon import compute_ribbon, ribbon_at  # noqa: E402
from lib.levels import _detect_from_history  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


# J's actual playbook trades (4/29, 5/1, 5/4 — only the rule-followed wins)
J_TRADES = [
    {
        "date": "2026-04-29",
        "entry_time": "10:25",
        "strike": 710,
        "side": "P",
        "qty": 6,
        "j_actual_pnl": 352,
        "rejection_level": 711.40,
    },
    {
        "date": "2026-05-01",
        "entry_time": "13:35",     # 5-min bar boundary (J's 13:36 entry rounds to 13:35 bar)
        "strike": 721,
        "side": "P",
        "qty": 10,
        "j_actual_pnl": 380,       # ~half of total $510 (13:36 add's contribution)
        "rejection_level": 723.50,
    },
    {
        "date": "2026-05-04",
        "entry_time": "10:25",     # closest 5-min bar to J's 10:27 entry
        "strike": 721,
        "side": "P",
        "qty": 10,
        "j_actual_pnl": 738,
        "rejection_level": 721.58,
    },
]


def load_day(date_str: str):
    """Load SPY 5-min bars for a single day, build ribbon and level set."""
    spy_path = REPO / "fixtures" / f"spy_5m_{date_str}_with_warmup.csv"
    spy = pd.read_csv(spy_path)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])

    # Filter to the trade day RTH
    target_date = dt.date.fromisoformat(date_str)
    rth = spy[
        (spy["timestamp_et"].dt.date == target_date)
        & (spy["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True).copy()

    # Add a 'date' column for compatibility
    rth["date"] = rth["timestamp_et"].dt.date

    ribbon = compute_ribbon(rth["close"])
    return rth, ribbon, spy


def find_entry_bar_idx(spy_rth: pd.DataFrame, entry_time_str: str):
    target = dt.datetime.strptime(entry_time_str, "%H:%M").time()
    matches = spy_rth[spy_rth["timestamp_et"].dt.time == target]
    if matches.empty:
        return None
    return int(matches.index[0])


def run_one(trade: dict, use_tiered: bool):
    spy_rth, ribbon, spy_full = load_day(trade["date"])
    entry_idx = find_entry_bar_idx(spy_rth, trade["entry_time"])
    if entry_idx is None:
        return None

    target_date = dt.date.fromisoformat(trade["date"])
    full_history = spy_full[spy_full["timestamp_et"] <= spy_rth.iloc[entry_idx]["timestamp_et"]]
    level_set = _detect_from_history(full_history, target_date)

    fill = simulate_trade_real(
        entry_bar_idx=entry_idx,
        entry_bar=spy_rth.iloc[entry_idx],
        spy_df=spy_rth,
        ribbon_df=ribbon,
        rejection_level=trade["rejection_level"],
        triggers_fired=["level_rejection"],
        side=trade["side"],
        qty=trade["qty"],
        setup="J_REPLAY",
        levels_active=level_set.active,
        levels_carry=level_set.multi_day,
        use_tiered_exits=use_tiered,
        strike_override=trade["strike"],   # use J's ACTUAL strike, not ATM-round
    )
    return fill


def main():
    print("\n" + "=" * 110)
    print("J's actual entries replayed through engine exits — DETAIL")
    print("=" * 110)
    print(f"{'Date':<12} {'K':<5} {'Qty':<4} {'EntryT':<8} {'EntryPx':<8} "
          f"{'TP1Time':<8} {'TP1Px':<8} {'ExitTime':<10} {'ExitPx':<8} {'PnL':<8} {'reason'}")
    print("-" * 110)

    totals = {"j": 0, "v8": 0}
    for t in J_TRADES:
        f8 = run_one(t, use_tiered=True)
        if f8 is None:
            print(f"{t['date']:<12} {t['strike']:<5} sim returned None")
            continue
        v8_pnl = f8.dollar_pnl
        totals["j"] += t["j_actual_pnl"]
        totals["v8"] += v8_pnl
        tp1_t = f8.tp1_time_et.strftime("%H:%M") if f8.tp1_time_et else "—"
        tp1_p = f"${f8.tp1_premium:.2f}" if f8.tp1_premium else "—"
        ex_t = f8.runner_exit_time_et.strftime("%H:%M") if f8.runner_exit_time_et else "—"
        ex_p = f"${f8.runner_exit_premium:.2f}" if f8.runner_exit_premium else "—"
        reason = (f8.exit_reason.value if f8.exit_reason else "NONE")[:30]
        print(
            f"{t['date']:<12} {t['strike']:<5} {t['qty']:<4} "
            f"{t['entry_time']:<8} ${f8.entry_premium:.2f}    "
            f"{tp1_t:<8} {tp1_p:<8} {ex_t:<10} {ex_p:<8} "
            f"${'+' if v8_pnl >= 0 else ''}{int(v8_pnl):<6} {reason}"
        )

    print("-" * 110)
    j_capture_pct = (totals["v8"] / totals["j"]) * 100 if totals["j"] != 0 else 0
    print(f"\n  J actual total: +${totals['j']}")
    print(f"  v8 sim total:   ${'+' if totals['v8'] >= 0 else ''}{int(totals['v8'])}")
    print(f"  v8 captures {j_capture_pct:.1f}% of J's actual edge")
    print()


if __name__ == "__main__":
    main()
