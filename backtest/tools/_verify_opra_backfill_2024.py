"""Post-backfill completeness verification for OPRA-BACKFILL-2026-07-31.

Rewritten 2026-08-02 (the original draft only checked "does >=1 real contract
file exist for this day", which conflates distinct-expiry-dates with usable
coverage -- it would have silently PASSED 2024-12-23, a day where the SPY 5m
bar cache is severely truncated (11 of 78 expected bars, live-reconfirmed
against Alpaca) even though its OPTIONS side is fully populated. See
analysis/deep-research/OPRA-BACKFILL-2026-07-31.md for the full writeup this
script's numbers feed.

For every NYSE trading day in [start, end] this checks BOTH:
  1. SPY 5m bar completeness (actual bar count vs the expected count for that
     day's real session length -- catches partial-day truncation, not just
     "any bars exist").
  2. Near-ATM (round(daily_close) +/- 2, both call+put) OPRA contract
     coverage -- real (non-empty-sentinel, non-header-only) rows, not just
     "a file exists somewhere for this expiry".

No `pandas_market_calendars` dependency (not in backtest/requirements.txt) --
the 2024 trading-day calendar is derived from a hardcoded NYSE holiday list
+ weekday filtering. Re-derive via `pandas_market_calendars.get_calendar("XNYS")`
if this is ever extended past 2024.

Usage:
    python tools/_verify_opra_backfill_2024.py
"""
from __future__ import annotations

import datetime as dt
import random
import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "data"
OPT_DIR = DATA_DIR / "options"
SPY_MASTER = DATA_DIR / "spy_5m_2024-01-18_2024-12-31.csv"

START = dt.date(2024, 1, 18)
END = dt.date(2024, 12, 31)

# NYSE closures in range (derived from pandas_market_calendars XNYS, verified
# 2026-08-02 -- not a project dependency, so hardcoded rather than imported).
HOLIDAYS_2024 = {
    dt.date(2024, 2, 19),   # Presidents Day
    dt.date(2024, 3, 29),   # Good Friday
    dt.date(2024, 5, 27),   # Memorial Day
    dt.date(2024, 6, 19),   # Juneteenth
    dt.date(2024, 7, 4),    # Independence Day
    dt.date(2024, 9, 2),    # Labor Day
    dt.date(2024, 11, 28),  # Thanksgiving
    dt.date(2024, 12, 25),  # Christmas
}
# 1:00pm ET early closes -> 42 expected 5-min bars (09:30-13:00) instead of 78.
EARLY_CLOSES_2024 = {
    dt.date(2024, 7, 3): 42,
    dt.date(2024, 11, 29): 42,
    dt.date(2024, 12, 24): 42,
}

SPY_BAR_DEFICIT_HARD_FAIL = 15  # >15 missing bars (~19% of a session) = hard FAIL
NEAR_ATM_OFFSETS = range(-2, 3)  # ATM +/- 2, matches _probe_opra_floor.py's definition


def trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in HOLIDAYS_2024:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def option_symbol(trade_date: dt.date, strike: int, side: str) -> str:
    yymmdd = trade_date.strftime("%y%m%d")
    return f"SPY{yymmdd}{side}{int(round(strike)) * 1000:08d}"


def main() -> int:
    cal_days = trading_days(START, END)

    spy = pd.read_csv(SPY_MASTER)
    spy["ts"] = pd.to_datetime(spy["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    spy["date"] = spy["ts"].dt.date
    bar_counts = spy.groupby("date").size()
    daily_close = spy.groupby("date").agg(close=("close", "last"))

    pat = re.compile(r"^SPY(\d{6})([CP])(\d{8})\.csv(\.empty)?$")
    by_day: dict[dt.date, dict[tuple[float, str], str]] = {}
    for f in OPT_DIR.iterdir():
        m = pat.match(f.name)
        if not m:
            continue
        code, side, strike_raw, is_empty = m.groups()
        if not code.startswith("24"):
            continue
        yy, mm, dd = int(code[0:2]), int(code[2:4]), int(code[4:6])
        date = dt.date(2000 + yy, mm, dd)
        strike = int(strike_raw) / 1000.0
        if not is_empty and f.stat().st_size <= 100:
            continue  # header-only / near-empty real file -- don't count as real coverage
        state = "empty" if is_empty else "real"
        by_day.setdefault(date, {})[(strike, side)] = state

    rows = []
    for date in cal_days:
        expected = EARLY_CLOSES_2024.get(date, 78)
        actual = int(bar_counts.get(date, 0))
        deficit = expected - actual
        has_spy = date in bar_counts.index
        if not has_spy:
            spy_status = "MISSING"
        elif deficit > SPY_BAR_DEFICIT_HARD_FAIL:
            spy_status = "SEVERE_GAP"
        elif deficit > 0:
            spy_status = "MINOR_TAIL_GAP"
        else:
            spy_status = "OK"

        n_real = n_empty = n_missing = 0
        atm = None
        opt_status = "N/A_NO_SPY"
        if has_spy:
            close = float(daily_close.loc[date, "close"])
            atm = int(round(close))
            contracts = by_day.get(date, {})
            for off in NEAR_ATM_OFFSETS:
                for side in ("C", "P"):
                    st = contracts.get((float(atm + off), side), "missing")
                    if st == "real":
                        n_real += 1
                    elif st == "empty":
                        n_empty += 1
                    else:
                        n_missing += 1
            opt_status = "OK" if n_real > 0 else ("GAP" if n_empty > 0 else "MISSING")

        if spy_status in ("SEVERE_GAP", "MISSING") or opt_status in ("GAP", "MISSING"):
            final = "FAIL"
        elif spy_status == "MINOR_TAIL_GAP":
            final = "PASS_WITH_CAVEAT"
        else:
            final = "PASS"

        rows.append({
            "date": date, "expected_bars": expected, "actual_bars": actual,
            "deficit": deficit, "spy_status": spy_status, "atm": atm,
            "near_atm_real": n_real, "near_atm_empty": n_empty,
            "near_atm_missing": n_missing, "opt_status": opt_status, "final": final,
        })

    df = pd.DataFrame(rows)
    counts = df["final"].value_counts()
    print(f"Trading days {START}..{END}: {len(df)}")
    print(counts.to_string())
    print()
    bad = df[df["final"] != "PASS"]
    if len(bad):
        print("Non-clean days:")
        print(bad[["date", "expected_bars", "actual_bars", "deficit", "spy_status", "opt_status", "final"]]
              .to_string(index=False))
    usable = df["final"].isin(["PASS", "PASS_WITH_CAVEAT"]).sum()
    clean = (df["final"] == "PASS").sum()
    print(f"\nverified usable (PASS + PASS_WITH_CAVEAT): {usable} / {len(df)}")
    print(f"fully clean (PASS only): {clean} / {len(df)}")

    # Spot-check 3 TRUE random PASS days (no fixed seed -- a repeatable seed
    # can hide a fetcher bug that only shows up on the "unlucky" draw).
    pass_days = df[df["final"] == "PASS"]["date"].tolist()
    print("\n--- SPOT CHECK: 3 random clean days ---")
    for d in random.sample(pass_days, min(3, len(pass_days))):
        row = df[df["date"] == d].iloc[0]
        atm = int(row["atm"])
        sym_c = option_symbol(d, atm, "C")
        path_c = OPT_DIR / f"{sym_c}.csv"
        cdf = pd.read_csv(path_c)
        print(f"\n{d} (atm={atm}): {path_c.name}  rows={len(cdf)}")
        print(f"  first: {cdf.iloc[0].to_dict()}")
        print(f"  last:  {cdf.iloc[-1].to_dict()}")

    return 0 if bad.empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
