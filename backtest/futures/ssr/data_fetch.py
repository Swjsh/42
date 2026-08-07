"""SSR battery data-fetch layer -- yfinance bars, CSV cache, provenance ledger.

Contract (backtest/futures/analysis/SSR-battery/DESIGN.md section 2;
markdown/research/SSR-PIVOT-LIQUIDITY-STRATEGY.md section 4):

    fetch_bars(symbol, interval, period, *, refresh=False) -> pd.DataFrame
        columns OUT: timestamp_et (tz-aware America/New_York), open, high,
        low, close, volume. Ascending, deduplicated, MultiIndex flattened.

This is a SANITY-tier puller (yfinance) per backtest/futures/data.py's own
documented data-source doctrine -- disclosed as a smoke battery, never a
multi-month validation source. GC/NQ/ES/VIX all come through this one path.

Cache: CSV at backtest/data/futures/ssr/<sanitized symbol>_<interval>.csv
(sanitize = "=" and "^" -> "_", e.g. "GC=F" 15m -> GC_F_15m.csv). A cache hit
loads from disk (parsing timestamp_et back to tz-aware ET) unless
refresh=True. Every FRESH fetch appends one provenance JSON line to
backtest/data/futures/ssr/provenance.jsonl: {ts_et, symbol, interval,
period, rows, first_ts, last_ts, source:'yfinance'}.

C6 (no look-ahead): UTC -> tz-aware America/New_York conversion happens
immediately on every fresh fetch and on every cache load -- never a raw wall
time, never backtest/lib/et_frame.py's wall-v1 convention.

C7 (no silent failures): an empty yfinance response, or a cache file that
normalizes to zero usable rows, raises RuntimeError. Nothing here ever
returns an empty frame quietly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "backtest" / "data" / "futures" / "ssr"
ET = "America/New_York"

BAR_COLUMNS = ["timestamp_et", "open", "high", "low", "close", "volume"]

# The exact fetch set this module was built to serve (SSR-battery/DESIGN.md
# section 2). Row counts from running this list are quoted in the builder's
# self_test_output; kept here so the probe is reproducible via `__main__`.
REQUIRED_PROBES = [
    ("GC=F", "15m", "60d"),
    ("GC=F", "1h", "730d"),
    ("NQ=F", "15m", "60d"),
    ("ES=F", "15m", "60d"),
    ("^VIX", "15m", "60d"),
]


def _sanitize(symbol: str) -> str:
    return symbol.replace("=", "_").replace("^", "_")


def _cache_path(symbol: str, interval: str) -> Path:
    # Looked up via the module global `DATA_DIR` (not a closed-over default)
    # so tests can monkeypatch DATA_DIR and have every helper follow it.
    return DATA_DIR / f"{_sanitize(symbol)}_{interval}.csv"


def _provenance_path() -> Path:
    return DATA_DIR / "provenance.jsonl"


def _flatten_columns(raw: pd.DataFrame) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.copy()
        raw.columns = raw.columns.get_level_values(0)
    return raw


def _normalize_fetch(raw: pd.DataFrame, symbol: str, interval: str, period: str) -> pd.DataFrame:
    """Raw yfinance download -> engine bar schema, tz-aware ET, ascending, deduped."""
    raw = _flatten_columns(raw)
    raw = raw.reset_index()
    tcol = next((c for c in raw.columns if c in ("Datetime", "Date")), raw.columns[0])
    ts = pd.to_datetime(raw[tcol], utc=True).dt.tz_convert(ET)
    out = pd.DataFrame({
        "timestamp_et": ts,
        "open": pd.to_numeric(raw["Open"], errors="coerce"),
        "high": pd.to_numeric(raw["High"], errors="coerce"),
        "low": pd.to_numeric(raw["Low"], errors="coerce"),
        "close": pd.to_numeric(raw["Close"], errors="coerce"),
        "volume": pd.to_numeric(raw["Volume"], errors="coerce"),
    }).dropna(subset=["open", "high", "low", "close"])
    out = out.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et").reset_index(drop=True)
    if out.empty:
        raise RuntimeError(
            f"fetch_bars({symbol!r}, {interval!r}, {period!r}): normalized frame is "
            "empty after cleaning -- yfinance returned rows but none survived "
            "OHLC dedup/cleaning"
        )
    return out[BAR_COLUMNS]


def _load_cache(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if df.empty:
        raise RuntimeError(f"fetch_bars: cache file {path} exists but has zero rows")
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(ET)
    df = df.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et").reset_index(drop=True)
    return df[BAR_COLUMNS]


def _append_provenance(symbol: str, interval: str, period: str, df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts_et": pd.Timestamp.now(tz=ET).isoformat(),
        "symbol": symbol,
        "interval": interval,
        "period": period,
        "rows": int(len(df)),
        "first_ts": df["timestamp_et"].iloc[0].isoformat(),
        "last_ts": df["timestamp_et"].iloc[-1].isoformat(),
        "source": "yfinance",
    }
    with open(_provenance_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def fetch_bars(symbol: str, interval: str, period: str, *, refresh: bool = False) -> pd.DataFrame:
    """yfinance bars for `symbol` at `interval` over `period`, CSV-cached.

    Cache hit (file exists, refresh=False) -> load from disk, tz-aware ET.
    Cache miss or refresh=True -> fresh yfinance download, normalize, cache,
    log one provenance line. Empty fetch or empty cache always raises
    RuntimeError (C7 -- never a silent empty frame).
    """
    cache_path = _cache_path(symbol, interval)
    if cache_path.exists() and not refresh:
        return _load_cache(cache_path)

    import yfinance as yf
    raw = yf.download(symbol, interval=interval, period=period, progress=False, auto_adjust=False)
    if raw is None or raw.empty:
        raise RuntimeError(
            f"fetch_bars: yfinance returned empty data for symbol={symbol!r} "
            f"interval={interval!r} period={period!r}"
        )

    df = _normalize_fetch(raw, symbol, interval, period)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    _append_provenance(symbol, interval, period, df)
    return df


def _run_required_probes() -> None:
    print(f"SSR data_fetch probes -- cache dir: {DATA_DIR}")
    for symbol, interval, period in REQUIRED_PROBES:
        df = fetch_bars(symbol, interval, period)
        first = df["timestamp_et"].iloc[0]
        last = df["timestamp_et"].iloc[-1]
        print(f"  {symbol:>5s} {interval:>4s} {period:>5s} -> {len(df):5d} rows  "
              f"[{first} .. {last}]")


if __name__ == "__main__":
    _run_required_probes()
