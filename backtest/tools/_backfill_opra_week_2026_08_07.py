"""Leading-edge OPRA backfill: 2026-07-23 .. 2026-08-06 (the gap that zeroed the
score-ladder week replay -- every week candidate died no_opra_cache).

Same fetch/auth/CSV path as expand_opra_cache.py (no new vendor, wired Alpaca data key,
prior-day OPRA is available -- only same-day is 403). Strike range per day =
[floor(day_low)-3, ceil(day_high)+3], both C/P, skip already_cached.

Usage: backtest/.venv/Scripts/python.exe backtest/tools/_backfill_opra_week_2026_08_07.py [--plan-only]
"""
from __future__ import annotations

import datetime as dt
import math
import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from expand_opra_cache import (  # noqa: E402
    already_cached, fetch_contract_bars, option_symbol, write_cache, write_empty_sentinel,
)
from _alpaca_creds import resolve_alpaca_creds  # noqa: E402

MASTER = REPO / "data" / "spy_5m_2026-05-19_2026-08-06.csv"
START, END = dt.date(2026, 7, 23), dt.date(2026, 8, 6)
SLEEP = 0.25


def main() -> int:
    plan_only = "--plan-only" in sys.argv
    df = pd.read_csv(MASTER)
    df["ts"] = pd.to_datetime(df["timestamp_et"])
    df["date"] = df["ts"].dt.date
    df["t"] = df["ts"].dt.time
    rth = df[(df["t"] >= dt.time(9, 30)) & (df["t"] < dt.time(16, 0))]
    days = [d for d in sorted(rth["date"].unique()) if START <= d <= END]
    todo = []
    for d in days:
        day = rth[rth["date"] == d]
        lo, hi = float(day["low"].min()), float(day["high"].max())
        for strike in range(math.floor(lo) - 3, math.ceil(hi) + 4):
            for side in ("C", "P"):
                sym = option_symbol(d, strike, side)
                if not already_cached(sym):
                    todo.append((d, sym))
    print(f"[backfill-week] {len(days)} days, {len(todo)} contracts to fetch", flush=True)
    if plan_only:
        for d, s in todo[:20]:
            print("  ", d, s)
        return 0
    key, secret = resolve_alpaca_creds()[:2]   # returns (key, secret, source)
    n_ok = n_empty = n_err = 0
    for i, (d, sym) in enumerate(todo):
        try:
            rows = fetch_contract_bars(sym, d, key, secret)
            if rows:
                write_cache(sym, rows)
                n_ok += 1
            else:
                write_empty_sentinel(sym)
                n_empty += 1
        except Exception as e:  # noqa: BLE001
            n_err += 1
            print(f"  ERR {sym}: {e}", flush=True)
        if i % 50 == 0:
            print(f"  {i}/{len(todo)} ok={n_ok} empty={n_empty} err={n_err}", flush=True)
        time.sleep(SLEEP)
    print(f"[backfill-week] DONE ok={n_ok} empty={n_empty} err={n_err}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
