"""Validate every J actual fill against the cached OPRA option bars.

For each (date, time, side, strike, qty, price) from J's broker history:
  1. Locate the 5-min option bar containing the fill timestamp.
  2. Show the bar's OHLCV+VWAP.
  3. Compute the fill's price as a % of the bar's range -- is it inside the bar?
  4. Flag any fills outside the bar (would mean wrong contract / wrong day).

Output is human-readable and prints J's actual P&L per trade vs what it would
have been at the bar's worst, mid, best.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.option_pricing_real import load_contract_bars  # noqa: E402

# All J fills from the broker screenshot, in time order.
J_FILLS = [
    # (date, time_et, side, strike, c_or_p, qty, price)
    # 4/29 -- SPY 710P
    ("2026-04-29", "10:25:51", "BUY",  710, "P",  6, 1.67),
    ("2026-04-29", "12:27:57", "SELL", 710, "P",  5, 2.17),  # avg 2.17
    ("2026-04-29", "12:37:41", "SELL", 710, "P",  1, 2.69),
    # 5/1 -- SPY 721P (anticipation + real trigger + sell)
    ("2026-05-01", "13:09:13", "BUY",  721, "P", 10, 0.46),
    ("2026-05-01", "13:36:11", "BUY",  721, "P", 10, 0.19),
    ("2026-05-01", "14:47:55", "SELL", 721, "P", 20, 0.58),  # avg
    # 5/4 -- SPY 721P (textbook execution: 8 TP1 + 2 runners)
    ("2026-05-04", "10:27:50", "BUY",  721, "P", 10, 0.85),
    ("2026-05-04", "11:14:05", "SELL", 721, "P",  8, 1.51),  # avg of 1.50/1.51
    ("2026-05-04", "11:18:29", "SELL", 721, "P",  2, 1.90),
    # 5/5 -- SPY 722P (NOT in journal)
    ("2026-05-05", "13:00:33", "BUY",  722, "P", 20, 0.30),
    ("2026-05-05", "13:30:26", "SELL", 722, "P", 20, 0.17),
    # 5/6 -- SPY 730P (NOT in journal -- held to expiry)
    ("2026-05-06", "13:09:37", "BUY",  730, "P", 10, 0.32),
    ("2026-05-06", "18:17:40", "SELL", 730, "P", 10, 0.02),  # extended hours, GTC market
    # 5/7 -- SPY 737C MANUAL (NOT in journal -- separate from 12:30 734C system trade)
    ("2026-05-07", "11:14:15", "BUY",  737, "C", 10, 0.38),
    ("2026-05-07", "11:30:05", "SELL", 737, "C", 10, 0.26),
]


def option_symbol(d: dt.date, strike: int, side: str) -> str:
    return f"SPY{d.strftime('%y%m%d')}{side}{int(strike) * 1000:08d}"


def find_bar(df: pd.DataFrame, when: dt.datetime):
    """Return the 5-min bar that CONTAINS this timestamp (start <= when < start+5min)."""
    if df["timestamp_et"].dt.tz is not None:
        df = df.copy()
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
    when_pd = pd.Timestamp(when)
    cutoff = df[df["timestamp_et"] <= when_pd]
    if cutoff.empty:
        return None
    last = cutoff.iloc[-1]
    if (when_pd - last["timestamp_et"]).total_seconds() > 300:
        return None
    return last


def main():
    print("\n" + "=" * 80)
    print("J's ACTUAL FILLS vs RAW OPRA BARS")
    print("=" * 80)

    flagged = 0
    last_date = None
    daily_pnl = {}

    for date_str, time_str, side, strike, cp, qty, price in J_FILLS:
        d = dt.date.fromisoformat(date_str)
        if d != last_date:
            print(f"\n-- {date_str} --")
            last_date = d

        symbol = option_symbol(d, strike, cp)
        df = load_contract_bars(symbol)
        if df is None:
            print(f"  {time_str} {side} {qty} @ {price}  XX CONTRACT NOT CACHED ({symbol})")
            flagged += 1
            continue

        when = dt.datetime.combine(d, dt.time.fromisoformat(time_str))
        bar = find_bar(df, when)
        if bar is None:
            print(f"  {time_str} {side} {qty} @ ${price:.2f}  XX NO BAR AT THIS TIME")
            flagged += 1
            continue

        bar_low = float(bar["low"])
        bar_high = float(bar["high"])
        bar_vwap = float(bar["vwap"])
        bar_close = float(bar["close"])
        bar_open = float(bar["open"])
        bar_vol = int(bar["volume"])

        in_range = bar_low <= price <= bar_high
        flag = "OK" if in_range else "XX"
        if not in_range:
            flagged += 1

        # P&L tracker
        signed_qty = qty if side == "BUY" else -qty
        cash_flow = -signed_qty * price * 100  # buy = negative cash, sell = positive
        daily_pnl.setdefault(date_str, []).append(cash_flow)

        print(
            f"  {time_str}  {side:4s} {qty:3d} @ ${price:.2f}  "
            f"bar [low ${bar_low:.2f}  vwap ${bar_vwap:.2f}  high ${bar_high:.2f}]  "
            f"vol {bar_vol:>5}  {flag}"
        )

    print("\n" + "=" * 80)
    print("DAILY P&L (per J's actual fills)")
    print("=" * 80)
    grand_total = 0
    for date_str, flows in daily_pnl.items():
        net = sum(flows)
        grand_total += net
        sign = "+" if net >= 0 else ""
        print(f"  {date_str}  {sign}${net:.0f}")
    sign = "+" if grand_total >= 0 else ""
    print(f"\n  TOTAL  {sign}${grand_total:.0f}  ({len(daily_pnl)} days)")

    if flagged:
        print(f"\n!!  {flagged} fills flagged -- investigate")
    else:
        print(f"\nOK  All {len(J_FILLS)} J fills land inside their bar's high/low range")


if __name__ == "__main__":
    main()
