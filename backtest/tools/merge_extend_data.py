"""Merge the historical data file (through 2026-05-22) with the incremental
file (2026-05-19 to 2026-06-16) into a single extended dataset.

Output:
  backtest/data/spy_5m_2025-01-01_2026-06-16.csv
  backtest/data/vix_5m_2025-01-01_2026-06-16.csv

Deduplication: on timestamp_et (keeps last occurrence, so the incremental
file values win in the 5/19-5/22 overlap window).
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backtest" / "data"


def merge(sym: str) -> None:
    base = DATA / f"{sym}_5m_2025-01-01_2026-05-22.csv"
    incr = DATA / f"{sym}_5m_2026-05-19_2026-06-16.csv"
    out  = DATA / f"{sym}_5m_2025-01-01_2026-06-16.csv"

    print(f"Loading {base.name} ...")
    df_base = pd.read_csv(base)
    print(f"  {len(df_base)} rows")

    print(f"Loading {incr.name} ...")
    df_incr = pd.read_csv(incr)
    print(f"  {len(df_incr)} rows")

    combined = pd.concat([df_base, df_incr], ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["timestamp_et"], keep="last")
    combined = combined.sort_values("timestamp_et").reset_index(drop=True)
    after = len(combined)
    print(f"  merged: {before} -> {after} rows (removed {before - after} dupes)")

    # Sanity check: confirm we have data past 2026-05-22
    max_ts = combined["timestamp_et"].max()
    print(f"  date range: {combined['timestamp_et'].min()[:10]} to {max_ts[:10]}")
    assert "2026-06" in max_ts, f"merge didn't extend past May: max={max_ts}"

    combined.to_csv(out, index=False)
    print(f"  wrote {out.relative_to(ROOT)}  ({after} rows)")


if __name__ == "__main__":
    merge("spy")
    merge("vix")
    print("\nDone. New OOS window: 2026-05-08 to 2026-06-16.")
