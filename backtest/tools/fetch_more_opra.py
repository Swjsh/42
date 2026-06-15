"""Fetch OPRA option grids for OOS days that don't yet have cached contracts.
Uses the existing fetch_contract_bars infrastructure — same Alpaca key, same schema.
Grabs ATM +/-15 strikes (C+P) for each uncached day in the master OOS window.
This expands the gate test from 68 to ~150+ OOS trades.
Engine-benefit data infra (OP-22). No doctrine/order edits."""
from __future__ import annotations
import sys, datetime as dt, time as _time
from pathlib import Path
from collections import Counter

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
from fetch_option_data import fetch_contract_bars, write_cache, already_cached, cache_path
from lib.option_pricing_real import option_symbol
import sniper_matrix as SM
import pandas as pd

DATA = REPO / "data"


def cached_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return {dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8}


def spy_close_date(date: dt.date) -> float | None:
    """Approximate SPY close for strike centering from the master CSV."""
    cands = sorted([p for p in DATA.glob("spy_5m_*.csv")], key=lambda p: p.stat().st_size, reverse=True)
    for p in cands:
        df = pd.read_csv(p, usecols=["timestamp_et", "close"])
        df["ts"] = SM._to_et(df["timestamp_et"])
        day = df[df["ts"].dt.date == date]
        rth = day[(day["ts"].dt.time >= dt.time(9, 30)) & (day["ts"].dt.time < dt.time(16, 0))]
        if len(rth):
            return float(rth["close"].iloc[-1])
    return None


def main():
    cands = [p for p in DATA.glob("spy_5m_*.csv") if (DATA / p.name.replace("spy_5m", "vix_5m")).exists()]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    master = cands[0]
    spy_dates = set(SM._to_et(pd.read_csv(master)["timestamp_et"]).dt.date)
    # All trading days in master that are NOT already in the cached-fill set and NOT in the missed week
    missed = {dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
    already = cached_fill_days()
    # Take up to 40 uncached days from the most recent end of the master window
    to_fetch = sorted(spy_dates - already - missed, reverse=True)[:40]
    print(f"Cached grids: {len(already)} days. Fetching grids for up to {len(to_fetch)} new days.")

    fetched_days = 0
    for date in reversed(to_fetch):  # oldest first for determinism
        center = spy_close_date(date)
        if center is None:
            print(f"  skip {date}: no SPY close in master")
            continue
        atm = int(round(center))
        contracts = [(date.strftime("%Y-%m-%d"), option_symbol(date, atm + offset, side))
                     for offset in range(-15, 16) for side in ("C", "P")]
        n_new = 0
        for date_str, sym in contracts:
            if already_cached(sym):
                continue
            try:
                rows = fetch_contract_bars(sym, date_str)
                if rows:
                    write_cache(sym, rows)
                    n_new += 1
                _time.sleep(0.10)
            except Exception as e:
                print(f"    FAIL {sym}: {e}")
        print(f"  {date}: ATM {atm}, fetched {n_new} new contracts")
        if n_new > 0:
            fetched_days += 1

    new_total = len(cached_fill_days())
    print(f"\nDone. New cached days with >=8 contracts: {new_total} (was {len(already)}), fetched {fetched_days} new days.")


if __name__ == "__main__":
    raise SystemExit(main())
