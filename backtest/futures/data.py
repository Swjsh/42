"""Futures market-data layer for the 42 Futures Edition.

Sources (decided 2026-06-14):
  - PRIMARY (real bars): Databento GLBX.MDP3, schema ohlcv-1m, continuous front-month
        symbology MNQ.c.0 / MES.c.0. $125 free credits ~ covers 2yr 1-min x2 symbols
        (call metadata.get_cost() preflight). Historical only (live needs subscription).
  - STATIC BACKUP: FirstRate Data CSV (MNQ/MES, 2019-present, back-/ratio-adjusted continuous).
  - SANITY ONLY: yfinance NQ=F/ES=F (1m last 7d, 5m last 60d — NOT for multi-month backtests).

CONTINUOUS-CONTRACT DISCIPLINE (L-equivalent for futures — the #1 backtest footgun):
  Never trade the RAW spliced series — roll gaps fabricate P&L. Use a roll-adjusted
  continuous series. For point-based intraday strategies (ours), the BACK-ADJUSTED
  (Panama) series is appropriate (preserves absolute point moves); for %-return studies,
  use RATIO-adjusted. We ingest a pre-adjusted continuous series and record which method.

Bar schema (matches the engine's SPY bars so existing watchers run unchanged):
  columns: timestamp_et (tz-aware), open, high, low, close, volume
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path
from typing import Optional
import pandas as pd

RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)


def load_continuous_csv(path: str, tz: str = "America/New_York") -> pd.DataFrame:
    """Load a roll-adjusted continuous-contract CSV (FirstRate/Databento export).

    Expects a datetime column + OHLCV. Normalizes to the engine bar schema.
    """
    df = pd.read_csv(path)
    # find the timestamp column
    tcol = next((c for c in df.columns if c.lower() in
                 ("timestamp", "timestamp_et", "datetime", "date", "time")), df.columns[0])
    ts = pd.to_datetime(df[tcol])
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(tz)
    else:
        ts = ts.dt.tz_convert(tz)
    out = pd.DataFrame({
        "timestamp_et": ts,
        "open": df.get("open", df.get("Open")),
        "high": df.get("high", df.get("High")),
        "low": df.get("low", df.get("Low")),
        "close": df.get("close", df.get("Close")),
        "volume": df.get("volume", df.get("Volume", 0)),
    }).dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return out


def rth_only(df: pd.DataFrame) -> pd.DataFrame:
    t = df["timestamp_et"].dt.time
    return df[(t >= RTH_START) & (t < RTH_END)].reset_index(drop=True)


def resample_5m(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-min RTH bars to 5-min. Bar label = bar OPEN time."""
    df = df_1m.set_index("timestamp_et").sort_index()
    r = df.resample("5min", label="left", closed="left").agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna(subset=["open", "high", "low", "close"]).reset_index()
    t = r["timestamp_et"].dt.time
    return r[(t >= RTH_START) & (t < RTH_END)].reset_index(drop=True)


def pull_yfinance(symbol: str = "NQ=F", interval: str = "5m", period: str = "60d") -> pd.DataFrame:
    """Sanity-only recent bars (yfinance limits: 1m<=7d, 5m<=60d). Not for multi-month."""
    import yfinance as yf
    raw = yf.download(symbol, interval=interval, period=period, progress=False)
    raw = raw.reset_index()
    tcol = "Datetime" if "Datetime" in raw.columns else raw.columns[0]
    ts = pd.to_datetime(raw[tcol], utc=True).dt.tz_convert("America/New_York")
    return pd.DataFrame({"timestamp_et": ts, "open": raw["Open"], "high": raw["High"],
                         "low": raw["Low"], "close": raw["Close"], "volume": raw["Volume"]})


# Databento puller (requires DATABENTO_API_KEY; documented, not auto-run here).
DATABENTO_SNIPPET = '''
import databento as db
client = db.Historical(os.environ["DATABENTO_API_KEY"])
cost = client.metadata.get_cost(dataset="GLBX.MDP3", symbols=["MNQ.c.0"],
        stype_in="continuous", schema="ohlcv-1m", start="2024-06-01", end="2026-06-14")
# verify cost < free credit, then:
data = client.timeseries.get_range(dataset="GLBX.MDP3", symbols=["MNQ.c.0","MES.c.0"],
        stype_in="continuous", schema="ohlcv-1m", start="2024-06-01", end="2026-06-14")
df = data.to_df()
'''
