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
    if ts.dtype == object:
        # Mixed UTC offsets in the source strings (e.g. a continuous series
        # spanning a DST transition, "-05:00" then "-04:00") parse to a Series
        # of per-row Timestamp objects, not a uniform tz-aware dtype -- the
        # `.dt` accessor below then raises AttributeError on current pandas
        # (bug found 2026-07-09 loading MES_1m_continuous.csv, which spans
        # 2025-01-01..2026-06-12 and crosses two DST boundaries). Re-parsing
        # with utc=True still respects each row's own offset (utc=True only
        # changes the OUTPUT dtype to a uniform one); the tz_convert below
        # then lands on the same wall-clock time as before the fix.
        ts = pd.to_datetime(df[tcol], utc=True)
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


def resample_daily(df_1m: pd.DataFrame, tz: str = "America/New_York") -> pd.DataFrame:
    """Resample 1-min bars (RTH or full ETH -- filtered to RTH internally) to ONE
    daily bar per RTH session.

    Bar label (`timestamp_et`) = that session's 09:30 ET open, NOT the first tick's
    raw timestamp -- deterministic even if the 09:30:00 print is occasionally
    missing. This is a swing-horizon (1-5 day) primitive for `swing_sim.py`;
    same bar schema as `resample_5m` (timestamp_et, open, high, low, close, volume)
    so existing watchers/detectors (e.g. lib.ribbon.compute_ribbon, the RRW
    detector) run unchanged on the `close` series.

    Source may be full ETH (Globex, ~24h/day) or already-RTH-filtered -- this
    function filters to RTH itself before grouping, so overnight/premarket prints
    never leak into the daily OHLC (matches lib/levels.py's RTH-only PDH/PDL fix,
    L-equivalent for futures per this module's continuous-contract discipline).
    """
    rth = rth_only(df_1m)
    if rth.empty:
        return rth.copy()
    date = rth["timestamp_et"].dt.tz_convert(tz).dt.date
    g = rth.groupby(date)
    out = g.agg(open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum")).reset_index()
    out = out.rename(columns={out.columns[0]: "date"})
    out["timestamp_et"] = [
        pd.Timestamp.combine(d, RTH_START).tz_localize(tz) for d in out["date"]
    ]
    return out[["timestamp_et", "date", "open", "high", "low", "close", "volume"]]


# 4h-of-RTH bucket boundaries: RTH is 09:30-16:00 (6.5h) -- two buckets/day,
# the 2nd necessarily partial (2.5h). Disclosed design choice (no overnight
# Globex data mixed into a "4h" bar; each bucket is a pure RTH sub-session).
RTH_4H_BOUNDARIES = [dt.time(9, 30), dt.time(13, 30), RTH_END]


def resample_4h_rth(df_1m: pd.DataFrame, tz: str = "America/New_York") -> pd.DataFrame:
    """Resample to 4h-of-RTH bars: [09:30,13:30) and [13:30,16:00) per session.

    The 2nd bucket is a partial 2.5h bar (RTH is only 6.5h/day) -- disclosed,
    not padded with overnight data. Bar label = bucket start time. Same schema
    as `resample_daily`/`resample_5m`.
    """
    rth = rth_only(df_1m)
    if rth.empty:
        return rth.copy()
    ts_local = rth["timestamp_et"].dt.tz_convert(tz)
    date = ts_local.dt.date
    t = ts_local.dt.time
    bucket = pd.cut(
        pd.to_timedelta(ts_local.dt.strftime("%H:%M:%S")),
        bins=[pd.to_timedelta(f"{b.hour}:{b.minute}:00") for b in RTH_4H_BOUNDARIES],
        right=False, include_lowest=True, labels=False,
    )
    df = rth.assign(_date=date, _bucket=bucket).dropna(subset=["_bucket"])
    df["_bucket"] = df["_bucket"].astype(int)
    g = df.groupby(["_date", "_bucket"], sort=True)
    out = g.agg(open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum")).reset_index()
    out = out.rename(columns={"_date": "date", "_bucket": "bucket"})
    bucket_start = {i: b for i, b in enumerate(RTH_4H_BOUNDARIES[:-1])}
    out["timestamp_et"] = [
        pd.Timestamp.combine(r.date, bucket_start[r.bucket]).tz_localize(tz)
        for r in out.itertuples()
    ]
    out = out.sort_values("timestamp_et").reset_index(drop=True)
    return out[["timestamp_et", "date", "bucket", "open", "high", "low", "close", "volume"]]


def fetch_vix_daily(start: str, end: str) -> pd.DataFrame:
    """Daily ^VIX close via yfinance (unrestricted range, free, no creds).

    Returns columns: date (datetime.date), vix_close. Used for the regime
    split (VIX above/below 17.5) -- yfinance is the documented sanity/gap
    source per this module's docstring; daily bars have no yfinance range limit.
    """
    import yfinance as yf
    raw = yf.download("^VIX", start=start, end=end, interval="1d", progress=False, auto_adjust=True)
    if raw.empty:
        return pd.DataFrame(columns=["date", "vix_close"])
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.reset_index()
    return pd.DataFrame({
        "date": pd.to_datetime(raw["Date"]).dt.date,
        "vix_close": raw["Close"].astype(float),
    })


def fetch_es_daily_gap(start: str, end: str) -> pd.DataFrame:
    """Daily ES=F bars via yfinance to cover the cache-end -> now gap.

    Used ONLY to extend the signal/decision window past the cached Databento
    file's last date -- NOT a substitute for the cached 1m data's own native
    overnight bars (verified ETH, see swing_data_prep.py provenance notes).
    Returns the standard bar schema (timestamp_et = that day's 09:30 ET label,
    to match `resample_daily`) plus close-based OHLC (yfinance daily ES=F is
    a continuous-ish front-month series; used for gap coverage only, disclosed
    as lower-fidelity than the Databento continuous series).
    """
    import yfinance as yf
    raw = yf.download("ES=F", start=start, end=end, interval="1d", progress=False, auto_adjust=True)
    if raw.empty:
        return pd.DataFrame(columns=["timestamp_et", "date", "open", "high", "low", "close", "volume"])
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.reset_index()
    dates = pd.to_datetime(raw["Date"]).dt.date
    return pd.DataFrame({
        "timestamp_et": [pd.Timestamp.combine(d, RTH_START).tz_localize("America/New_York") for d in dates],
        "date": dates,
        "open": raw["Open"].astype(float), "high": raw["High"].astype(float),
        "low": raw["Low"].astype(float), "close": raw["Close"].astype(float),
        "volume": raw["Volume"].astype(float),
    })


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
