"""data_sources — fetch crypto bars from multiple providers, normalized to BarSeries.

Sources:
  - coinbase  : Coinbase Exchange public REST (free, US-OK, no auth)
  - yfinance  : Yahoo Finance via yfinance package (60-day 5m limit)
  - alpaca    : Alpaca crypto bars via MCP (separate workflow — not callable from script)

Coinbase candle format: [time, low, high, open, close, volume]
where `time` is the START of the bar (unix seconds).

The Coinbase API returns bars NEWEST-FIRST. The newest bar is typically IN-PROGRESS
(close_time > now). This is the exact 2026-05-14 SPY heartbeat foot-gun reproduced on crypto.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Literal

import requests

from crypto.lib.bar import Bar, BarSeries

Source = Literal["coinbase", "yfinance", "alpaca"]

COINBASE_GRANULARITIES = {60, 300, 900, 3600, 21600, 86400}  # Coinbase fixed set


def fetch_bars(
    source: Source,
    symbol: str,
    granularity_seconds: int,
    count: int = 100,
) -> BarSeries:
    """Fetch the most recent `count` bars and return a BarSeries (chronological, oldest first).

    Includes the in-progress bar (the caller is responsible for filtering it via bar_reader).
    """
    if source == "coinbase":
        return _fetch_coinbase(symbol, granularity_seconds, count)
    if source == "yfinance":
        return _fetch_yfinance(symbol, granularity_seconds, count)
    if source == "alpaca":
        return _fetch_alpaca(symbol, granularity_seconds, count)
    raise ValueError(f"unknown source: {source!r}")


def _fetch_alpaca(symbol: str, granularity_seconds: int, count: int) -> BarSeries:
    """Alpaca crypto market-data REST (public, no auth)."""
    tf_map = {60: "1Min", 300: "5Min", 900: "15Min", 1800: "30Min", 3600: "1Hour", 86400: "1Day"}
    if granularity_seconds not in tf_map:
        raise ValueError(f"alpaca unsupported granularity: {granularity_seconds}")
    timeframe = tf_map[granularity_seconds]

    # Alpaca uses BTC/USD (slash), not BTC-USD (dash)
    alpaca_symbol = symbol.upper().replace("-", "/")
    if "/" not in alpaca_symbol and alpaca_symbol.endswith("USD") and len(alpaca_symbol) > 3:
        alpaca_symbol = f"{alpaca_symbol[:-3]}/USD"

    # Compute a start time `count * granularity_seconds * 2` seconds in the past
    # (2x oversample so we comfortably get `count` bars even with gaps), then take last `count`.
    start_dt = (datetime.now(timezone.utc) - timedelta(seconds=granularity_seconds * count * 2))
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    r = requests.get(
        "https://data.alpaca.markets/v1beta3/crypto/us/bars",
        params={
            "symbols": alpaca_symbol,
            "timeframe": timeframe,
            "start": start_iso,
            "sort": "asc",
            "limit": count * 3,  # oversample
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    rows = data.get("bars", {}).get(alpaca_symbol, [])
    if not rows:
        raise RuntimeError(f"alpaca returned no bars for {alpaca_symbol} {timeframe}")
    rows = rows[-count:]  # most recent N

    bars = []
    for row in rows:
        ts = row["t"]
        # ISO format like "2026-05-16T14:35:00Z"
        ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        bars.append(Bar(
            open_time=ts_dt,
            open=float(row["o"]),
            high=float(row["h"]),
            low=float(row["l"]),
            close=float(row["c"]),
            volume=float(row["v"]),
            granularity_seconds=granularity_seconds,
            source="alpaca",
        ))
    bars.sort(key=lambda b: b.open_time)
    return BarSeries(
        symbol=alpaca_symbol,
        granularity_seconds=granularity_seconds,
        source="alpaca",
        bars=tuple(bars),
    )


def _fetch_coinbase(symbol: str, granularity_seconds: int, count: int) -> BarSeries:
    if granularity_seconds not in COINBASE_GRANULARITIES:
        raise ValueError(
            f"Coinbase granularity must be one of {sorted(COINBASE_GRANULARITIES)}, "
            f"got {granularity_seconds}"
        )
    if count > 300:
        raise ValueError(f"Coinbase max 300 candles per request, asked for {count}")

    product = symbol.upper()
    if "-" not in product:
        # Coinbase uses BTC-USD style; accept BTCUSD too
        if product.endswith("USD") and len(product) > 3:
            product = f"{product[:-3]}-USD"

    url = f"https://api.exchange.coinbase.com/products/{product}/candles"
    params = {"granularity": granularity_seconds}
    r = requests.get(
        url, params=params,
        headers={"User-Agent": "gamma-crypto-validator/0.1"},
        timeout=15,
    )
    r.raise_for_status()
    rows = r.json()
    rows.sort(key=lambda row: row[0])  # ascending by time
    rows = rows[-count:]
    bars = tuple(
        Bar(
            open_time=datetime.fromtimestamp(int(row[0]), tz=timezone.utc),
            low=float(row[1]),
            high=float(row[2]),
            open=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            granularity_seconds=granularity_seconds,
            source="coinbase",
        )
        for row in rows
    )
    return BarSeries(
        symbol=product,
        granularity_seconds=granularity_seconds,
        source="coinbase",
        bars=bars,
    )


def _fetch_yfinance(symbol: str, granularity_seconds: int, count: int) -> BarSeries:
    import yfinance as yf

    if granularity_seconds not in {60, 300, 900, 1800, 3600, 86400}:
        raise ValueError(f"yfinance unsupported granularity: {granularity_seconds}")
    interval_map = {60: "1m", 300: "5m", 900: "15m", 1800: "30m", 3600: "1h", 86400: "1d"}
    interval = interval_map[granularity_seconds]

    # yfinance crypto symbols: BTC-USD, ETH-USD (same convention as Coinbase, lucky)
    yf_symbol = symbol.upper()
    if "-" not in yf_symbol and yf_symbol.endswith("USD"):
        yf_symbol = f"{yf_symbol[:-3]}-USD"

    # yfinance 5m bars: 60 days max history
    period = "5d" if granularity_seconds <= 300 else "30d"
    df = yf.download(
        yf_symbol, period=period, interval=interval, progress=False, auto_adjust=False
    )
    if df.empty:
        raise RuntimeError(f"yfinance returned empty for {yf_symbol} {interval}")

    # Defensive: flatten MultiIndex columns (yfinance returns ('Open', 'BTC-USD') tuples)
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    df = df.tail(count)

    bars_list = []
    for ts, row in df.iterrows():
        ts_utc = ts.tz_convert("UTC") if ts.tzinfo is not None else ts.tz_localize("UTC")
        vol = float(row["Volume"]) if not _is_nan(row["Volume"]) else 0.0
        bars_list.append(
            Bar(
                open_time=ts_utc.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=vol,
                granularity_seconds=granularity_seconds,
                source="yfinance",
            )
        )
    return BarSeries(
        symbol=yf_symbol,
        granularity_seconds=granularity_seconds,
        source="yfinance",
        bars=tuple(bars_list),
    )


def _is_nan(x) -> bool:
    try:
        return x != x  # NaN is the only value not equal to itself
    except Exception:
        return False


def now_utc() -> datetime:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc)
