"""Fetch SPY + VIX 5-min OHLCV from yfinance for a given date range.

Yahoo Finance gives 5-min intraday data going back ~60 days for free.
That's exactly the window we want for the playbook validation.

Output: backtest/data/spy_5m_{from}_{to}.csv  (and same for vix)
Schema: timestamp_et, open, high, low, close, volume

Usage:
    python tools/fetch_data.py --start 2026-03-01 --end 2026-05-06
    python tools/fetch_data.py --days 60                       # alias: last N calendar days
    python tools/fetch_data.py --known-trades                  # fetches the 3 known trade days separately for fixtures

Notes:
  - yfinance returns timestamps in UTC. We convert to America/New_York (handles DST automatically).
  - Pre-market (04:00-09:30 ET) and post-market (16:00-20:00 ET) bars are dropped — heartbeat only fires 09:35-15:50.
  - Weekend/holiday bars naturally absent.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd
import yfinance as yf
import pytz

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
FIXTURES = REPO / "fixtures"
ET = pytz.timezone("America/New_York")

KNOWN_TRADE_DATES = ["2026-04-29", "2026-05-01", "2026-05-04"]


def _format_window(df: pd.DataFrame, include_premarket: bool = True) -> pd.DataFrame:
    """Normalize a yfinance bars DataFrame to our standard schema.

    If include_premarket=True, retains 04:00-09:30 ET bars (used by levels.py to
    derive PMH/PML). Default True since the playbook's "level rejection" trigger
    sometimes targets the premarket high.
    """
    if df.empty:
        return df
    df = df.copy()
    df.index = df.index.tz_convert(ET) if df.index.tz is not None else df.index.tz_localize("UTC").tz_convert(ET)
    df.reset_index(inplace=True)
    ts_col = df.columns[0]  # 'Datetime' or similar
    df = df.rename(columns={
        ts_col: "timestamp_et",
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    df = df[["timestamp_et", "open", "high", "low", "close", "volume"]]
    times = df["timestamp_et"].dt.tz_convert(ET)
    if include_premarket:
        # Keep premarket (04:00) through end of regular session (16:00 ET)
        in_window = (times.dt.time >= dt.time(4, 0)) & (times.dt.time < dt.time(16, 0))
    else:
        in_window = (times.dt.time >= dt.time(9, 30)) & (times.dt.time < dt.time(16, 0))
    df = df.loc[in_window].reset_index(drop=True)
    return df


def fetch(symbol: str, start: str, end: str, include_premarket: bool = True) -> pd.DataFrame:
    """Fetch 5-min bars from yfinance. yfinance treats `end` as exclusive."""
    print(f"  fetching {symbol} from {start} to {end} ...")
    raw = yf.download(
        symbol, start=start, end=end, interval="5m",
        progress=False, auto_adjust=False, prepost=include_premarket,
    )
    if raw.empty:
        print(f"  WARN: no data returned for {symbol}")
        return raw
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return _format_window(raw, include_premarket=include_premarket)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"  wrote {path.relative_to(REPO)}  ({len(df)} bars)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", help="Start date (YYYY-MM-DD)")
    ap.add_argument("--end", help="End date (YYYY-MM-DD), exclusive")
    ap.add_argument("--days", type=int, help="Last N calendar days (alternative to --start/--end)")
    ap.add_argument("--known-trades", action="store_true",
                    help="Fetch the 3 known trade days separately into fixtures/")
    args = ap.parse_args()

    if args.known_trades:
        print("Fetching known-trade fixture days for e2e tests:")
        # Need ~5 prior trading days for EMA(48) warmup. 8 calendar days covers 5+ trading days.
        for date in KNOWN_TRADE_DATES:
            d = dt.date.fromisoformat(date)
            start_str = (d - dt.timedelta(days=8)).isoformat()
            end_str = (d + dt.timedelta(days=1)).isoformat()
            for sym, name in [("SPY", "spy"), ("^VIX", "vix")]:
                df = fetch(sym, start_str, end_str)
                if not df.empty:
                    out = FIXTURES / f"{name}_5m_{date}_with_warmup.csv"
                    write_csv(df, out)
        return 0

    if args.days:
        end = dt.date.today()
        start = end - dt.timedelta(days=args.days)
        start_str, end_str = start.isoformat(), end.isoformat()
    elif args.start and args.end:
        start_str, end_str = args.start, args.end
    else:
        ap.error("Either --start/--end OR --days OR --known-trades is required.")

    print(f"Fetching SPY + VIX 5-min bars: {start_str} to {end_str}")
    spy = fetch("SPY", start_str, end_str)
    vix = fetch("^VIX", start_str, end_str)

    if spy.empty:
        print("ABORT: no SPY data returned (yfinance window exceeded? 60d max for 5m bars)")
        return 1

    write_csv(spy, DATA / f"spy_5m_{start_str}_{end_str}.csv")
    if not vix.empty:
        write_csv(vix, DATA / f"vix_5m_{start_str}_{end_str}.csv")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
