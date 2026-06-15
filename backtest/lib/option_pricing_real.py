"""Real OPRA option contract bar lookup — replaces Black-Scholes with actual fills.

Reads cached CSVs from `backtest/data/options/{symbol}.csv` (populated by
`tools/fetch_option_data.py`). Returns OHLCV+VWAP for any (symbol, time_et).

Fill model (when used by simulator_real.py):
  - Entry: next 5-min bar's VWAP after the trigger bar (proxy for an intra-bar fill)
  - Stop: bar's high (worst adverse for puts → spot up = put down) becomes premium low
  - TP1: bar's high (best favorable for puts) becomes premium high
  - Exit-on-close events (ribbon flip / level stop / time stop): bar.close

Note: for a PUT, premium moves INVERSE to spot. The Alpaca bars give us the option's
own OHLCV — `high` is the put's highest premium during the bar, `low` is the lowest.
We don't need to invert anything; we just use the bar's own high/low.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd


CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "options"

# Process-level in-memory cache for loaded contract bars.
# Populated lazily by load_contract_bars(); persists for the lifetime of the
# worker process.  With multiprocessing.Pool(maxtasksperchild=10), a worker
# handles up to 10 combos before recycling, so all contracts touched by combo-0
# are already in RAM when combo-1 runs.  This eliminates repeated CSV reads
# that caused the overnight/v14e grinders to run 19× slower after the real-fills
# upgrade (each combo triggered hundreds of individual CSV reads from the 7K+
# OPRA cache files).
_CONTRACT_BAR_CACHE: dict[str, Optional[pd.DataFrame]] = {}


@dataclass(frozen=True)
class OptionBar:
    """One 5-min bar from the option chain."""
    timestamp_et: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float
    trade_count: int


def option_symbol(trade_date: dt.date, strike: int, side: str) -> str:
    """Build OCC option symbol: SPY{YYMMDD}{C|P}{strike*1000:08d}."""
    yymmdd = trade_date.strftime("%y%m%d")
    s = side.upper()
    assert s in ("C", "P"), f"side must be C or P, got {side}"
    return f"SPY{yymmdd}{s}{int(round(strike)) * 1000:08d}"


def load_contract_bars(symbol: str) -> Optional[pd.DataFrame]:
    """Load cached bars for a contract. Returns None if not cached.

    Results are stored in _CONTRACT_BAR_CACHE for the lifetime of the worker
    process — subsequent calls for the same symbol return the cached DataFrame
    without touching disk.
    """
    if symbol in _CONTRACT_BAR_CACHE:
        return _CONTRACT_BAR_CACHE[symbol]
    path = CACHE_DIR / f"{symbol}.csv"
    if not path.exists():
        _CONTRACT_BAR_CACHE[symbol] = None
        return None
    df = pd.read_csv(path)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    _CONTRACT_BAR_CACHE[symbol] = df
    return df


def bar_at_or_after(df: pd.DataFrame, when_et: dt.datetime) -> Optional[OptionBar]:
    """Return the first bar whose timestamp is >= when_et.

    The trigger bar in spy_df closes at e.g. 10:25:00. Entry would fill in the
    NEXT 5-min bar (10:25-10:30). We use that bar's VWAP as the entry proxy.
    """
    matches = df[df["timestamp_et"] >= when_et]
    if matches.empty:
        return None
    row = matches.iloc[0]
    return OptionBar(
        timestamp_et=row["timestamp_et"].to_pydatetime(),
        open=float(row["open"]), high=float(row["high"]),
        low=float(row["low"]), close=float(row["close"]),
        volume=int(row["volume"]), vwap=float(row["vwap"]),
        trade_count=int(row["trade_count"]),
    )


def bar_containing(df: pd.DataFrame, when_et: dt.datetime) -> Optional[OptionBar]:
    """Return the bar whose timestamp <= when_et < timestamp + 5 min."""
    when = pd.Timestamp(when_et)
    if when.tz is None and df["timestamp_et"].dt.tz is not None:
        when = when.tz_localize(df["timestamp_et"].dt.tz)
    cutoff = df[df["timestamp_et"] <= when]
    if cutoff.empty:
        return None
    row = cutoff.iloc[-1]
    if (when - row["timestamp_et"]).total_seconds() > 300:
        return None  # gap — no bar covers this time
    return OptionBar(
        timestamp_et=row["timestamp_et"].to_pydatetime(),
        open=float(row["open"]), high=float(row["high"]),
        low=float(row["low"]), close=float(row["close"]),
        volume=int(row["volume"]), vwap=float(row["vwap"]),
        trade_count=int(row["trade_count"]),
    )


def quote_at_index(df: pd.DataFrame, idx: int) -> Optional[OptionBar]:
    """Direct index access for fast iteration in the simulator."""
    if idx < 0 or idx >= len(df):
        return None
    row = df.iloc[idx]
    return OptionBar(
        timestamp_et=row["timestamp_et"].to_pydatetime(),
        open=float(row["open"]), high=float(row["high"]),
        low=float(row["low"]), close=float(row["close"]),
        volume=int(row["volume"]), vwap=float(row["vwap"]),
        trade_count=int(row["trade_count"]),
    )
