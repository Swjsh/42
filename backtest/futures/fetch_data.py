"""Step 1: Pull real MNQ + MES 1-min data from Databento, resample to 5m, save CSVs.

Usage:
    set DATABENTO_API_KEY=db-...
    python backtest/futures/fetch_data.py --start 2025-01-01 --end 2026-06-14

Outputs (in backtest/data/futures/):
    MNQ_1m_continuous.csv   MNQ_5m_continuous.csv
    MES_1m_continuous.csv   MES_5m_continuous.csv

Bar schema: timestamp_et (tz-aware America/New_York), open, high, low, close, volume
"""
from __future__ import annotations
import os, sys, argparse, datetime as dt
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO / "backtest" / "data" / "futures"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def cost_check(client, symbols: list[str], start: str, end: str) -> float:
    total = 0.0
    for sym in symbols:
        cost = client.metadata.get_cost(
            dataset="GLBX.MDP3",
            symbols=[sym],
            stype_in="continuous",
            schema="ohlcv-1m",
            start=start,
            end=end,
        )
        print(f"  {sym}: ${cost:.4f}")
        total += cost
    return total


def pull_symbol(client, symbol: str, start: str, end: str) -> pd.DataFrame:
    """Pull 1-min OHLCV, return DataFrame in engine bar schema (ET timezone)."""
    print(f"  Pulling {symbol} {start} â†’ {end} â€¦", flush=True)
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        symbols=[symbol],
        stype_in="continuous",
        schema="ohlcv-1m",
        start=start,
        end=end,
    )
    raw = data.to_df()
    if raw.empty:
        raise RuntimeError(f"No data returned for {symbol}")

    # Databento returns a ts_event index in UTC nanoseconds
    raw = raw.reset_index()
    ts_col = "ts_event" if "ts_event" in raw.columns else raw.columns[0]
    ts = pd.to_datetime(raw[ts_col], utc=True).dt.tz_convert("America/New_York")

    df = pd.DataFrame({
        "timestamp_et": ts,
        "open":   pd.to_numeric(raw.get("open",   raw.get("Open",   0)), errors="coerce"),
        "high":   pd.to_numeric(raw.get("high",   raw.get("High",   0)), errors="coerce"),
        "low":    pd.to_numeric(raw.get("low",    raw.get("Low",    0)), errors="coerce"),
        "close":  pd.to_numeric(raw.get("close",  raw.get("Close",  0)), errors="coerce"),
        "volume": pd.to_numeric(raw.get("volume", raw.get("Volume", 0)), errors="coerce"),
    }).dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    # Databento OHLCV fields come as integer fixed-point (price * 1e9 for some schemas)
    # ohlcv-1m returns actual prices already for equities; for futures check scale
    if df["close"].mean() > 1_000_000:
        for col in ("open", "high", "low", "close"):
            df[col] = df[col] / 1e9

    print(f"    â†’ {len(df):,} 1m bars, range {df['timestamp_et'].iloc[0]} to {df['timestamp_et'].iloc[-1]}")
    return df


def rth_only(df: pd.DataFrame) -> pd.DataFrame:
    t = df["timestamp_et"].dt.time
    return df[(t >= dt.time(9, 30)) & (t < dt.time(16, 0))].copy()


def resample_5m(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-min bars to 5-min (RTH). Bar label = bar OPEN time."""
    df = df_1m.set_index("timestamp_et").sort_index()
    r = df.resample("5min", label="left", closed="left").agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna(subset=["open", "high", "low", "close"]).reset_index()
    r.rename(columns={"timestamp_et": "timestamp_et"}, inplace=True)
    # Keep only RTH rows
    t = r["timestamp_et"].dt.time
    r = r[(t >= dt.time(9, 30)) & (t < dt.time(16, 0))].reset_index(drop=True)
    return r


def save(df: pd.DataFrame, path: Path):
    df.to_csv(path, index=False)
    print(f"    Saved {len(df):,} rows â†’ {path.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end",   default="2026-06-14")
    ap.add_argument("--symbols", nargs="+", default=["MNQ.c.0", "MES.c.0"])
    ap.add_argument("--skip-cost-check", action="store_true")
    a = ap.parse_args()

    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        sys.exit("ERROR: DATABENTO_API_KEY not set")

    import databento as db
    client = db.Historical(key)

    # â”€â”€ cost check â”€â”€
    if not a.skip_cost_check:
        print(f"\nCost estimate for {a.start} to {a.end}:")
        total = cost_check(client, a.symbols, a.start, a.end)
        print(f"  TOTAL: ${total:.4f}")
        if total > 20:
            sys.exit(f"Cost ${total:.2f} exceeds $20 safety threshold - aborting. Use --skip-cost-check to override.")
        print("  Cost OK. Proceedingâ€¦\n")

    # â”€â”€ pull each symbol â”€â”€
    for sym_continuous in a.symbols:
        ticker = sym_continuous.split(".")[0]  # MNQ or MES
        print(f"=== {ticker} ===")

        df_1m = pull_symbol(client, sym_continuous, a.start, a.end)

        # Save 1m (all sessions)
        path_1m = DATA_DIR / f"{ticker}_1m_continuous.csv"
        save(df_1m, path_1m)

        # Resample to 5m RTH
        df_rth_1m = rth_only(df_1m)
        print(f"    RTH 1m bars: {len(df_rth_1m):,}")
        df_5m = resample_5m(df_rth_1m)
        path_5m = DATA_DIR / f"{ticker}_5m_continuous.csv"
        save(df_5m, path_5m)

        # Quick sanity print
        if not df_5m.empty:
            print(f"    5m close range: {df_5m['close'].min():.2f} â€“ {df_5m['close'].max():.2f}")
            print(f"    5m date range: {df_5m['timestamp_et'].iloc[0].date()} to {df_5m['timestamp_et'].iloc[-1].date()}\n")

    print("Done. Files saved to:", DATA_DIR)


if __name__ == "__main__":
    main()
